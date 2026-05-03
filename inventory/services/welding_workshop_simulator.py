from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from inventory.services.welding_finance import clamp_percent, quantize_money, to_decimal


MATERIAL_CATEGORIES = (
    ("metal", "Metal"),
    ("wood", "Wood"),
    ("plywood", "Plywood"),
    ("leather", "Leather"),
    ("fabric", "Fabric"),
    ("paint", "Paint"),
    ("welding_rods", "Welding rods"),
    ("cutting_discs", "Cutting/grinding discs"),
    ("screws_bolts", "Screws / bolts"),
    ("labour", "Labour"),
    ("transport", "Transport"),
    ("other", "Other"),
)

UNIT_CHOICES = (
    ("piece", "Piece"),
    ("length", "Length"),
    ("sheet", "Sheet"),
    ("sqm", "Square metre"),
    ("litre", "Litre"),
    ("kg", "Kg"),
    ("packet", "Packet"),
    ("hour", "Hour"),
    ("trip", "Trip"),
    ("lot", "Lot"),
)

DEFAULT_WORKSHOP_ROWS = (
    {"category": "metal", "name": "Steel tube / angle iron", "quantity": "1", "unit": "length", "unit_cost": "", "waste_percent": "10"},
    {"category": "plywood", "name": "Board / plywood", "quantity": "1", "unit": "sheet", "unit_cost": "", "waste_percent": "8"},
    {"category": "paint", "name": "Primer / paint", "quantity": "1", "unit": "litre", "unit_cost": "", "waste_percent": "5"},
)


def _post_list(post, key: str) -> list[str]:
    if isinstance(post, dict):
        raw = dict.get(post, key, [])
        if isinstance(raw, list):
            return raw
        if raw not in (None, ""):
            return [raw]
    values = post.getlist(key)
    if isinstance(values, str):
        return [values] if values not in (None, "") else []
    if values:
        return list(values)
    value = post.get(key)
    return [value] if value not in (None, "") else []


def workshop_rows_from_post(post) -> list[dict[str, object]]:
    categories = _post_list(post, "material_category")
    names = _post_list(post, "material_name")
    quantities = _post_list(post, "quantity")
    units = _post_list(post, "unit")
    unit_costs = _post_list(post, "unit_cost")
    waste_percents = _post_list(post, "waste_percent")

    allowed_categories = {code for code, _label in MATERIAL_CATEGORIES}
    allowed_units = {code for code, _label in UNIT_CHOICES}
    row_count = max(len(categories), len(names), len(quantities), len(units), len(unit_costs), len(waste_percents))
    rows: list[dict[str, object]] = []

    for index in range(row_count):
        category = (categories[index] if index < len(categories) else "other") or "other"
        unit = (units[index] if index < len(units) else "piece") or "piece"
        name = (names[index] if index < len(names) else "").strip()
        quantity = to_decimal(quantities[index] if index < len(quantities) else "0")
        unit_cost = to_decimal(unit_costs[index] if index < len(unit_costs) else "0")
        waste_percent = clamp_percent(waste_percents[index] if index < len(waste_percents) else "0")

        if not name and quantity <= 0 and unit_cost <= 0:
            continue

        base_cost = quantize_money(quantity * unit_cost)
        waste_cost = quantize_money(base_cost * waste_percent / Decimal("100"))
        line_total = quantize_money(base_cost + waste_cost)

        rows.append(
            {
                "category": category if category in allowed_categories else "other",
                "name": name[:120] or "Material",
                "quantity": quantity,
                "unit": unit if unit in allowed_units else "piece",
                "unit_cost": quantize_money(unit_cost),
                "waste_percent": waste_percent,
                "base_cost": base_cost,
                "waste_cost": waste_cost,
                "line_total": line_total,
            }
        )

    return rows


def compute_workshop_estimate(post) -> dict[str, object]:
    rows = workshop_rows_from_post(post)
    materials_subtotal = quantize_money(sum((row["base_cost"] for row in rows), Decimal("0")))
    waste_cost = quantize_money(sum((row["waste_cost"] for row in rows), Decimal("0")))
    materials_total = quantize_money(materials_subtotal + waste_cost)

    labour_hours = to_decimal(post.get("labour_hours"), Decimal("0"))
    labour_rate = to_decimal(post.get("workshop_labour_rate"), Decimal("0"))
    labour_cost = quantize_money(labour_hours * labour_rate)
    transport_cost = quantize_money(post.get("transport_cost"))

    overhead_percent = clamp_percent(post.get("overhead_percent"), Decimal("10"))
    profit_percent = clamp_percent(post.get("profit_percent"), Decimal("25"))

    cost_before_overhead = quantize_money(materials_total + labour_cost + transport_cost)
    overhead_cost = quantize_money(cost_before_overhead * overhead_percent / Decimal("100"))
    cost_before_profit = quantize_money(cost_before_overhead + overhead_cost)
    profit_amount = quantize_money(cost_before_profit * profit_percent / Decimal("100"))
    final_estimate = quantize_money(cost_before_profit + profit_amount)

    return {
        "rows": rows,
        "materials_subtotal": materials_subtotal,
        "waste_cost": waste_cost,
        "materials_total": materials_total,
        "labour_hours": labour_hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "labour_rate": quantize_money(labour_rate),
        "labour_cost": labour_cost,
        "transport_cost": transport_cost,
        "overhead_percent": overhead_percent,
        "overhead_cost": overhead_cost,
        "profit_percent": profit_percent,
        "profit_amount": profit_amount,
        "cost_before_profit": cost_before_profit,
        "final_estimate": final_estimate,
    }
