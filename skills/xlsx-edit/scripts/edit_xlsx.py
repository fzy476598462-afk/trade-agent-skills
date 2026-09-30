"""Patch existing literal XLSX cells, preserving unrelated package contents."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TAG = r"(?:[A-Za-z_][\w.-]*:)?"
CELLS = re.compile(rf"<{TAG}c\b[^>]*(?:/>|>.*?</{TAG}c>)", re.S)
REF = re.compile(r"[A-Z]{1,3}[1-9][0-9]{0,6}")


def package(path):
    archive = zipfile.ZipFile(path)
    infos = archive.infolist()
    names = [i.filename for i in infos]
    if len(set(names)) != len(names) or any(i.flag_bits & 1 for i in infos):
        archive.close()
        raise ValueError("Duplicate/encrypted package entries are unsupported")
    if sum(i.file_size for i in infos) > 512 * 1024 * 1024 or any(
        n.startswith("_xmlsignatures/") for n in names
    ):
        archive.close()
        raise ValueError("Oversized/signed workbooks are unsupported")
    return archive


def sheets(archive):
    links = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for node in links:
        if node.get("TargetMode") != "External":
            raw = node.get("Target", "")
            target = posixpath.normpath(raw.lstrip("/") if raw.startswith("/") else "xl/" + raw)
            if not target.startswith("xl/"):
                raise ValueError("Invalid workbook relationship")
            targets[node.get("Id")] = target
    root = ET.fromstring(archive.read("xl/workbook.xml"))
    return {
        n.get("name"): targets[n.get(f"{{{REL}}}id")]
        for n in root.findall(f"{{{NS}}}sheets/{{{NS}}}sheet")
    }


def literal(node, shared):
    if node.find(f"{{{NS}}}f") is not None:
        raise ValueError("Formula cells cannot be edited")
    kind = node.get("t", "n")
    value = node.findtext(f"{{{NS}}}v")
    if kind == "s":
        return shared[int(value)]
    if kind == "inlineStr":
        return "".join(node.find(f"{{{NS}}}is").itertext())
    if kind == "b":
        return value == "1"
    if kind in ("str", "e"):
        if kind == "e":
            raise ValueError("Error cells cannot be edited")
        return value or ""
    if value is None:
        return None
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


def context(archive):
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        for entry in ET.fromstring(archive.read("xl/sharedStrings.xml")):
            shared.append("".join(n.text or "" for n in entry.iter(f"{{{NS}}}t")))
    return sheets(archive), shared


def fragments(payload):
    text = payload.decode("utf-8-sig")
    root = re.search(rf"<{TAG}worksheet\b[^>]*>", text)
    if not root:
        raise ValueError("Unsupported worksheet XML")
    namespaces = " ".join(
        re.findall(r'xmlns(?::[\w.-]+)?\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27)', root.group())
    )
    return text, namespaces


def parsed(fragment, namespaces):
    return ET.fromstring(f"<wrapper {namespaces}>{fragment}</wrapper>")[0]


def find_cell(text, namespaces, coordinate):
    for match in CELLS.finditer(text):
        node = parsed(match.group(), namespaces)
        if node.get("r") == coordinate:
            return match, node
    raise ValueError(f"Existing cell required: {coordinate}")


def inspect(path, selected):
    result = []
    with package(path) as archive:
        names, shared = context(archive)
        for name, coordinate in selected:
            text, namespaces = fragments(archive.read(names[name]))
            _, node = find_cell(text, namespaces, coordinate)
            result.append({"sheet": name, "cell": coordinate, "expected": literal(node, shared)})
    return {"source_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "changes": result}


def replacement(node, value, prefix):
    attrs = {k: v for k, v in node.attrib.items() if k != "t"}
    if any("}" in k for k in attrs):
        raise ValueError("Cells with extension attributes are unsupported")
    if isinstance(value, str):
        if len(value) > 32767 or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Invalid cell text")
        attrs["t"] = "inlineStr"
        body = (
            f'<{prefix}is><{prefix}t xml:space="preserve">{escape(value)}</{prefix}t></{prefix}is>'
        )
    elif isinstance(value, bool):
        attrs["t"] = "b"
        body = f"<{prefix}v>{int(value)}</{prefix}v>"
    elif value is None:
        body = ""
    elif isinstance(value, (int, float)):
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) > Decimal("1e15"):
            raise ValueError("Expected finite numeric value <= 1e15")
        body = f"<{prefix}v>{number}</{prefix}v>"
    else:
        raise ValueError("Cell values must be strings, numbers, booleans or null")
    attributes = " ".join(f"{key}={quoteattr(val)}" for key, val in attrs.items())
    return f"<{prefix}c {attributes}>{body}</{prefix}c>"


def same(a, b):
    # Boolean values must not compare equal to numeric 0/1.
    return (isinstance(a, bool) == isinstance(b, bool)) and a == b


def position(coordinate):
    letters, row = re.fullmatch(r"([A-Z]+)([0-9]+)", coordinate).groups()
    column = 0
    for letter in letters:
        column = column * 26 + ord(letter) - ord("A") + 1
    if column > 16384 or int(row) > 1048576:
        raise ValueError("Cell is outside Excel bounds")
    return column, int(row)


def apply(path, patch, output):
    path, output = Path(path), Path(output)
    if path.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
        raise ValueError("Only XLSX input/output supported")
    if path.resolve() == output.resolve() or output.exists():
        raise ValueError("Output must be a new, different file")
    if not isinstance(patch, dict) or set(patch) != {"source_sha256", "changes"}:
        raise ValueError("Patch requires source_sha256 and changes")
    if hashlib.sha256(path.read_bytes()).hexdigest() != patch["source_sha256"]:
        raise ValueError("Source changed: hash mismatch")
    changes = patch["changes"]
    if not isinstance(changes, list) or not 1 <= len(changes) <= 1000:
        raise ValueError("Supply 1 to 1000 cell changes")
    changed, seen, cleared = {}, set(), 0
    with package(path) as source:
        names, shared = context(source)
        for change in changes:
            if not isinstance(change, dict) or set(change) != {
                "sheet",
                "cell",
                "expected",
                "value",
            }:
                raise ValueError("Each change requires sheet, cell, expected, value")
            name, coordinate = change["sheet"], change["cell"]
            if (
                name not in names
                or not isinstance(coordinate, str)
                or not REF.fullmatch(coordinate)
            ):
                raise ValueError("Invalid sheet/cell")
            if (name, coordinate) in seen:
                raise ValueError("Duplicate cell change")
            seen.add((name, coordinate))
            member = names[name]
            text, namespaces = fragments(changed.get(member, source.read(member)))
            column, row = position(coordinate)
            for merged in ET.fromstring(source.read(member)).iter(f"{{{NS}}}mergeCell"):
                first, last = merged.get("ref").split(":")
                left, top = position(first)
                right, bottom = position(last)
                if left <= column <= right and top <= row <= bottom and coordinate != first:
                    raise ValueError("Only the anchor cell of a merged range can be edited")
            match, node = find_cell(text, namespaces, coordinate)
            if not same(literal(node, shared), change["expected"]):
                raise ValueError(f"Expected value mismatch: {name}!{coordinate}")
            if any(child.tag not in {f"{{{NS}}}v", f"{{{NS}}}is"} for child in node):
                raise ValueError("Cells with extra metadata are unsupported")
            prefix = re.match(r"<((?:[\w.-]+:)?)c", match.group()).group(1)
            changed[member] = (
                text[: match.start()]
                + replacement(node, change["value"], prefix)
                + text[match.end() :]
            ).encode("utf-8")
        # Every formula cache may depend on an edited input. Clear caches globally;
        # keep expressions and request recalculation instead of returning stale totals.
        for member in names.values():
            text, namespaces = fragments(changed.get(member, source.read(member)))

            def clear(match, namespaces=namespaces):
                nonlocal cleared
                node = parsed(match.group(), namespaces)
                if node.find(f"{{{NS}}}f") is None:
                    return match.group()
                cleared += 1
                return re.sub(rf"<{TAG}v\b[^>]*(?:/>|>.*?</{TAG}v>)", "", match.group(), flags=re.S)

            updated = CELLS.sub(clear, text).encode("utf-8")
            if updated != source.read(member):
                changed[member] = updated
        workbook = source.read("xl/workbook.xml").decode("utf-8")
        calc = re.search(rf"<{TAG}calcPr\b[^>]*(?:/>|>.*?</{TAG}calcPr>)", workbook, re.S)
        if calc:
            updated = re.sub(
                r'\s+(?:fullCalcOnLoad|forceFullCalc|calcMode)\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27)',
                "",
                calc.group(),
            )
            updated = re.sub(
                r"(/?>)",
                ' fullCalcOnLoad="1" forceFullCalc="1" calcMode="auto"' + r"\1",
                updated,
                count=1,
            )
            workbook = workbook[: calc.start()] + updated + workbook[calc.end() :]
        else:
            workbook = re.sub(
                rf"</({TAG})workbook>",
                r'<\1calcPr fullCalcOnLoad="1" forceFullCalc="1" calcMode="auto"/></\1workbook>',
                workbook,
            )
        changed["xl/workbook.xml"] = workbook.encode("utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(suffix=".xlsx", dir=output.parent)
        os.close(descriptor)
        try:
            with zipfile.ZipFile(temporary, "w") as destination:
                destination.comment = source.comment
                for info in source.infolist():
                    destination.writestr(
                        copy.copy(info), changed.get(info.filename, source.read(info.filename))
                    )
            with zipfile.ZipFile(temporary) as check:
                for name in source.namelist():
                    if check.read(name) != changed.get(name, source.read(name)):
                        raise ValueError(f"Package preservation failed: {name}")
            os.link(temporary, output)  # Atomic no-clobber publication on the same filesystem.
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {
        "output": str(output),
        "edited_cells": len(changes),
        "formula_caches_cleared": cleared,
        "changed_members": sorted(changed),
        "recalculation_required": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("inspect")
    read.add_argument("source", type=Path)
    read.add_argument("--cell", nargs=2, action="append", required=True, metavar=("SHEET", "CELL"))
    edit = commands.add_parser("apply")
    edit.add_argument("source", type=Path)
    edit.add_argument("patch", type=Path)
    edit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            inspect(args.source, args.cell)
            if args.command == "inspect"
            else apply(
                args.source, json.loads(args.patch.read_text(encoding="utf-8-sig")), args.output
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        zipfile.BadZipFile,
        ET.ParseError,
        InvalidOperation,
    ) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
