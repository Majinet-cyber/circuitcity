# inventory/helpers_liquor_units.py
"""
SSOT helper for liquor unit pricing calculations.
Handles per-bottle, per-shot, per-glass conversions for different liquor categories.

ARCHITECTURE CONTRACT (DO NOT CHANGE without updating ALL callers):
  - Beer/Cider: quantity_in_stock is stored in BOTTLES
  - Spirits/Whisky: quantity_in_stock is stored in SHOTS (base units)
  - Wine: quantity_in_stock is stored in GLASSES (base units)

This means max_quantity = quantity_in_stock directly for all categories —
no multiplication needed, the base conversion already happened at stock-in time.
"""
from decimal import Decimal
from typing import Dict, Optional


def get_liquor_unit_info(product) -> Dict:
    """
    Get unit pricing information for a liquor product.

    Args:
        product: MerchProduct instance (liquor)

    Returns:
        dict with keys:
            - sale_unit: "bottle" or "shot" or "glass"
            - units_per_item: int (shots/glasses per bottle, 1 for bottles)
            - unit_price: Decimal (price per selling unit)
            - unit_cost: Decimal (cost per selling unit)
            - max_quantity: int (available stock in selling units, matching quantity_in_stock units)
            - label: str (human-readable label for UI)
    """
    category = (product.category or "").lower()

    # Default values
    sale_unit = "bottle"
    units_per_item = 1
    unit_price = Decimal("0.00")
    unit_cost = Decimal("0.00")
    # quantity_in_stock IS the available stock in base units — do not multiply
    available_stock = product.quantity_in_stock or 0

    # Beer & Cider: quantity_in_stock = BOTTLES
    if category in ["beer", "cider"]:
        sale_unit = "bottle"
        units_per_crate = product.bottles_per_crate or 20

        if product.price_per_bottle:
            unit_price = product.price_per_bottle
        elif product.selling_price and units_per_crate:
            unit_price = product.selling_price / Decimal(str(units_per_crate))

        if product.cost_per_bottle:
            unit_cost = product.cost_per_bottle
        elif product.cost_price and units_per_crate:
            unit_cost = product.cost_price / Decimal(str(units_per_crate))

        # quantity_in_stock IS bottles — use directly
        max_quantity = available_stock
        units_per_item = units_per_crate
        label = "Bottles"

    # Spirits & Whiskey: quantity_in_stock = SHOTS
    elif category in ["spirits", "whiskey"]:
        sale_unit = "shot"
        shots_per_bottle = product.sellable_shots_per_bottle or 23
        units_per_item = shots_per_bottle

        if product.price_per_shot:
            unit_price = product.price_per_shot
        elif product.price_per_bottle and shots_per_bottle > 0:
            unit_price = product.price_per_bottle / Decimal(str(shots_per_bottle))

        if product.cost_per_shot:
            unit_cost = product.cost_per_shot
        elif product.cost_per_bottle and shots_per_bottle > 0:
            unit_cost = product.cost_per_bottle / Decimal(str(shots_per_bottle))

        # quantity_in_stock IS shots — use directly (NOT * shots_per_bottle)
        max_quantity = available_stock
        label = "Shots"

    # Wine: quantity_in_stock = GLASSES
    elif category == "wine":
        sale_unit = "glass"
        glasses_per_bottle = product.glasses_per_bottle or 5
        units_per_item = glasses_per_bottle

        if product.price_per_glass:
            unit_price = product.price_per_glass
        elif product.price_per_bottle and glasses_per_bottle > 0:
            unit_price = product.price_per_bottle / Decimal(str(glasses_per_bottle))

        if product.cost_per_glass:
            unit_cost = product.cost_per_glass
        elif product.cost_per_bottle and glasses_per_bottle > 0:
            unit_cost = product.cost_per_bottle / Decimal(str(glasses_per_bottle))

        # quantity_in_stock IS glasses — use directly (NOT * glasses_per_bottle)
        max_quantity = available_stock
        label = "Glasses"

    # Other categories: default to bottle
    else:
        sale_unit = "bottle"
        units_per_item = 1

        if product.price_per_bottle:
            unit_price = product.price_per_bottle
        elif product.selling_price:
            unit_price = product.selling_price

        if product.cost_per_bottle:
            unit_cost = product.cost_per_bottle
        elif product.cost_price:
            unit_cost = product.cost_price

        max_quantity = available_stock
        label = "Bottles"

    return {
        "sale_unit": sale_unit,
        "units_per_item": units_per_item,
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "max_quantity": max_quantity,
        "label": label,
        "category": category,
    }


