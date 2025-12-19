# inventory/services_kpis.py
"""
Universal KPI Calculator Service

Provides standardized KPI calculations (Revenue, COGS, Profit, Stock Value)
for all verticals with date range support.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Dict, Any, Tuple, Optional

from django.db.models import Sum, F, DecimalField, QuerySet
from django.utils import timezone

from tenants.models import Business


def parse_date_range(
    date_range_param: str,
    start_date_param: Optional[str] = None,
    end_date_param: Optional[str] = None
) -> Tuple[date, date, str]:
    """
    Parse date range parameter and return (start_date, end_date, display_label).
    
    Args:
        date_range_param: One of "today", "yesterday", "7days", "30days", "this_month", "custom"
        start_date_param: ISO format date string for custom range start
        end_date_param: ISO format date string for custom range end
    
    Returns:
        Tuple of (start_date, end_date, display_label)
    """
    today = timezone.now().date()
    
    if date_range_param == "today":
        return today, today, "Today"
    
    elif date_range_param == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday, "Yesterday"
    
    elif date_range_param == "7days" or not date_range_param:
        start = today - timedelta(days=6)  # Last 7 days including today
        return start, today, "Last 7 Days"
    
    elif date_range_param == "30days":
        start = today - timedelta(days=29)  # Last 30 days including today
        return start, today, "Last 30 Days"
    
    elif date_range_param == "this_month":
        start = today.replace(day=1)
        return start, today, "This Month"
    
    elif date_range_param == "custom" and start_date_param and end_date_param:
        try:
            start = date.fromisoformat(start_date_param)
            end = date.fromisoformat(end_date_param)
            return start, end, f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Fallback to last 7 days
            start = today - timedelta(days=6)
            return start, today, "Last 7 Days"
    
    else:
        # Default: last 7 days
        start = today - timedelta(days=6)
        return start, today, "Last 7 Days"


def calculate_grocery_kpis(
    business: Business,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    Calculate KPIs for Grocery vertical.
    
    Returns:
        Dict with keys: revenue, cogs, profit, stock_value
    """
    from .models_grocery import GroceryProduct, GrocerySale, GroceryCost
    from .models_unique_products import UniqueSale
    
    # Sales (both regular and unique products)
    regular_sales = GrocerySale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )
    
    unique_sales = UniqueSale.objects.filter(
        business=business,
        product__vertical="groceries",
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )
    
    # Calculate revenue and COGS from regular sales
    regular_revenue = sum(sale.total_amount for sale in regular_sales)
    regular_cogs = sum(sale.quantity * sale.unit_cost for sale in regular_sales)
    
    # Calculate revenue and COGS from unique sales
    unique_revenue = sum(sale.total_amount for sale in unique_sales)
    unique_cogs = sum(sale.total_cost for sale in unique_sales)
    
    # Total revenue and COGS
    revenue = regular_revenue + unique_revenue
    cogs = regular_cogs + unique_cogs
    profit = revenue - cogs
    
    # Stock value (current snapshot, not date-filtered)
    regular_products = GroceryProduct.objects.filter(business=business, is_active=True)
    regular_stock_value = sum(p.stock_value_cost for p in regular_products)
    
    from .models_unique_products import UniqueProduct
    unique_products = UniqueProduct.objects.filter(
        business=business,
        vertical="groceries",
        is_active=True
    )
    unique_stock_value = sum(p.stock_value_cost for p in unique_products)
    
    stock_value = regular_stock_value + unique_stock_value
    
    return {
        "revenue": revenue,
        "cogs": cogs,
        "profit": profit,
        "stock_value": stock_value,
    }


