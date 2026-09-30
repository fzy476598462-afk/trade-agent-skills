---
name: freight-estimator
description: Calculate chargeable weight, volume and freight estimates from carton measurements and user-supplied carrier rates. Use for freight arithmetic and comparison, not live rate lookup, packing optimization, carrier booking or customs advice.
---

# Freight estimates

Use the standard-library script `scripts/estimate_freight.py`. Supply packed-carton measurements, never guessed dimensions inferred from a product name or part number.

```bash
python scripts/estimate_freight.py shipment.json
```

Run relative to this skill folder, or substitute the absolute script path. See `examples/freight.json` and `examples/freight-sea.json` in the repository for fictional inputs.

## Required inputs

- `rate_unit`: `kg` or `cbm`; `rate`: a positive supplied rate; `currency`: uppercase three-letter code.
- `rate_source`: identify the quote or reference used. This tool contains no live or historical rate table.
- `cartons`: one object per carton group, with `dimensions_cm: [L,W,H]`, `gross_weight_kg`, `dimensions_source` (`measured`, `supplier`, `estimate`) and optional integer `count` (identical cartons).
- For kg billing, `divisor_cm3_per_kg` must be supplied from the carrier's terms. `rounding_step_kg` defaults to 1 and applies per carton; override when the carrier differs.

## Optional carrier terms

`minimum_billable_units` is a shipment-level floor in kg or cbm. `minimum_charge` is a shipment-level monetary floor. `surcharge_percent` applies to the base after that monetary floor; `flat_surcharge` is added afterward, once per shipment. Supply a total flat surcharge yourself when fees are per carton; the script does not infer carrier rules.

`max_length_cm` and `max_length_plus_girth_cm` only flag size-limit breaches. They do not approve shipment or price oversize fees. Length plus girth is the longest side plus twice each other side.

## Interpret correctly

Missing rates and invalid dimensions fail, rather than returning a zero quote. All results remain estimates; tax, clearance, delivery and unlisted fees are excluded. Verify carrier acceptance, current rates, minima and surcharges before treating the result as a quote. This tool does not guess carton arrangements, fitment, exchange rates or transit time.