def get_bottle_breakdown(product) -> Dict:
    """
    Compute bottle-level display breakdown for spirits/whisky and wine.

    For spirits/whisky: quantity_in_stock is in SHOTS.
    For wine: quantity_in_stock is in GLASSES.

    Returns dict with display-ready breakdown:
        - full_bottles: int
        - partial_units: int (shots or glasses in the open bottle)
        - units_per_bottle: int
        - total_units: int
        - has_open_bottle: bool
        - unit_label: str ("shots" or "glasses")
        - display_text: str  e.g. "4 full bottles + 1 open bottle (29/30 shots left)"
    """
    qty = product.quantity_in_stock or 0
    category = (product.category or "").lower()

    if category in ("spirits", "whiskey") and product.has_shots and product.shots_per_bottle:
        spb = product.shots_per_bottle
        full_bottles = qty // spb
        partial_units = qty % spb
        has_open = partial_units > 0
        unit_label = "shot"

        if has_open:
            display = (
                f"{full_bottles} full bottle{'s' if full_bottles != 1 else ''} "
                f"+ 1 open bottle ({partial_units}/{spb} shots left)"
            )
        else:
            display = f"{full_bottles} full bottle{'s' if full_bottles != 1 else ''}"

        return {
            "full_bottles": full_bottles,
            "partial_units": partial_units,
            "units_per_bottle": spb,
            "total_units": qty,
            "has_open_bottle": has_open,
            "unit_label": unit_label,
            "display_text": display,
            "total_label": f"{qty} shot{'s' if qty != 1 else ''} remaining",
        }

    elif category == "wine" and product.has_glasses and product.glasses_per_bottle:
        gpb = product.glasses_per_bottle
        full_bottles = qty // gpb
        partial_units = qty % gpb
        has_open = partial_units > 0
        unit_label = "glass"

        if has_open:
            display = (
                f"{full_bottles} full bottle{'s' if full_bottles != 1 else ''} "
                f"+ 1 open bottle ({partial_units}/{gpb} glasses left)"
            )
        else:
            display = f"{full_bottles} full bottle{'s' if full_bottles != 1 else ''}"

        return {
            "full_bottles": full_bottles,
            "partial_units": partial_units,
            "units_per_bottle": gpb,
            "total_units": qty,
            "has_open_bottle": has_open,
            "unit_label": unit_label,
            "display_text": display,
            "total_label": f"{qty} glass{'es' if qty != 1 else ''} remaining",
        }

    # Beer / cider / other: stock in bottles, simple display
    return {
        "full_bottles": qty,
        "partial_units": 0,
        "units_per_bottle": 1,
        "total_units": qty,
        "has_open_bottle": False,
        "unit_label": "bottle",
        "display_text": f"{qty} bottle{'s' if qty != 1 else ''}",
        "total_label": f"{qty} bottle{'s' if qty != 1 else ''} remaining",
    }


def compute_sale_totals(product, quantity: int, unit_price: Optional[Decimal] = None) -> Dict:
    """
    Compute sale totals for a liquor product.

    Args:
        product: MerchProduct instance
        quantity: Number of units to sell
        unit_price: Optional override price (if None, uses default from product)

    Returns:
        dict with keys:
            - unit_price: Decimal
            - unit_cost: Decimal
            - total: Decimal (quantity * unit_price)
            - total_cost: Decimal (quantity * unit_cost)
            - profit: Decimal (total - total_cost)
            - margin: Decimal (profit / total * 100, or 0 if total is 0)
    """
    unit_info = get_liquor_unit_info(product)

    if unit_price is None:
        unit_price = unit_info["unit_price"]

    unit_cost = unit_info["unit_cost"]

    total = Decimal(str(quantity)) * unit_price
    total_cost = Decimal(str(quantity)) * unit_cost
    profit = total - total_cost

    if total > 0:
        margin = (profit / total) * Decimal("100.00")
    else:
        margin = Decimal("0.00")

    return {
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "total": total,
        "total_cost": total_cost,
        "profit": profit,
        "margin": margin,
    }
