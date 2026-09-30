---
name: translate-rfq
description: Translate text in an XLSX RFQ into a new workbook while preserving images, formulas, sheets, styles and other untouched archive parts. Use for customer workbooks with embedded images; translation is supplied by the agent or user, not an API.
---

# Preserve the RFQ workbook

Use the standard-library `scripts/translate_xlsx.py`. It edits only shared-string and inline-string XML text nodes, including rich-text runs. Every other archive member is verified byte-for-byte after writing. Do not round-trip the source through a spreadsheet library merely to translate it.

```bash
python scripts/translate_xlsx.py extract source.xlsx translations.json
# Fill empty values in translations.json using the requested target language.
python scripts/translate_xlsx.py apply source.xlsx translations.json translated.xlsx
```

Run relative to this skill folder, or substitute the absolute script path. `extract --glossary glossary.json` optionally fills exact matches; a small ES-to-ZH demonstration glossary is supplied in `assets/es-zh-demo.json`. It is a sample, not a comprehensive parts dictionary.

## Translation boundaries

Preserve identifiers, VINs, part numbers, brands, models, dates and numeric values. Codes containing digits are mechanically protected; names without digits require agent review. Do not add fitment, position, assembly type or quality claims absent from the source. Rich-text runs are extracted separately, so review the combined phrase in the original cell before translating them.

Empty translations keep the original visible text. They are reported as `unfilled`; review them before claiming a complete translation. Translation is model/user work; the script only extracts and applies supplied strings and makes no network calls.

## Verification and limits

The map is bound to the source file's SHA-256. If the source changes, extract a new map. Source and destination must differ, and outputs must not already exist. XML special characters are escaped; invalid XML characters fail before publication.

Check the reported `changed_members`, `untouched_members_identical`, `images_preserved` and `unfilled`. Then open the resulting workbook and inspect representative cells, combined rich-text phrases and images. This verifies unchanged archive-member contents, not a byte-identical ZIP container.

XLSX only; encrypted, signed and duplicate-member archives are rejected. The unpacked-size limit is 512 MiB. Text in images, comments, drawings, formula results or chart labels is not translated. Publishing uses a same-directory hard link; the destination filesystem must support hard links. No source file is modified.
