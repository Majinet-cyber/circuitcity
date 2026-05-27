# inventory/services/pricing_suggestions.py
"""
Smart pricing suggestions for cement and other verticals.
Calculates recommended selling prices based on cost, margins, and rounding.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional


def calculate_suggested_price(
    cost_price: Decimal,
    target_margin_pct: Decimal = Decimal("15"),
    competitor_price: Optional[Decimal] = None,
    rounding: int = 50,
) -> Dict[str, Decimal]:
    """
    Calculate suggested selling price based on cost and target margin.

    Args:
        cost_price: Cost per unit (buying price)
        target_margin_pct: Target profit margin percentage (default 15%)
        competitor_price: Optional competitor price for reference
        rounding: Round to nearest X (default 50 MWK for nice pricing)

    Returns:
        Dict with:
            - suggested_price: Recommended selling price (rounded)
            - margin_amount: Profit per unit
            - margin_pct: Actual margin percentage
            - competitor_diff: Difference from competitor (if provided)

    Examples:
        >>> calculate_suggested_price(Decimal("10000"), Decimal("15"))
        {'suggested_price': Decimal('11500'), 'margin_amount': Decimal('1500'), 'margin_pct': Decimal('15.0')}

        >>> calculate_suggested_price(Decimal("8500"), Decimal("20"), rounding=100)
        {'suggested_price': Decimal('10200'), 'margin_amount': Decimal('1700'), 'margin_pct': Decimal('20.0')}
    """
    if cost_price <= 0:
        return {
            "suggested_price": Decimal("0"),
            "margin_amount": Decimal("0"),
            "margin_pct": Decimal("0"),
            "competitor_diff": None,
        }

    # Calculate base price with target margin
    # Selling Price = Cost / (1 - Margin%)
    # Or: Selling Price = Cost * (1 + Markup%)
    # For 15% margin: markup = 15 / (100 - 15) = 17.65%
    margin_decimal = target_margin_pct / Decimal("100")
    markup_decimal = margin_decimal / (Decimal("1") - margin_decimal)
    base_price = cost_price * (Decimal("1") + markup_decimal)

    # Round to nearest rounding value (e.g., 50 or 100 MWK)
    if rounding > 0:
        suggested_price = (base_price / rounding).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * rounding
    else:
        suggested_price = base_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Calculate actual margin with rounded price
    margin_amount = suggested_price - cost_price
    actual_margin_pct = (margin_amount / suggested_price * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )

    result = {
        "suggested_price": suggested_price,
        "margin_amount": margin_amount,
        "margin_pct": actual_margin_pct,
        "competitor_diff": None,
    }

    # Compare with competitor price if provided
    if competitor_price and competitor_price > 0:
        diff = suggested_price - competitor_price
        result["competitor_diff"] = diff

    return result


def get_margin_presets() -> list[dict]:
    """
    Get list of common margin presets for UI quick selection.

    Returns:
        List of dicts with 'value', 'label', and 'description' keys
    """
    return [
        {
            "value": Decimal("10"),
            "label": "10%",
            "description": "Low margin (competitive pricing)",
        },
        {
            "value": Decimal("15"),
            "label": "15%",
            "description": "Standard margin (recommended)",
        },
        {
            "value": Decimal("20"),
            "label": "20%",
            "description": "Good margin (profitable)",
        },
        {
            "value": Decimal("25"),
            "label": "25%",
            "description": "High margin (premium)",
        },
        {
            "value": Decimal("30"),
            "label": "30%",
            "description": "Very high margin",
        },
    ]


def validate_selling_price(
    selling_price: Decimal,
    cost_price: Decimal,
    min_margin_pct: Decimal = Decimal("5"),
) -> Dict[str, any]:
    """
    Validate selling price against cost price.
    Warns if selling below cost or below minimum margin.

    Args:
        selling_price: Proposed selling price
        cost_price: Cost per unit
        min_margin_pct: Minimum acceptable margin percentage (default 5%)

    Returns:
        Dict with:
            - is_valid: True if price is acceptable
            - warnings: List of warning messages
            - margin_pct: Actual margin percentage
            - margin_amount: Profit per unit
    """
    warnings = []
    is_valid = True

    if cost_price <= 0:
        return {
            "is_valid": True,
            "warnings": [],
            "margin_pct": Decimal("0"),
            "margin_amount": Decimal("0"),
        }

    margin_amount = selling_price - cost_price
    margin_pct = (margin_amount / selling_price * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # Check if selling below cost
    if selling_price < cost_price:
        warnings.append(f"⚠️ Selling below cost! Loss: MK {abs(margin_amount):,.2f} per unit")
        is_valid = False

    # Check if margin is too low
    elif margin_pct < min_margin_pct:
        warnings.append(f"⚠️ Low margin: {margin_pct}% (minimum recommended: {min_margin_pct}%)")

    # Check if margin is very high (possible data entry error)
    elif margin_pct > Decimal("50"):
        warnings.append(f"ℹ️ High margin: {margin_pct}% - verify pricing is correct")

    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "margin_pct": margin_pct,
        "margin_amount": margin_amount,
    }
