---
name: quote-audit
description: Check an XLSX quotation read-only for mapped line arithmetic and totals, hidden content, unfinished labels and possible internal-cost fields. Use before sharing a quote or comparing an unchanged table layout with an earlier version.
---

# Quote audit

1. Inspect the actual workbook and define an explicit layout. No guessing column meanings. `tables` is a nonempty list of `{sheet,start_row,end_row,id,quality?,quantity,unit_price,amount}`; column values are uppercase letters. Include every intended item row and an option label column when IDs repeat for different qualities.
2. Optional `totals`: `{sheet,cell,sources}` where `sources` is a list of `[sheet,range]` pairs of numeric cells. Include goods, freight and grand-total relationships separately. Do not include subtotals twice.
3. Run `python scripts/audit_quote.py FILE.xlsx LAYOUT.json [--previous OLD.xlsx]`. Requires `openpyxl`. Previous comparison requires the same row/sheet layout and uses item ID plus quality, not only row position.
4. Exit 0 means these configured arithmetic checks passed; exit 1 means findings; exit 2 means invalid input. Inspect `errors`, `warnings`, `price_changes`, and the reported coverage. Unit prices must have no more than two decimals. Price changes are reported for review, never automatically accepted or forbidden.

Formula results need a current cache saved by a spreadsheet application. Missing caches fail; the script does not evaluate formulas or save/rewrite the workbook. Hidden sheets/rows/columns, Excel error cells, TBD/TODO labels and common internal-price words are flagged across loaded sheets. External/structured formulas produce warnings. This is not a complete personal-information detector: inspect comments, embedded images, document properties and all customer-facing content manually. A pass does not verify fitment, agreed prices or shipping terms.

Repository example: `examples/quote-layout.json` matches the unchanged output of `examples/multi-quote.json`.
