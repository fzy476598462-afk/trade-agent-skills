"""Estimate freight from explicit carton measurements and supplied carrier rates."""

from __future__ import annotations

import argparse
import json
import re
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, DecimalException, InvalidOperation
from pathlib import Path


def number(value: object, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name}: expected a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name}: invalid number") from exc
    if not result.is_finite() or result < 0 or (positive and not result):
        raise ValueError(f"{name}: must be finite and {'positive' if positive else 'nonnegative'}")
    if result > Decimal("1e9") or (result and result < Decimal("1e-9")):
        raise ValueError(f"{name}: value is outside the supported range (1e-9 to 1e9, or zero)")
    return result


def estimate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Input must be an object")
    allowed = {
        "rate_unit",
        "currency",
        "rate",
        "rate_source",
        "divisor_cm3_per_kg",
        "rounding_step_kg",
        "cartons",
        "minimum_billable_units",
        "minimum_charge",
        "flat_surcharge",
        "surcharge_percent",
        "max_length_cm",
        "max_length_plus_girth_cm",
    }
    if extra := set(data) - allowed:
        raise ValueError(f"Unsupported shipment fields: {', '.join(sorted(extra))}")
    method = data.get("rate_unit")
    if method not in {"kg", "cbm"}:
        raise ValueError("rate_unit: choose kg or cbm")
    currency = data.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency: supply a three-letter uppercase code")
    source = data.get("rate_source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("rate_source: identify where the supplied rate came from")
    rate = number(data.get("rate"), "rate", positive=True)
    divisor = (
        number(data.get("divisor_cm3_per_kg"), "divisor_cm3_per_kg", positive=True)
        if method == "kg"
        else None
    )
    step = number(data.get("rounding_step_kg", 1), "rounding_step_kg", positive=True)
    raw_cartons = data.get("cartons")
    if not isinstance(raw_cartons, list) or not raw_cartons:
        raise ValueError(
            "cartons: supply at least one carton; dimensions are cm, gross weight is kg"
        )
    cartons = []
    actual = Decimal(0)
    volume = Decimal(0)
    chargeable = Decimal(0)
    warnings = []
    for index, carton in enumerate(raw_cartons, 1):
        if not isinstance(carton, dict):
            raise ValueError(f"cartons[{index}]: expected an object")
        if extra := set(carton) - {
            "count",
            "dimensions_cm",
            "gross_weight_kg",
            "dimensions_source",
        }:
            raise ValueError(f"Unsupported carton fields: {', '.join(sorted(extra))}")
        count = number(carton.get("count", 1), "carton.count", positive=True)
        if count != count.to_integral_value():
            raise ValueError("carton.count must be an integer")
        dims = carton.get("dimensions_cm")
        if not isinstance(dims, list) or len(dims) != 3:
            raise ValueError(f"cartons[{index}].dimensions_cm: supply exactly three sides in cm")
        sides = [number(side, "carton.dimension", positive=True) for side in dims]
        weight = number(carton.get("gross_weight_kg"), "carton.gross_weight_kg", positive=True)
        evidence = carton.get("dimensions_source")
        if evidence not in {"measured", "supplier", "estimate"}:
            raise ValueError("dimensions_source: use measured, supplier, or estimate")
        if evidence == "estimate":
            warnings.append(
                f"Carton group {index}: dimensions/weight are estimated; confirm after packing."
            )
        cbm = sides[0] * sides[1] * sides[2] / Decimal(1000000)
        volumetric = sides[0] * sides[1] * sides[2] / divisor if divisor else Decimal(0)
        billed = (
            (max(weight, volumetric) / step).to_integral_value(rounding=ROUND_CEILING) * step
            if divisor
            else Decimal(0)
        )
        length, width, height = sorted(sides, reverse=True)
        girth = length + 2 * (width + height)
        for key, measured in (("max_length_cm", length), ("max_length_plus_girth_cm", girth)):
            if key in data and measured > number(data[key], key, positive=True):
                warnings.append(
                    f"Carton group {index}: exceeds supplied {key}; confirm acceptance and extra fees."
                )
        actual += weight * count
        volume += cbm * count
        chargeable += billed * count
        cartons.append(
            {
                "count": int(count),
                "actual_kg_per_carton": str(weight),
                "cbm_per_carton": str(cbm),
                "volumetric_kg_per_carton": str(volumetric) if divisor else None,
                "chargeable_kg_per_carton": str(billed) if divisor else None,
            }
        )
    minimum = number(data.get("minimum_billable_units", 0), "minimum_billable_units")
    billable = max(chargeable if method == "kg" else volume, minimum)
    base = billable * rate
    minimum_charge = number(data.get("minimum_charge", 0), "minimum_charge")
    base = max(base, minimum_charge)
    surcharge = number(data.get("flat_surcharge", 0), "flat_surcharge")
    surcharge_percent = number(data.get("surcharge_percent", 0), "surcharge_percent")
    total = (base * (1 + surcharge_percent / 100) + surcharge).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    warnings.append(
        "Estimate only. Taxes, customs clearance, delivery and other fees are excluded unless explicitly included in the supplied rate/surcharges."
    )
    return {
        "status": "estimate",
        "currency": currency,
        "rate_unit": method,
        "rate_source": source.strip(),
        "rate": str(rate),
        "divisor_cm3_per_kg": str(divisor) if divisor else None,
        "rounding_step_kg": str(step) if divisor else None,
        "total_actual_kg": str(actual),
        "total_cbm": str(volume),
        "total_chargeable_kg": str(chargeable) if method == "kg" else None,
        "billable_units": str(billable),
        "base_charge": str(base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total": str(total),
        "cartons": cartons,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        result = estimate(json.loads(args.input.read_text(encoding="utf-8-sig")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, TypeError, OSError, DecimalException) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
