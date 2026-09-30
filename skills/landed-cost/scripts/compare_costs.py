"""Compare complete, user-supplied door-to-door costs in one target currency."""

from __future__ import annotations

import argparse
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

COMPONENTS = ("goods", "freight", "insurance", "duty", "tax", "clearance", "delivery", "other")


def number(value, label, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}: expected number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label}: invalid number") from exc
    if not result.is_finite() or not 0 <= result <= Decimal("1e12") or positive and not result:
        raise ValueError(
            f"{label}: expected finite {'positive' if positive else 'nonnegative'} number <= 1e12"
        )
    return result


def currency(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("Currency must be an uppercase three-letter code")
    return value


def compare(data):
    if not isinstance(data, dict) or set(data) != {"target_currency", "comparison_scope", "offers"}:
        raise ValueError("Supply target_currency, comparison_scope and offers")
    target = currency(data["target_currency"])
    scope = data["comparison_scope"]
    if not isinstance(scope, dict) or set(scope) != {"goods", "quantity", "delivery_point"}:
        raise ValueError("comparison_scope requires common goods, quantity and delivery_point")
    if any(
        not isinstance(scope[field], str) or not scope[field].strip()
        for field in ("goods", "delivery_point")
    ):
        raise ValueError("Identify the common goods and delivery point")
    number(scope["quantity"], "scope.quantity", True)
    offers = data["offers"]
    if not isinstance(offers, list) or not 2 <= len(offers) <= 50:
        raise ValueError("Supply 2 to 50 comparable offers")
    results, names = [], set()
    for offer in offers:
        if not isinstance(offer, dict) or set(offer) - {
            "name",
            "currency",
            "source",
            "costs",
            "fx_to_target",
            "fx_source",
        }:
            raise ValueError("Invalid offer fields")
        name, source = offer.get("name"), offer.get("source")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Offer names must be nonempty and unique")
        names.add(name)
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Offer source required")
        original = currency(offer.get("currency"))
        costs = offer.get("costs")
        if not isinstance(costs, dict) or set(costs) - set(COMPONENTS):
            raise ValueError("Unsupported cost fields")
        missing = [field for field in COMPONENTS if field not in costs or costs[field] is None]
        amounts = {
            field: number(value, field) for field, value in costs.items() if value is not None
        }
        fx = Decimal(1)
        if original != target:
            if offer.get("fx_to_target") is None:
                missing.append("fx_to_target")
            else:
                fx = number(offer["fx_to_target"], "fx_to_target", True)
                if not isinstance(offer.get("fx_source"), str) or not offer["fx_source"].strip():
                    raise ValueError("fx_source required for a supplied conversion")
        elif "fx_to_target" in offer and number(offer["fx_to_target"], "fx_to_target", True) != 1:
            raise ValueError("Same-currency fx_to_target must be 1")
        total = (sum(amounts.values(), Decimal(0)) * fx).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        results.append(
            {
                "name": name,
                "source": source,
                "status": "needs_data" if missing else "complete",
                "missing": missing,
                "currency": original,
                "fx_to_target": str(fx) if "fx_to_target" not in missing else None,
                "total_target": None if missing else str(total),
            }
        )
    complete = all(offer["status"] == "complete" for offer in results)
    ranking = sorted(results, key=lambda item: Decimal(item["total_target"])) if complete else []
    lowest = Decimal(ranking[0]["total_target"]) if ranking else None
    return {
        "comparison_scope": scope,
        "target_currency": target,
        "complete": complete,
        "offers": results,
        "lowest_cost_offers": [
            item["name"] for item in ranking if Decimal(item["total_target"]) == lowest
        ],
        "note": "User-supplied costs only. All offers must cover the same quantity, destination, quality and tax treatment. Enter explicit zero for known excluded/not-applicable fees; unknown is not zero. No duty, tax or FX lookup.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.input.read_text(encoding="utf-8-sig")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["complete"]:
            parser.exit(1)
    except (ValueError, TypeError, OSError, InvalidOperation) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
