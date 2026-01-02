# inventory/utils_metrics.py
"""
Utility functions for computing business metrics and KPIs.

This module provides helpers for calculating margins, profit estimates, and other
key performance indicators based on sales history.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import Coalesce


# Default gross margin for electronics/phones when no sales history exists
DEFAULT_MARGIN = Decimal("0.12")  # 12%

# Sanity cap to prevent unrealistic margin estimates
MAX_MARGIN = Decimal("0.90")  # 90%


def estimate_margin_for_business_and_sku(business, product=None, sku=None) -> Decimal:
    """
    Returns a gross margin percentage (0–1) based on past sales history.

    Priority:
      1) SKU-specific margin if enough history exists
      2) Product-specific margin if SKU not available
      3) Business-wide average margin
      4) DEFAULT_MARGIN (0.12 = 12%)

    Never returns negative values or None. Returns a safe default if no sales exist.

    Args:
        business: Business instance
        product: Optional Product instance for product-specific margin
        sku: Optional SKU string for SKU-specific margin

    Returns:
        Decimal: Gross margin percentage (0.00 to 0.90)

    Examples:
        >>> margin = estimate_margin_for_business_and_sku(my_business)
        >>> # Returns 0.15 if business has 15% average margin from past sales
        >>> # Returns 0.12 if no sales history exists (default)
    """
    from sales.models import Sale
    from inventory.models import InventoryItem

    # Try to use Sale model first (has explicit price and item.order_price)
    try:
        # Build base queryset for this business
        # Sale doesn't have business FK, so we filter via item's business
        sales_qs = Sale.objects.select_related("item").filter(
            item__business=business,
            price__gt=0,  # Only valid sales with positive price
            item__order_price__gt=0,  # Must have valid cost
        )

        # 1) Try SKU-specific margin first
        if sku:
            sku_sales = sales_qs.filter(item__product__code=sku)
            if sku_sales.count() >= 3:  # Need at least 3 sales for reliable average
                margin = _compute_margin_from_sales(sku_sales)
                if margin is not None:
                    return _clamp_margin(margin)

        # 2) Try Product-specific margin
        if product:
            product_sales = sales_qs.filter(item__product=product)
            if product_sales.count() >= 3:
                margin = _compute_margin_from_sales(product_sales)
                if margin is not None:
                    return _clamp_margin(margin)

        # 3) Business-wide average margin
        if sales_qs.count() >= 5:  # Need at least 5 sales for business average
            margin = _compute_margin_from_sales(sales_qs)
            if margin is not None:
                return _clamp_margin(margin)

    except Exception:
        # If Sale model not available or query fails, try InventoryItem fallback
        pass

    # Fallback: try InventoryItem SOLD items (older pattern)
    try:
        sold_items = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            selling_price__gt=0,
            order_price__gt=0,
        )

        if product:
            sold_items = sold_items.filter(product=product)

        if sold_items.count() >= 3:
            margin = _compute_margin_from_inventory(sold_items)
            if margin is not None:
                return _clamp_margin(margin)

    except Exception:
        pass

    # 4) Final fallback: default margin
    return DEFAULT_MARGIN


def _compute_margin_from_sales(sales_qs) -> Optional[Decimal]:
    """
    Compute average gross margin from Sale queryset.

    Margin = (selling_price - cost) / cost
    Returns average margin across all sales, or None if invalid.
    """
    try:
        # Annotate each sale with its margin percentage
        # margin = (price - order_price) / order_price
        annotated = sales_qs.annotate(
            margin_pct=Coalesce(
                (F("price") - F("item__order_price")) / F("item__order_price"),
                Decimal("0"),
            )
        )

        # Filter out extreme outliers (negative margins or > 200%)
        # This prevents bad data from skewing the average
        valid_margins = annotated.filter(
            margin_pct__gte=Decimal("-0.5"),  # Allow some negative (returns/errors)
            margin_pct__lte=Decimal("2.0"),  # Cap at 200% margin
        )

        if valid_margins.count() == 0:
            return None

        avg_margin = valid_margins.aggregate(avg=Avg("margin_pct"))["avg"]

        if avg_margin is not None:
            return Decimal(str(avg_margin))

    except Exception:
        pass

    return None


def _compute_margin_from_inventory(inventory_qs) -> Optional[Decimal]:
    """
    Compute average gross margin from InventoryItem queryset (SOLD items).

    Margin = (selling_price - order_price) / order_price
    Returns average margin, or None if invalid.
    """
    try:
        annotated = inventory_qs.annotate(
            margin_pct=Coalesce(
                (F("selling_price") - F("order_price")) / F("order_price"),
                Decimal("0"),
            )
        )

        # Filter out extreme outliers
        valid_margins = annotated.filter(
            margin_pct__gte=Decimal("-0.5"),
            margin_pct__lte=Decimal("2.0"),
        )

        if valid_margins.count() == 0:
            return None

        avg_margin = valid_margins.aggregate(avg=Avg("margin_pct"))["avg"]

        if avg_margin is not None:
            return Decimal(str(avg_margin))

    except Exception:
        pass

    return None


def _clamp_margin(margin: Decimal) -> Decimal:
    """
    Clamp margin to reasonable bounds (0% to MAX_MARGIN).

    If margin is negative or unrealistic, return DEFAULT_MARGIN instead.
    """
    # If negative or zero, use default
    if margin < Decimal("0"):
        return DEFAULT_MARGIN

    # If unrealistically high, cap it
    if margin > MAX_MARGIN:
        return MAX_MARGIN

    return margin


def compute_potential_profit_from_stock(stock_qs, business, product=None) -> Decimal:
    """
    Compute estimated potential profit for stock on hand using margin-based estimation.

    This replaces the old (selling_value - cost_value) calculation which could go negative
    when selling prices weren't set or were zero.

    Instead, we:
    1. Calculate total cost value of stock
    2. Estimate margin % from sales history
    3. potential_profit = cost_value * margin_pct

    Args:
        stock_qs: QuerySet of in-stock items
        business: Business instance
        product: Optional Product to get product-specific margin

    Returns:
        Decimal: Estimated potential profit (always >= 0)
    """
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    # Calculate total cost value of stock on hand
    stock_cost_value = stock_qs.aggregate(total=Coalesce(Sum("order_price"), Decimal("0.00")))["total"] or Decimal(
        "0.00"
    )

    if stock_cost_value <= 0:
        return Decimal("0.00")

    # Get estimated margin from sales history
    margin_pct = estimate_margin_for_business_and_sku(business, product=product)

    # Calculate potential profit
    potential_profit = stock_cost_value * margin_pct

    # Ensure it's never negative
    if potential_profit < 0:
        return Decimal("0.00")

    return potential_profit