def calculate_clothing_kpis(
    business: Business,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    Calculate KPIs for Clothing vertical.
    """
    from .models import ClothingStockIn, ClothingSale
    from .models_unique_products import UniqueSale, UniqueProduct
    
    # Regular sales
    regular_sales = ClothingSale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    ).select_related("stock_item")
    
    # Unique sales
    unique_sales = UniqueSale.objects.filter(
        business=business,
        product__vertical="clothing",
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )
    
    # Calculate metrics
    regular_revenue = sum(sale.total_amount for sale in regular_sales)
    regular_cogs = sum(sale.unit_cost * sale.quantity_sold for sale in regular_sales)
    
    unique_revenue = sum(sale.total_amount for sale in unique_sales)
    unique_cogs = sum(sale.total_cost for sale in unique_sales)
    
    revenue = regular_revenue + unique_revenue
    cogs = regular_cogs + unique_cogs
    profit = revenue - cogs
    
    # Stock value (current)
    regular_stock = ClothingStockIn.objects.filter(
        business=business,
        is_active=True,
        quantity_remaining__gt=0
    )
    regular_stock_value = sum(
        item.cost_price_per_item * item.quantity_remaining
        for item in regular_stock
    )
    
    unique_products = UniqueProduct.objects.filter(
        business=business,
        vertical="clothing",
        is_active=True
    )
    unique_stock_value = sum(p.stock_value_cost for p in unique_products)
    
    stock_value = regular_stock_value + unique_stock_value
    
    return {
        "revenue": revenue,
        "cogs": cogs,
        "profit": profit,
        "stock_value": stock_value,
    }


def calculate_pharmacy_kpis(
    business: Business,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    Calculate KPIs for Pharmacy vertical (includes cosmetics).
    """
    from .models_pharmacy import PharmacyProductSale, PharmacyProduct
    from .models_unique_products import UniqueSale, UniqueProduct
    
    # Regular sales
    regular_sales = PharmacyProductSale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )
    
    # Unique sales (pharmacy + cosmetics)
    unique_sales = UniqueSale.objects.filter(
        business=business,
        product__vertical__in=["pharmacy", "cosmetics"],
        is_deleted=False,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )
    
    # Calculate metrics
    regular_revenue = sum(sale.total_amount for sale in regular_sales)
    regular_cogs = sum(sale.quantity * sale.unit_cost for sale in regular_sales)
    
    unique_revenue = sum(sale.total_amount for sale in unique_sales)
    unique_cogs = sum(sale.total_cost for sale in unique_sales)
    
    revenue = regular_revenue + unique_revenue
    cogs = regular_cogs + unique_cogs
    profit = revenue - cogs
    
    # Stock value (current)
    regular_products = PharmacyProduct.objects.filter(
        business=business,
        is_active=True
    )
    regular_stock_value = sum(
        p.quantity * p.cost_price
        for p in regular_products
    )
    
    unique_products = UniqueProduct.objects.filter(
        business=business,
        vertical__in=["pharmacy", "cosmetics"],
        is_active=True
    )
    unique_stock_value = sum(p.stock_value_cost for p in unique_products)
    
    stock_value = regular_stock_value + unique_stock_value
    
    return {
        "revenue": revenue,
        "cogs": cogs,
        "profit": profit,
        "stock_value": stock_value,
    }


def get_kpi_context(
    business: Business,
    vertical: str,
    date_range_param: Optional[str] = None,
    start_date_param: Optional[str] = None,
    end_date_param: Optional[str] = None
) -> Dict[str, Any]:
    """
    Universal KPI context builder for any vertical.
    
    Args:
        business: Business instance
        vertical: Vertical slug ("groceries", "clothing", "pharmacy", "liquor", "phones", "gym")
        date_range_param: Date range parameter from request
        start_date_param: Custom start date (ISO format)
        end_date_param: Custom end date (ISO format)
    
    Returns:
        Dict with KPI data ready for template context
    """
    # Parse date range
    start_date, end_date, display_label = parse_date_range(
        date_range_param or "7days",
        start_date_param,
        end_date_param
    )
    
    # Calculate KPIs based on vertical
    if vertical == "groceries":
        kpis = calculate_grocery_kpis(business, start_date, end_date)
    elif vertical == "clothing":
        kpis = calculate_clothing_kpis(business, start_date, end_date)
    elif vertical in ["pharmacy", "cosmetics"]:
        kpis = calculate_pharmacy_kpis(business, start_date, end_date)
    else:
        # Default/fallback
        kpis = {
            "revenue": Decimal("0.00"),
            "cogs": Decimal("0.00"),
            "profit": Decimal("0.00"),
            "stock_value": Decimal("0.00"),
        }
    
    return {
        "kpi_revenue": kpis["revenue"],
        "kpi_cogs": kpis["cogs"],
        "kpi_profit": kpis["profit"],
        "kpi_stock_value": kpis["stock_value"],
        "selected_date_range": date_range_param or "7days",
        "custom_start_date": start_date.isoformat() if date_range_param == "custom" else "",
        "custom_end_date": end_date.isoformat() if date_range_param == "custom" else "",
        "kpi_date_label": display_label,
    }

