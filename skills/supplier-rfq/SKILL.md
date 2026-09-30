---
name: supplier-rfq
description: Build an XLSX supplier request for quotation with reference images embedded beside their items, quantities and supplier response columns. Use for preparing supplier-facing RFQs from confirmed requirements.
---

# Supplier RFQ

1. Confirm the model/year, part identity, required quantity and reference-image meaning. A picture is not proof of fitment. Preserve the source description separately.
2. Prepare JSON with `rfq_no`, ISO `date`, optional `vehicle` / `instructions`, and `items` (1–200). Each item accepts `description`, `source_text`, `part_no`, positive `quantity`, optional `photo` and `notes`. Unknown fields fail.
3. Run `python scripts/build_supplier_rfq.py INPUT.json --output NEW.xlsx`. Photo paths resolve relative to the JSON file. `openpyxl` and Pillow are required.
4. Open the output, verify each image is on the correct row, and review the quantities and reference notes. Blank Quote A / Quote B / Lead Time fields are for the supplier to fill; specify the currency and quality labels in the instructions.

Pictures are converted to RGB PNG thumbnails without original EXIF/GPS metadata. This does not remove names or sensitive content visibly printed in an image: inspect the actual pixels. Text beginning with `=` remains literal text. Existing files are never overwritten. No customer-contact fields or fixed company defaults are added; review user-supplied text before sharing. The script creates a file and never contacts a supplier.

Repository example: `examples/supplier-rfq.json`. Preview: `docs/supplier-rfq-preview.png`.
