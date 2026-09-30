---
name: multi-quote
description: Generate a multi-vehicle XLSX quotation with separate quality options, editable quantities, vehicle subtotals and a summary. Use when several models or quality choices must stay clear in one customer-facing quote.
---

# Multi-vehicle quote

1. Confirm the currency, seller/buyer labels, price precision and available quality choices. Do not invent a quality selection or infer costs, markup or freight.
2. Supply `quote_no`, ISO `date`, three-letter uppercase `currency`, `seller`, `buyer`, `vehicles`, optional `freight` (defaults to explicitly excluded zero) and `terms`. Each vehicle: unique valid Excel `sheet`, `model`, `items`. Each item: unique `id`, `description`, optional `part_no` / `notes`, and 1–4 `options`; each option has unique `quality`, `unit_price`, optional `quantity` (defaults to zero, unselected).
3. Run `python scripts/build_quote.py INPUT.json --output NEW.xlsx` with `openpyxl` installed.
4. Inspect each model tab and the Summary. Each quality is a separate row. A positive quantity selects that row; selecting two options orders both, so confirm the intended selection. Prices and line amounts use half-up rounding to two decimals.
5. Verify the initial cached totals. After editing quantities in Excel, let the spreadsheet application recalculate and save, then audit the actual exported workbook. Initial cached values are not a live calculation engine.

Only supplied outward-facing fields are accepted. There are no internal-price defaults. Unit prices are rounded before multiplication so displayed arithmetic agrees. Output uses a new filename. No sends or orders occur.

Repository examples: `examples/multi-quote.json`, `examples/quote-layout.json`. The sample goods subtotal is USD 135.00; freight 20.00; total 155.00. Adapt the audit mapping when rows/sheets change.
