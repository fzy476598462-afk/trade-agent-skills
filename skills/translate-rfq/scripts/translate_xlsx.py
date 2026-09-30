"""Translate XLSX text nodes while preserving every untouched archive member."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

TEXT_NODE = re.compile(
    r"(<(?P<prefix>[\w.-]+:)?t\b[^>]*>)(?P<text>.*?)(</(?P=prefix)t>)", re.DOTALL
)
# A separate pattern handles the normal, unprefixed <t> elements.
PLAIN_TEXT_NODE = re.compile(r"(<t\b[^>]*>)(?P<text>.*?)(</t>)", re.DOTALL)
PHONETIC_NODE = re.compile(r"<(?:[\w.-]+:)?rPh\b[^>]*>.*?</(?:[\w.-]+:)?rPh>", re.DOTALL)
DATA_CODE = re.compile(
    r"^(?=.*\d)[A-Z0-9][A-Z0-9 ./_+\-]*$|^\d+(?:[.,]\d+)?$", re.IGNORECASE | re.ASCII
)
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return (
            hashlib.file_digest(stream, "sha256").hexdigest()
            if hasattr(hashlib, "file_digest")
            else hashlib.sha256(stream.read()).hexdigest()
        )


def text_member(name: str) -> bool:
    return name == "xl/sharedStrings.xml" or bool(re.fullmatch(r"xl/worksheets/[^/]+\.xml", name))


def xml_strings(data: bytes) -> list[str]:
    root = ET.fromstring(data)

    # Cell text only; attributes, formulas, numbers, drawing labels and phonetic guides stay intact.
    def walk(node):
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "rPh":
            return
        if tag == "t":
            yield node.text or ""
        for child in node:
            yield from walk(child)

    return list(walk(root))


def inspect_archive(archive: zipfile.ZipFile) -> None:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Workbook has duplicate archive members")
    if "xl/workbook.xml" not in names:
        raise ValueError("Input is not an XLSX workbook")
    if any(name.startswith("_xmlsignatures/") for name in names):
        raise ValueError(
            "Signed workbooks are not supported: translating invalidates the signature"
        )
    if any(item.flag_bits & 1 for item in archive.infolist()):
        raise ValueError("Encrypted workbooks are not supported")
    if sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_BYTES:
        raise ValueError("Workbook exceeds the 512 MiB uncompressed limit")


def protected(value: str) -> bool:
    return not value.strip() or bool(DATA_CODE.fullmatch(value.strip()))


def extract(source: Path, destination: Path, glossary: dict | None = None) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("Mapping output must differ from the source workbook")
    glossary = glossary or {}
    if not isinstance(glossary, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in glossary.items()
    ):
        raise ValueError("Glossary must map text strings to text strings")
    strings = {}
    with zipfile.ZipFile(source) as archive:
        inspect_archive(archive)
        for name in archive.namelist():
            if text_member(name):
                for value in xml_strings(archive.read(name)):
                    if value:
                        strings.setdefault(
                            value, value if protected(value) else glossary.get(value, "")
                        )
    payload = {"source_sha256": digest(source), "map": strings}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return {
        "strings": len(strings),
        "unfilled": sum(not value for value in strings.values()),
        "map": str(destination),
    }


def rewrite_xml(data: bytes, mapping: dict[str, str]) -> tuple[bytes, int]:
    ET.fromstring(data)
    source = data.decode("utf-8-sig")
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        if any(start <= match.start() < end for start, end in phonetic_spans):
            return match.group(0)
        original = html.unescape(match.group("text"))
        replacement = mapping.get(original, "")
        if not replacement or replacement == original:
            return match.group(0)
        if protected(original):
            raise ValueError(
                f"Refusing to translate a numeric value, identifier or code: {original}"
            )
        if replacement != replacement.strip() and not re.search(
            r"xml:space\s*=\s*['\"]preserve['\"]", match.group(1)
        ):
            raise ValueError(
                "New leading/trailing whitespace requires xml:space=preserve; retain original spacing"
            )
        count += 1
        return (
            match.group(1)
            + escape(replacement)
            + match.group(3 if match.re is PLAIN_TEXT_NODE else 4)
        )

    # The two patterns are disjoint, so translated text is never revisited.
    result = source
    for pattern in (TEXT_NODE, PLAIN_TEXT_NODE):
        phonetic_spans = [(match.start(), match.end()) for match in PHONETIC_NODE.finditer(result)]
        result = pattern.sub(replace, result)
    encoded = result.encode("utf-8")
    ET.fromstring(encoded)  # Detect illegal XML characters before creating a destination.
    return (encoded if count else data), count


def apply(source: Path, map_path: Path, destination: Path) -> dict:
    if destination.resolve() in {source.resolve(), map_path.resolve()}:
        raise ValueError("Destination must differ from both input files")
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    payload = json.loads(map_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("source_sha256") != digest(source):
        raise ValueError(
            "Mapping belongs to a different or modified source workbook; extract again"
        )
    mapping = payload.get("map")
    if not isinstance(mapping, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in mapping.items()
    ):
        raise ValueError("map must contain text keys and text values")
    changes = {}
    count = 0
    with zipfile.ZipFile(source) as original:
        inspect_archive(original)
        known = set()
        for name in original.namelist():
            if text_member(name):
                data = original.read(name)
                known.update(xml_strings(data))
                rewritten, translated = rewrite_xml(data, mapping)
                if translated:
                    changes[name] = rewritten
                    count += translated
        unknown = set(mapping) - known
        if unknown:
            raise ValueError(f"Mapping contains {len(unknown)} strings absent from the workbook")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, suffix=".xlsx", delete=False
            ) as stream:
                temporary = Path(stream.name)
            with zipfile.ZipFile(temporary, "w") as output:
                output.comment = original.comment
                for item in original.infolist():
                    output.writestr(
                        copy.copy(item),
                        changes[item.filename]
                        if item.filename in changes
                        else original.read(item.filename),
                    )
            with zipfile.ZipFile(temporary) as output:
                if original.namelist() != output.namelist() or output.testzip() is not None:
                    raise ValueError("Workbook archive verification failed")
                for name in original.namelist():
                    if name not in changes and original.read(name) != output.read(name):
                        raise ValueError(f"Untouched member changed: {name}")
            # A hard link publishes atomically without overwriting an existing destination.
            os.link(temporary, destination)
            return {
                "output": str(destination),
                "translated_nodes": count,
                "changed_members": sorted(changes),
                "untouched_members_identical": True,
                "images_preserved": sum(
                    name.startswith("xl/media/") for name in original.namelist()
                ),
                "unfilled": sum(not value for value in mapping.values()),
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extracting = commands.add_parser("extract", help="Extract shared and inline cell text")
    extracting.add_argument("source", type=Path)
    extracting.add_argument("map", type=Path)
    extracting.add_argument("--glossary", type=Path)
    applying = commands.add_parser("apply", help="Apply completed translations to a new workbook")
    applying.add_argument("source", type=Path)
    applying.add_argument("map", type=Path)
    applying.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "extract":
            glossary = (
                json.loads(args.glossary.read_text(encoding="utf-8-sig")) if args.glossary else None
            )
            result = extract(args.source, args.map, glossary)
        else:
            result = apply(args.source, args.map, args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, TypeError, OSError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
