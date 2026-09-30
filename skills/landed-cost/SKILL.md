---
name: landed-cost
description: Compare user-supplied door-to-door offers in a common currency without treating missing fees as zero. Use for comparing complete costs for the same goods, quantity, quality and delivery point.
---

# Door-to-door cost comparison

1. Establish a common goods/quantity/quality/destination/tax basis. If offers differ, normalize them using confirmed information before running the comparison. The script cannot verify that their scope is equivalent.
2. JSON has exactly `target_currency`, `comparison_scope` (`goods`, positive `quantity`, `delivery_point`) and `offers` (2–50). Each offer supplies unique `name`, `currency`, `source`, `costs`; foreign-currency offers also need positive `fx_to_target` (target-currency units per source-currency unit) and `fx_source`.
3. Every offer's `costs` must explicitly account for `goods`, `freight`, `insurance`, `duty`, `tax`, `clearance`, `delivery`, `other`. Use zero only for a confirmed excluded/not-applicable charge, accounting for any bundled costs once. Null or omitted means unknown. An inclusive freight figure must not have its included delivery fee added twice.
4. Run `python scripts/compare_costs.py INPUT.json`. Exit 0: all complete; 1: missing data; 2: invalid input. If any offer is incomplete, no lowest-cost winner is returned. Complete totals are converted and half-up rounded to two decimals; exact ties are retained.

Sources and exchange rates are supplied by the caller. No live carrier, duty, tax, currency or customs lookup occurs. This is cost arithmetic, not a landed-cost quotation or tax advice. Review fees and the stated scope before making a commercial decision.

Repository sample: `examples/landed-cost.json` compares fictional totals USD 145.00 and 154.00.
