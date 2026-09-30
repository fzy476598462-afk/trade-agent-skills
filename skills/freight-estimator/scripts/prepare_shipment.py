"""Prepare carton inputs using vehicle context and explicit packing references."""

from __future__ import annotations

import argparse
import json
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

BODY_TYPES = {
    "sedan",
    "hatchback",
    "suv",
    "mpv",
    "pickup",
    "van",
    "truck",
    "bus",
    "other",
    "unknown",
}
SIZE_CLASSES = {"compact", "medium", "large", "oversize", "unknown"}
# Operational reference bins, not official vehicle segments or packing dimensions.
SIZE_BINS_MM = (("compact", 4500, 1850), ("medium", 4900, 1950), ("large", 5500, 2100))
SIZE_SENSITIVE_PARTS = {
    "bumper_cover",
    "bumper_beam",
    "hood",
    "door",
    "fender",
    "windshield",
    "long_trim",
}
RECORD_FIELDS = {
    "id",
    "part_type",
    "oe",
    "vehicle_model",
    "platform",
    "body_type",
    "size_class",
    "units_per_carton",
    "dimensions_cm",
    "gross_weight_kg",
    "source",
}


def positive(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected a positive number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label}: invalid number") from exc
    if not number.is_finite() or not 0 < number <= Decimal("1e9"):
        raise ValueError(f"{label}: expected a finite positive number no larger than 1e9")
    return number


def integer(value, label):
    number = positive(value, label)
    if number != number.to_integral_value():
        raise ValueError(f"{label}: expected a positive integer")
    return int(number)


def normalized(value):
    if not isinstance(value, str):
        raise ValueError("Identifiers and labels must be strings")
    return value.strip().casefold()


