---
name: invoice-builder
description: Build a new commercial invoice, proforma invoice, customs goods-value invoice or packing list XLSX from confirmed trade data. Use for document creation, not repricing or editing an existing customer workbook.
---

# Trade documents

Use `scripts/build_invoice.py`; install `openpyxl>=3.1.5,<4` if needed. It creates a new workbook and refuses to overwrite an existing file.

## Choose the document

- `commercial`: agreed goods prices, optional freight, total.
- `proforma`: a pre-sale document using prices and terms the user has explicitly supplied.
- `customs`: description, material, use, HS code and goods subtotal. No freight or combined total. Do not infer HS codes, suppress a required trademark, or alter declared values to evade duties.
- `packing`: quantities, carton count, net/gross weight and volume. No prices. Missing measurements stay blank.

## Inputs and execution

Confirm seller, buyer, document number, date, currency and line items. Do not invent contacts, prices, measurements or delivery promises. Use the repository's `examples/invoice.json` (commercial, proforma and customs) or `examples/packing.json` as schema examples; all their contents are fictional.

```bash
python scripts/build_invoice.py input.json --kind commercial --output Commercial_Invoice_DEMO.xlsx
```

Run relative to this skill folder, or substitute the absolute script path. Each item needs `description` and positive `quantity`; invoices also need `unit_price`. Commercial/proforma items optionally carry `part_no`, `model`, `unit`; customs items carry `material`, `use`, `hs_code`. Packing items optionally carry `part_no`, `unit`, `cartons`, `net_kg`, `gross_kg`, `cbm`.

The script uses two-decimal unit prices and amounts with half-up rounding, then sums the visible line amounts. It rejects unsupported fields, including internal cost/margin/supplier fields, and stores user text as text rather than formulas.

## Check the result

Reopen the generated XLSX. Reconcile descriptions, quantities, visible prices, subtotal and total with the supplied data. Inspect the print layout for long descriptions or addresses. Check customs files have only a goods subtotal, and packing lists contain no prices. Generating a file does not authorize sending it or filing a declaration.
