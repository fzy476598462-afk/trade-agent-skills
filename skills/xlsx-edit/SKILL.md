---
name: xlsx-edit
description: Make small, hash-bound changes to existing literal XLSX cells while preserving unrelated archive members, pictures and formula expressions. Use for local quantity or text corrections without rebuilding an existing workbook.
---

# Bounded spreadsheet edits

1. Inspect the source and choose existing, nonformula cells. Structural changes (rows, merges, sheet names, drawings) require a different spreadsheet editor and its own preservation check.
2. Run `python scripts/edit_xlsx.py inspect SOURCE.xlsx --cell "Sheet Name" E6`. Repeat `--cell SHEET CELL` for more cells. This returns the source SHA-256 and current expected values.
3. Make a JSON patch with exactly `source_sha256` and a nonempty `changes` list. Each change is `{sheet,cell,expected,value}`. Keep the reported `expected` unchanged; add the intended `value` (string, number, boolean or null). A whole-cell text replacement intentionally replaces any existing rich-text runs in that cell.
4. Run `python scripts/edit_xlsx.py apply SOURCE.xlsx PATCH.json --output NEW.xlsx`. Output must be a new, different filename. Source hash, expected values, duplicate cells and unsupported cells are checked before publication.
5. Inspect the edited values and images. All formula expressions are retained, but **every worksheet formula cache is cleared** and workbook recalculation is requested, because changing an input can invalidate distant totals. Open with a spreadsheet application, recalculate and save before using formula results or running quote-audit. Never treat an empty cache as a zero total.

Only XLSX cell values are supported, without external dependencies. Signed/encrypted/duplicate-entry files and packages over 512 MiB unpacked are rejected. Unrelated ZIP-member contents are verified byte-for-byte; ZIP compression bytes may differ. A preserved image can still contain private information. The output filesystem must support hard links. There is no claim that arbitrary structural changes, macros or protected workbooks are supported.

Repository demo: generate `examples/multi-quote.json`, then use `examples/make_demo_edit.py` to create the quantity-change patch.
