---
name: freight-estimator
description: Estimate auto-parts freight from confirmed cartons or explicit packing references, using vehicle body type, size and part category to rank references. Calculate kg or CBM billing with supplied carrier terms. Use for freight arithmetic and packing-data preparation, not live rates or carrier booking.
---

# Freight estimates

Use the standard-library script `scripts/estimate_freight.py` for confirmed carton measurements. Use `scripts/prepare_shipment.py` when you have vehicle/part context and explicit packing references; do not invent reference dimensions from a product name.

## Before arithmetic: vehicle and packing evidence

Separate `body_type` (sedan, hatchback, suv, mpv, pickup, van, truck, bus, other, unknown) from `size_class` (compact, medium, large, oversize, unknown). Confirm exact model/year/variant and dimensional evidence when relevant; the script does not retrieve vehicle specifications or infer compatibility.

The preparation script can group supplied overall vehicle dimensions `[length,width,height]` in **mm**: compact up to 4500×1850, medium up to 4900×1950, large up to 5500×2100, otherwise oversize (length and width both must fit). Height remains context. These are explicit operational reference bins, not official market segments, legal limits or carton measurements. Without dimensions, a supplied size class is an assumption; do not present it as independently verified.

Evidence order: supplied packed cartons > unique exact-OE packing record > explicitly selected same-model/platform record > explicitly selected similar body/size record for size-sensitive parts. Similar body/size applies only to bumper covers/beams, hoods, doors, fenders, windshields and long trim. Small sensors and other small parts do not automatically become larger because the vehicle is an SUV.

Records must specify source, part type, units per carton, carton sides in **cm** and gross kg. A unique exact-OE reference can be selected automatically; model/platform/similarity matches and ambiguous records require `reference_id`. Every reused record remains an **estimate** for the new shipment. Partial cartons retain full reference dimensions/weight as a conservative assumption. Consolidation, folding, stacking and nesting are not inferred.

```bash
python scripts/prepare_shipment.py vehicle-input.json --output shipment.json
python scripts/estimate_freight.py shipment.json
```

See `examples/vehicle-shipment.json` in the repository; it is entirely fictional. Preparation reports candidates, selected sources and unresolved lines. If any line lacks packing evidence, it exits with code 2 and writes no shipment file. Do not silently omit unresolved goods or turn missing evidence into zero freight.

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
