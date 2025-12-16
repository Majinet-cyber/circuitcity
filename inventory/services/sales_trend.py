# inventory/services/sales_trend.py
"""
Shared sales trend service providing consistent bar chart data across all verticals.
Returns Products vs Quantity Sold data suitable for Chart.js bar charts.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta, date
from typing import Dict, List, Any, Optional
from django.db.models import Sum, Count, Q, F
from django.utils import timezone


def get_sales_trend_by_product(
    business,
    start_date: date,
    end_date: date,
    vertical: Optional[str] = None,
    location=None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Get sales trend data grouped by product/model.
    Returns top N products by quantity sold within the date range.
    
    Args:
        business: Business instance
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        vertical: Business vertical/kind (phones, pharmacy, liquor, etc.)
        location: Optional location filter
        limit: Max number of products to return (default 10)
    
    Returns:
        Dict with:
            - labels: List[str] - Product names/models
            - quantities: List[int] - Units sold per product
            - revenue: List[float] - Revenue per product
            - total_qty: int - Total units sold
            - total_revenue: float - Total revenue
            - period: str - Date range description
    """
    if not vertical:
        vertical = getattr(business, 'business_kind', 'phones').lower()
    
    # Route to vertical-specific handler
    if vertical == 'phones':
        return _get_phones_sales_trend(business, start_date, end_date, location, limit)
    elif vertical == 'pharmacy':
        return _get_pharmacy_sales_trend(business, start_date, end_date, location, limit)
    elif vertical == 'liquor':
        return _get_liquor_sales_trend(business, start_date, end_date, location, limit)
    elif vertical == 'clothing':
        return _get_clothing_sales_trend(business, start_date, end_date, location, limit)
    elif vertical == 'gym':
        return _get_gym_sales_trend(business, start_date, end_date, location, limit)
    elif vertical == 'grocery':
        return _get_grocery_sales_trend(business, start_date, end_date, location, limit)
    else:
        # Generic fallback
        return _get_generic_sales_trend(business, start_date, end_date, location, limit)


