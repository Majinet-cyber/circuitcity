# inventory/liquor_utils.py
"""
Utility functions for liquor vertical operations.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from math import ceil
from typing import TYPE_CHECKING

from django.db.models import Sum, Max
from django.utils import timezone

if TYPE_CHECKING:
    from tenants.models import Business


def recalculate_liquor_targets_for_business(business: "Business", lookback_days: int = 30) -> dict:
    """
    Recalculate stock targets for all liquor products with auto-adjust enabled.

    Uses the last `lookback_days` of sales data to find peak daily bottles sold,
    then adjusts the target upward by the product's auto_adjust_pct.

    Returns a dict of {product_id: new_target} for products that were updated.
    """
    from inventory.models import MerchProduct
    from inventory.models_verticals import LiquorSale, LiquorStockSettings
    from inventory.business_kinds import BusinessKind

    # Get business-level settings for default auto-adjust percentage
    try:
        settings = LiquorStockSettings.objects.get(business=business)
        default_pct = settings.default_auto_adjust_pct
        lookback_days = settings.auto_adjust_lookback_days
    except LiquorStockSettings.DoesNotExist:
        default_pct = 20
        lookback_days = 30

    # Get all liquor products with auto-adjust enabled
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.LIQUOR, is_active=True, auto_adjust_enabled=True
    )

    cutoff_date = timezone.now() - timedelta(days=lookback_days)
    updated = {}

    for product in products:
        # Get sales for this product in the lookback period
        sales = (
            LiquorSale.objects.filter(
                business=business,
                product=product,
                sold_at__gte=cutoff_date,
                unit="bottle",  # Only count bottle sales for target calculation
            )
            .values("sold_at__date")
            .annotate(daily_bottles=Sum("quantity"))
        )

        if not sales:
            # No sales data, skip this product
            continue

        # Find peak daily bottles sold
        peak_daily = max(s["daily_bottles"] for s in sales)

        if peak_daily <= 0:
            continue

        # Use product's auto_adjust_pct if set, otherwise use business default
        adjust_pct = product.auto_adjust_pct if product.auto_adjust_pct else default_pct

        # Calculate new target: peak_daily * (1 + adjust_pct/100)
        multiplier = 1 + (Decimal(adjust_pct) / 100)
        new_target = ceil(float(peak_daily) * float(multiplier))

        # Only update if the new target is different from current
        if new_target != product.target_bottles:
            product.target_bottles = new_target
            product.save(update_fields=["target_bottles"])
            updated[product.id] = new_target

    return updated


def get_stock_overview_data(business: "Business", location=None) -> dict:
    """
    Get stock overview data with per-product and business-level targets.

    Returns a dict with:
    - categories: list of category dicts with {category, current, target, percent}
    - totals: {current, target, percent}
    - warnings: list of warning messages
    """
    from inventory.models import MerchProduct
    from inventory.models_verticals import LiquorStockSettings
    from inventory.business_kinds import BusinessKind

    # Get or create business-level settings
    settings, _ = LiquorStockSettings.objects.get_or_create(
        business=business,
        defaults={
            "beer_target": 600,
            "cider_target": 600,
            "spirits_target": 600,
            "whiskey_target": 600,
            "wine_target": 600,
            "other_target": 600,
            "default_auto_adjust_pct": 20,
        },
    )

    # Get all active liquor products
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True)

    if location:
        products = products.filter(location=location)

    # Group by category and calculate current stock + targets
    category_data = {}
    category_defaults = {
        "beer": settings.beer_target,
        "cider": settings.cider_target,
        "spirits": settings.spirits_target,
        "whiskey": settings.whiskey_target,
        "wine": settings.wine_target,
        "other": settings.other_target,
    }

    for product in products:
        cat = (product.category or "other").lower()

        if cat not in category_data:
            category_data[cat] = {
                "category": cat,
                "current": 0,
                "per_product_target": 0,
                "business_default": category_defaults.get(cat, 600),
            }

        # Add current stock
        qty = getattr(product, "quantity", 0) or 0
        category_data[cat]["current"] += qty

        # Add per-product target if set
        if product.target_bottles > 0:
            category_data[cat]["per_product_target"] += product.target_bottles

    # Calculate final targets and percentages
    category_rows = []
    warnings = []

    for cat, data in category_data.items():
        # Use per-product targets if any exist, otherwise use business default
        target = data["per_product_target"] if data["per_product_target"] > 0 else data["business_default"]
        current = data["current"]

        percent = int(current * 100 / target) if target > 0 else 0
        percent = min(percent, 100)  # Cap at 100%

        category_rows.append(
            {
                "category": cat,
                "category_display": cat.title(),
                "current": current,
                "target": target,
                "percent": percent,
                "using_per_product_targets": data["per_product_target"] > 0,
            }
        )

        # Add warnings for low or excessive stock
        if target > 0:
            if current < target * 0.3:  # Below 30%
                warnings.append(
                    {
                        "type": "danger",
                        "category": cat.title(),
                        "message": f"Critical: {cat.title()} is very low ({current}/{target} bottles, {percent}%). Restock urgently!",
                    }
                )
            elif current < target * 0.5:  # Below 50%
                warnings.append(
                    {
                        "type": "warning",
                        "category": cat.title(),
                        "message": f"Warning: {cat.title()} is running low ({current}/{target} bottles, {percent}%). Consider restocking soon.",
                    }
                )
            elif current > target * 1.2:  # Above 120%
                warnings.append(
                    {
                        "type": "info",
                        "category": cat.title(),
                        "message": f"Info: {cat.title()} is above target ({current}/{target} bottles, {percent}%). You may want to adjust your target upward or slow restocking.",
                    }
                )

    # Sort by category name
    category_rows.sort(key=lambda x: x["category"])

    # Calculate totals
    total_current = sum(row["current"] for row in category_rows)
    total_target = sum(row["target"] for row in category_rows)
    total_percent = int(total_current * 100 / total_target) if total_target > 0 else 0

    return {
        "categories": category_rows,
        "totals": {
            "current": total_current,
            "target": total_target,
            "percent": total_percent,
        },
        "warnings": warnings,
        "settings": settings,
    }
