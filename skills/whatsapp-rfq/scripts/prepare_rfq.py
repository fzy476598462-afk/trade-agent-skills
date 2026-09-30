"""Validate WhatsApp MCP receipts and package reviewed RFQ lines without contacting anyone."""

import argparse
import hashlib
import json
import re
import shutil
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

MESSAGE_START = re.compile(r"(?m)^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]")
MEDIA = re.compile(r"\[([^\]\n]+) - Message ID: ([^\]\n]+) - Chat JID: ([^\]\n]+)\]")
CONTACT = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\S+@(?:lid|s\.whatsapp\.net|g\.us)|\+\d[\d ()-]{8,}\d"
)
MONEY = re.compile(r"[$€£¥￥]\s*\d|\b(?:USD|EUR|CNY)\s*\d", re.IGNORECASE)
EMPTY = "No messages to display."


def fields(data, allowed, label):
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError(f"{label}: invalid object or unsupported fields")


def text(value, label, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{label}: expected {'nonempty ' if required else ''}text")
    return value.strip()


def shared_text(value, label, required=False):
    result = text(value, label, required)
    if CONTACT.search(result) or MONEY.search(result):
        raise ValueError(f"{label}: remove contact details or monetary amounts before sharing")
    return result


def payload(value):
    """Accept direct tool returns and standard MCP text/structured-result envelopes."""
    if isinstance(value, dict):
        if value.get("isError"):
            raise ValueError("MCP tool returned an error")
        if "structuredContent" in value and value["structuredContent"] is not None:
            value = value["structuredContent"]
        elif "content" in value:
            blocks = value["content"]
            if (
                not isinstance(blocks, list)
                or not blocks
                or any(not isinstance(b, dict) or b.get("type") != "text" for b in blocks)
            ):
                raise ValueError("Unsupported MCP content: preserve a readable tool result")
            value = "\n".join(text(b.get("text"), "MCP text") for b in blocks)
    if isinstance(value, dict) and set(value) == {"result"}:
        value = value["result"]
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def page_text(value, chat_jid):
    value = payload(value)
    if isinstance(value, str):
        if value.strip() == EMPTY:
            return "", 0
        count = len(MESSAGE_START.findall(value))
        if not count:
            raise ValueError(
                "Unrecognized message page; errors or blank text are not empty history"
            )
        return value, count
    if isinstance(value, list):
        for message in value:
            if not isinstance(message, dict) or message.get("chat_jid") != chat_jid:
                raise ValueError("Structured message belongs to another chat or lacks chat_jid")
        return (json.dumps(value, ensure_ascii=False) if value else ""), len(value)
    raise ValueError("Unsupported message result; cannot establish pagination coverage")


def citation(value, pages):
    fields(value, {"page", "quote"}, "evidence")
    page, quote = value.get("page"), text(value.get("quote"), "evidence quote", True)
    if isinstance(page, bool) or not isinstance(page, int) or page not in pages:
        raise ValueError("Evidence references an unknown page")
    if quote not in pages[page]:
        raise ValueError("Evidence quote is absent from its message page")
    return {"page": page, "quote": quote}


def quantity(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Ready line needs an explicit positive quantity; do not default to 1")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid quantity") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("Quantity must be finite and positive")
    return str(number)


def validate(data, input_root):
    fields(
        data,
        {"rfq_no", "date", "vehicle", "instructions", "scope", "pages", "downloads", "items"},
        "packet",
    )
    header = {
        "rfq_no": shared_text(data.get("rfq_no"), "rfq_no", True),
        "date": text(data.get("date"), "date", True),
        "vehicle": shared_text(data.get("vehicle", ""), "vehicle"),
        "instructions": shared_text(data.get("instructions", ""), "instructions"),
    }
    date.fromisoformat(header["date"])
    scope = data.get("scope")
    fields(scope, {"chat_jid", "after", "before", "limit"}, "scope")
    chat = text(scope.get("chat_jid"), "chat_jid", True)
    after = datetime.fromisoformat(text(scope.get("after"), "after", True))
    before = datetime.fromisoformat(text(scope.get("before"), "before", True))
    try:
        ordered = after < before
    except TypeError as exc:
        raise ValueError("after/before must use the same timezone convention") from exc
    limit = scope.get("limit")
    if (
        not ordered
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 200
    ):
        raise ValueError("Invalid time window or page limit (1–200)")
    receipts = data.get("pages")
    if not isinstance(receipts, list) or not 1 <= len(receipts) <= 20:
        raise ValueError("Expected 1–20 message pages, including a terminal empty page")
    pages, media, hashes, empty = {}, {}, set(), False
    for index, receipt in enumerate(receipts):
        fields(receipt, {"tool", "arguments", "result"}, "message receipt")
        expected = {**scope, "page": index, "include_context": False}
        if receipt.get("tool") != "list_messages" or receipt.get("arguments") != expected:
            raise ValueError(
                "Message receipts must cover consecutive pages of exactly the selected scope"
            )
        body, count = page_text(receipt.get("result"), chat)
        if empty or count > limit:
            raise ValueError("Unexpected page after terminal empty page or oversized result")
        empty = count == 0
        if not empty:
            digest = hashlib.sha256(body.encode()).hexdigest()
            if digest in hashes:
                raise ValueError("Repeated page; do not claim complete pagination")
            hashes.add(digest)
        pages[index] = body
        for kind, message_id, media_chat in MEDIA.findall(body):
            if media_chat.strip() != chat:
                raise ValueError("Media marker belongs to another chat")
            media.setdefault(message_id.strip(), kind.strip())
        raw = payload(receipt.get("result"))
        if isinstance(raw, list):
            for message in raw:
                if message.get("media_type"):
                    message_id = text(message.get("id"), "media message id", True)
                    media[message_id] = text(message["media_type"], "media type", True)
    if not empty:
        raise ValueError("History is truncated: fetch the next page until an explicit empty result")
    downloads = data.get("downloads", [])
    if not isinstance(downloads, list):
        raise ValueError("downloads must be a list")
    files, failures = {}, []
    for receipt in downloads:
        fields(receipt, {"tool", "arguments", "result"}, "download receipt")
        args = receipt.get("arguments")
        fields(args, {"message_id", "chat_jid"}, "download arguments")
        message_id = args.get("message_id")
        if (
            receipt.get("tool") != "download_media"
            or args.get("chat_jid") != chat
            or message_id not in media
        ):
            raise ValueError("Download is not linked to media in the selected chat window")
        if message_id in files or any(f["message_id"] == message_id for f in failures):
            raise ValueError("Duplicate download receipt")
        result = payload(receipt.get("result"))
        if not isinstance(result, dict) or result.get("success") is not True:
            failures.append(
                {
                    "message_id": message_id,
                    "reason": "Download failed; inspect the original receipt",
                }
            )
            continue
        path = Path(text(result.get("file_path"), "download path", True))
        path = (input_root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file():
            raise ValueError("Downloaded attachment is missing")
        files[message_id] = path
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 200:
        raise ValueError("Expected 1–200 reviewed demand lines")
    ready, pending, withdrawn = [], [], []
    for index, item in enumerate(raw_items, 1):
        fields(
            item,
            {
                "description",
                "part_no",
                "quantity",
                "quantity_evidence",
                "photo_message_id",
                "photo_verified",
                "notes",
                "state",
                "missing",
                "reason",
                "evidence",
            },
            "demand line",
        )
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Every demand line needs original-message evidence")
        checked = [citation(ref, pages) for ref in evidence]
        state = item.get("state")
        if state not in {"ready", "pending", "withdrawn"}:
            raise ValueError("Demand state must be explicit: ready, pending, withdrawn")
        description = text(item.get("description"), "description", True)
        if state == "withdrawn":
            withdrawn.append(
                {
                    "line": index,
                    "description": description,
                    "reason": text(item.get("reason"), "withdrawal reason", True),
                    "evidence": checked,
                }
            )
            continue
        if state == "pending":
            missing = item.get("missing")
            if not isinstance(missing, list) or not missing:
                raise ValueError("Pending line needs specific missing information")
            pending.append(
                {
                    "line": index,
                    "description": description,
                    "missing": [text(m, "missing field", True) for m in missing],
                    "evidence": checked,
                }
            )
            continue
        citation(item.get("quantity_evidence"), pages)
        row = {
            "description": shared_text(description, "description", True),
            "part_no": shared_text(item.get("part_no", ""), "part_no"),
            "quantity": quantity(item.get("quantity")),
            "notes": shared_text(item.get("notes", ""), "notes"),
        }
        photo = item.get("photo_message_id")
        if photo:
            if not isinstance(photo, str) or photo not in files or media[photo] != "image":
                raise ValueError("Ready reference image lacks a successful matching image download")
            if item.get("photo_verified") is not True:
                raise ValueError(
                    "Inspect and match the reference image before marking the line ready"
                )
            row["photo_message_id"] = photo
        ready.append(row)
    return header, ready, pending, withdrawn, files, failures


def prepare(data, output, input_root=Path(".")):
    header, ready, pending, withdrawn, files, failures = validate(data, Path(input_root))
    output = Path(output)
    if output.exists():
        raise FileExistsError("Output directory already exists; choose a new packet directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    copied = {}
    if files:
        (output / "media").mkdir()
    for index, (message_id, path) in enumerate(files.items(), 1):
        suffix = path.suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        relative = f"media/attachment-{index:03d}{suffix}"
        target = output / relative
        with path.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        copied[message_id] = {
            "path": relative,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    private = {
        "scope": data["scope"],
        "pages": data["pages"],
        "reviewed_items": data["items"],
        "attachments": copied,
        "download_failures": failures,
    }
    summary = {"pending": pending, "withdrawn": withdrawn, "download_failures": failures}
    contents = {"private-evidence.json": private, "pending.json": summary}
    if ready:
        for row in ready:
            message_id = row.pop("photo_message_id", None)
            if message_id:
                row["photo"] = copied[message_id]["path"]
        contents["supplier-rfq.json"] = {**header, "items": ready}
    for name, value in contents.items():
        with (output / name).open("x", encoding="utf-8") as destination:
            json.dump(value, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
    return {
        "output": str(output),
        "ready": len(ready),
        "pending": len(pending),
        "withdrawn": len(withdrawn),
        "download_failures": len(failures),
        "supplier_input": str(output / "supplier-rfq.json") if ready else None,
        "sent": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        result = prepare(data, args.output, args.input.parent)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