def object_fields(value, fields, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected an object")
    if extra := set(value) - fields:
        raise ValueError(f"{label}: unsupported fields {', '.join(sorted(extra))}")


def vehicle_context(vehicle):
    object_fields(
        vehicle,
        {"model", "platform", "body_type", "size_class", "dimensions_mm", "dimensions_source"},
        "vehicle",
    )
    context = dict(vehicle)
    body = vehicle.get("body_type", "unknown")
    if body not in BODY_TYPES:
        raise ValueError("vehicle.body_type: unsupported body type")
    size = vehicle.get("size_class", "unknown")
    if size not in SIZE_CLASSES:
        raise ValueError("vehicle.size_class: unsupported size class")
    for key in ("model", "platform"):
        normalized(vehicle.get(key, ""))
    dimensions = vehicle.get("dimensions_mm")
    if dimensions is not None:
        if not isinstance(dimensions, list) or len(dimensions) != 3:
            raise ValueError("vehicle.dimensions_mm: supply [length, width, height] in mm")
        length, width, height = [positive(value, "vehicle dimension") for value in dimensions]
        source = vehicle.get("dimensions_source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("vehicle.dimensions_source: identify the dimensional evidence")
        inferred = next(
            (
                label
                for label, max_length, max_width in SIZE_BINS_MM
                if length <= max_length and width <= max_width
            ),
            "oversize",
        )
        if size != "unknown" and size != inferred:
            raise ValueError(
                "vehicle.size_class conflicts with the operational bins for supplied dimensions"
            )
        size = inferred
        context["size_basis"] = (
            "operational bins from supplied length and width; height is context only"
        )
        context["dimensions_mm"] = [str(length), str(width), str(height)]
    else:
        context["size_basis"] = "user-supplied class" if size != "unknown" else "not provided"
    context.update(body_type=body, size_class=size)
    context["classification_note"] = (
        "These bins group reference records; they are not official car segments and do not imply part or carton dimensions."
    )
    return context


def validate_record(record):
    object_fields(record, RECORD_FIELDS, "packing record")
    for field in ("id", "part_type", "source"):
        if not normalized(record.get(field, "")):
            raise ValueError(f"packing record.{field}: required")
    for field in ("oe", "vehicle_model", "platform"):
        normalized(record.get(field, ""))
    if (
        record.get("body_type", "unknown") not in BODY_TYPES
        or record.get("size_class", "unknown") not in SIZE_CLASSES
    ):
        raise ValueError("packing record: invalid body type or size class")
    integer(record.get("units_per_carton"), "units_per_carton")
    dims = record.get("dimensions_cm")
    if not isinstance(dims, list) or len(dims) != 3:
        raise ValueError("packing record: supply three carton sides in cm")
    for value in dims:
        positive(value, "carton dimension")
    positive(record.get("gross_weight_kg"), "gross_weight_kg")


def match_basis(part, record, vehicle):
    if normalized(part["part_type"]) != normalized(record["part_type"]):
        return None
    for field, record_field, label, rank in (
        ("oe", "oe", "same_oe", 100),
        ("model", "vehicle_model", "same_model", 80),
        ("platform", "platform", "same_platform", 60),
    ):
        value = part.get(field, "") if field == "oe" else vehicle.get(field, "")
        if normalized(value) and normalized(value) == normalized(record.get(record_field, "")):
            return label, rank
    if normalized(part["part_type"]) in SIZE_SENSITIVE_PARTS:
        body, size = vehicle["body_type"], vehicle["size_class"]
        if (
            body != "unknown"
            and size != "unknown"
            and body == record.get("body_type")
            and size == record.get("size_class")
        ):
            return "similar_body_and_size", 30
    return None


def prepare(data):
    object_fields(data, {"vehicle", "parts", "packing_records", "freight_terms"}, "input")
    vehicle = vehicle_context(data.get("vehicle", {}))
    parts, records = data.get("parts"), data.get("packing_records", [])
    if not isinstance(parts, list) or not parts or not isinstance(records, list):
        raise ValueError("Supply a nonempty parts list and a packing_records list")
    for record in records:
        validate_record(record)
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Packing record IDs must be unique")
    terms = data.get("freight_terms")
    if not isinstance(terms, dict) or "cartons" in terms:
        raise ValueError("freight_terms: supply rate terms without cartons")
    lines, cartons, unresolved = [], [], []
    for index, part in enumerate(parts, 1):
        object_fields(
            part, {"part_type", "oe", "quantity", "reference_id", "packed_cartons"}, "part"
        )
        if not normalized(part.get("part_type", "")):
            raise ValueError("part.part_type: required")
        normalized(part.get("oe", ""))
        quantity = integer(part.get("quantity"), "part.quantity")
        line = {"line": index, "part_type": part["part_type"], "quantity": quantity}
        if "packed_cartons" in part:
            packed = part["packed_cartons"]
            if not isinstance(packed, list) or not packed:
                raise ValueError("packed_cartons: supply nonempty packed-carton data")
            # Validate with the arithmetic tool downstream; never estimate over supplied packing.
            cartons.extend(packed)
            line.update(
                basis="supplied_packing",
                warning="Confirm packed cartons cover this complete line quantity.",
            )
            lines.append(line)
            continue
        candidates = [(record, match_basis(part, record, vehicle)) for record in records]
        candidates = sorted(
            ((record, basis) for record, basis in candidates if basis),
            key=lambda pair: pair[1][1],
            reverse=True,
        )
        line["candidates"] = [
            {"id": record["id"], "basis": basis[0], "source": record["source"]}
            for record, basis in candidates
        ]
        chosen = None
        reference_id = part.get("reference_id")
        if reference_id is not None:
            normalized(reference_id)
            chosen = next(
                ((record, basis) for record, basis in candidates if record["id"] == reference_id),
                None,
            )
            if chosen is None:
                raise ValueError("reference_id must identify a compatible packing record")
        elif candidates:
            best = [candidate for candidate in candidates if candidate[1][1] == candidates[0][1][1]]
            # Only a unique exact-OE match is automatic. Other similarities need explicit selection.
            if len(best) == 1 and best[0][1][0] == "same_oe":
                chosen = best[0]
        if chosen is None:
            line.update(
                basis="needs_data",
                warning="Supply packed measurements or explicitly select a compatible reference_id. Vehicle size alone cannot determine a carton.",
            )
            unresolved.append(index)
        else:
            record, basis = chosen
            units = integer(record["units_per_carton"], "units_per_carton")
            count = int((Decimal(quantity) / units).to_integral_value(rounding=ROUND_CEILING))
            cartons.append(
                {
                    "count": count,
                    "dimensions_cm": record["dimensions_cm"],
                    "gross_weight_kg": record["gross_weight_kg"],
                    "dimensions_source": "estimate",
                }
            )
            line.update(
                basis=basis[0],
                reference_id=record["id"],
                reference_source=record["source"],
                warning="Reference packing is an estimate for this shipment. Partial cartons use the full reference size/weight; no consolidation or nesting is inferred.",
            )
        lines.append(line)
    return {
        "status": "needs_data" if unresolved else "ready_for_estimate",
        "vehicle": vehicle,
        "lines": lines,
        "unresolved_lines": unresolved,
        "shipment": None if unresolved else {**terms, "cartons": cartons},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--output", type=Path, required=True, help="New JSON shipment input; never overwrites"
    )
    args = parser.parse_args()
    try:
        result = prepare(json.loads(args.input.read_text(encoding="utf-8-sig")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["shipment"] is None:
            parser.exit(2, "Packing data unresolved; no shipment input written.\n")
        # Sibling import keeps the installed skill self-contained.
        from estimate_freight import estimate

        estimate(result["shipment"])  # Reject invalid rates or direct carton inputs before writing.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result["shipment"], stream, ensure_ascii=False, indent=2)
    except (ValueError, OSError, TypeError, InvalidOperation) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