def _get_phones_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for phones vertical (group by brand + model)."""
    try:
        from sales.models import Sale
        from inventory.models import InventoryItem, PhoneProductCatalog
    except ImportError:
        return _empty_response()
    
    # Build queryset
    sales_qs = Sale.objects.filter(
        item__business=business,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    ).select_related('item__product')
    
    if location:
        sales_qs = sales_qs.filter(location=location)
    
    # Group by product and aggregate
    product_sales = (
        sales_qs
        .values('item__product__brand', 'item__product__model_name')
        .annotate(
            qty=Count('id'),
            revenue=Sum('price')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in product_sales:
        brand = row['item__product__brand'] or 'Unknown'
        model = row['item__product__model_name'] or 'Unknown'
        labels.append(f"{brand} {model}")
        quantities.append(row['qty'])
        revenues.append(float(row['revenue'] or 0))
    
    total_qty = sum(quantities)
    total_revenue = sum(revenues)
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': total_qty,
        'total_revenue': total_revenue,
        'period': f"{start_date} to {end_date}",
    }


def _get_pharmacy_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for pharmacy vertical (group by product)."""
    try:
        from inventory.models_pharmacy import PharmacySale, PharmacyProduct
    except ImportError:
        return _empty_response()
    
    sales_qs = PharmacySale.objects.filter(
        business=business,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    )
    
    if location:
        sales_qs = sales_qs.filter(location=location)
    
    # Group by product
    product_sales = (
        sales_qs
        .values('product__name')
        .annotate(
            qty=Sum('quantity'),
            revenue=Sum('total_amount')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in product_sales:
        labels.append(row['product__name'] or 'Unknown Product')
        quantities.append(int(row['qty'] or 0))
        revenues.append(float(row['revenue'] or 0))
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': sum(quantities),
        'total_revenue': sum(revenues),
        'period': f"{start_date} to {end_date}",
    }


def _get_liquor_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for liquor vertical (group by product)."""
    try:
        from inventory.models_verticals import LiquorSale, LiquorProduct
    except ImportError:
        return _empty_response()
    
    sales_qs = LiquorSale.objects.filter(
        business=business,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    )
    
    if location and hasattr(LiquorSale, 'location'):
        sales_qs = sales_qs.filter(location=location)
    
    # Group by product
    product_sales = (
        sales_qs
        .values('product__name')
        .annotate(
            qty=Sum('quantity'),
            revenue=Sum('total_price')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in product_sales:
        labels.append(row['product__name'] or 'Unknown Product')
        quantities.append(int(row['qty'] or 0))
        revenues.append(float(row['revenue'] or 0))
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': sum(quantities),
        'total_revenue': sum(revenues),
        'period': f"{start_date} to {end_date}",
    }


def _get_clothing_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for clothing vertical (group by product)."""
    try:
        from inventory.models_verticals import ClothingSale, ClothingProduct
    except ImportError:
        return _empty_response()
    
    sales_qs = ClothingSale.objects.filter(
        business=business,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    )
    
    if location and hasattr(ClothingSale, 'location'):
        sales_qs = sales_qs.filter(location=location)
    
    # Group by product
    product_sales = (
        sales_qs
        .values('product__name')
        .annotate(
            qty=Sum('quantity'),
            revenue=Sum('total_price')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in product_sales:
        labels.append(row['product__name'] or 'Unknown Product')
        quantities.append(int(row['qty'] or 0))
        revenues.append(float(row['revenue'] or 0))
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': sum(quantities),
        'total_revenue': sum(revenues),
        'period': f"{start_date} to {end_date}",
    }


def _get_gym_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for gym vertical (group by membership type)."""
    try:
        from inventory.models_verticals import GymMemberPayment
    except ImportError:
        return _empty_response()
    
    payments_qs = GymMemberPayment.objects.filter(
        business=business,
        payment_date__gte=start_date,
        payment_date__lte=end_date,
    )
    
    if location and hasattr(GymMemberPayment, 'location'):
        payments_qs = payments_qs.filter(location=location)
    
    # Group by membership type or period
    payment_sales = (
        payments_qs
        .values('member__membership_type')
        .annotate(
            qty=Count('id'),
            revenue=Sum('amount')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in payment_sales:
        labels.append(row['member__membership_type'] or 'Unknown Type')
        quantities.append(int(row['qty'] or 0))
        revenues.append(float(row['revenue'] or 0))
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': sum(quantities),
        'total_revenue': sum(revenues),
        'period': f"{start_date} to {end_date}",
    }


def _get_grocery_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Get sales trend for grocery vertical (generic product sales)."""
    return _get_generic_sales_trend(business, start_date, end_date, location, limit)


def _get_generic_sales_trend(business, start_date, end_date, location, limit) -> Dict[str, Any]:
    """Generic fallback for verticals without specific implementation."""
    try:
        from inventory.models import InventoryItem
    except ImportError:
        return _empty_response()
    
    # Try to use InventoryItem as generic approach
    items_qs = InventoryItem.objects.filter(
        business=business,
        status='SOLD',
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    )
    
    if location:
        items_qs = items_qs.filter(location=location)
    
    # Group by product name or SKU
    product_field = 'name' if hasattr(InventoryItem, 'name') else 'sku'
    
    product_sales = (
        items_qs
        .values(product_field)
        .annotate(
            qty=Count('id'),
            revenue=Sum('selling_price')
        )
        .order_by('-qty')[:limit]
    )
    
    labels = []
    quantities = []
    revenues = []
    
    for row in product_sales:
        labels.append(row.get(product_field) or 'Unknown Product')
        quantities.append(int(row['qty'] or 0))
        revenues.append(float(row['revenue'] or 0))
    
    return {
        'labels': labels,
        'quantities': quantities,
        'revenue': revenues,
        'total_qty': sum(quantities),
        'total_revenue': sum(revenues),
        'period': f"{start_date} to {end_date}",
    }


def _empty_response() -> Dict[str, Any]:
    """Return empty response structure."""
    return {
        'labels': [],
        'quantities': [],
        'revenue': [],
        'total_qty': 0,
        'total_revenue': 0.0,
        'period': 'N/A',
    }

