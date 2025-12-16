# inventory/services/stock_overview_common.py
"""
Shared stock overview service providing consistent stock summary across all verticals.
Returns total items, values, low stock, out of stock, etc.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Any, Optional
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce


def get_stock_overview(
    business,
    vertical: Optional[str] = None,
    location=None,
) -> Dict[str, Any]:
    """
    Get stock overview summary for a business across all verticals.
    
    Args:
        business: Business instance
        vertical: Business vertical/kind (phones, pharmacy, liquor, etc.)
        location: Optional location filter
    
    Returns:
        Dict with:
            - total_items: int - Total items in stock
            - total_cost_value: Decimal - Total cost/purchase value
            - total_retail_value: Decimal - Total retail/selling value
            - expected_profit: Decimal - Difference between retail and cost
            - low_stock_count: int - Items below low stock threshold
            - out_of_stock_count: int - Items with zero quantity
            - categories: List[Dict] - Breakdown by category/brand
    """
    if not vertical:
        vertical = getattr(business, 'business_kind', 'phones').lower()
    
    # Route to vertical-specific handler
    if vertical == 'phones':
        return _get_phones_stock_overview(business, location)
    elif vertical == 'pharmacy':
        return _get_pharmacy_stock_overview(business, location)
    elif vertical == 'liquor':
        return _get_liquor_stock_overview(business, location)
    elif vertical == 'clothing':
        return _get_clothing_stock_overview(business, location)
    elif vertical == 'gym':
        return _get_gym_stock_overview(business, location)
    elif vertical == 'grocery':
        return _get_grocery_stock_overview(business, location)
    else:
        return _get_generic_stock_overview(business, location)


def _get_phones_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for phones vertical (IMEI-based inventory)."""
    try:
        from inventory.models import InventoryItem
    except ImportError:
        return _empty_overview()
    
    # Base queryset: unsold items
    items_qs = InventoryItem.objects.filter(
        business=business,
        status='IN_STOCK',
    )
    
    if location:
        items_qs = items_qs.filter(location=location)
    
    # Aggregate values
    agg = items_qs.aggregate(
        total_items=Count('id'),
        total_cost=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField()),
        total_retail=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField()),
    )
    
    total_items = agg['total_items'] or 0
    total_cost = agg['total_cost'] or Decimal('0.00')
    total_retail = agg['total_retail'] or Decimal('0.00')
    expected_profit = total_retail - total_cost
    
    # Group by brand for categories
    try:
        categories = (
            items_qs.filter(product__isnull=False)
            .values('product__brand')
            .annotate(
                count=Count('id'),
                cost=Sum('order_price'),
                retail=Sum('selling_price'),
            )
            .order_by('-count')[:10]
        )
        categories_list = [
            {
                'name': cat['product__brand'] or 'Unknown',
                'count': cat['count'],
                'cost_value': float(cat['cost'] or 0),
                'retail_value': float(cat['retail'] or 0),
            }
            for cat in categories
        ]
    except Exception:
        categories_list = []
    
    return {
        'total_items': total_items,
        'total_cost_value': float(total_cost),
        'total_retail_value': float(total_retail),
        'expected_profit': float(expected_profit),
        'low_stock_count': 0,  # Not applicable for IMEI-based inventory
        'out_of_stock_count': 0,
        'categories': categories_list,
    }


def _get_pharmacy_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for pharmacy vertical (quantity-based inventory)."""
    try:
        from inventory.models_pharmacy import PharmacyProduct
    except ImportError:
        return _empty_overview()
    
    products_qs = PharmacyProduct.objects.filter(business=business)
    
    if location:
        products_qs = products_qs.filter(location=location)
    
    # Aggregate values
    agg = products_qs.aggregate(
        total_items=Count('id'),
        total_cost=Coalesce(Sum(F('quantity') * F('cost_price')), Decimal('0.00'), output_field=DecimalField()),
        total_retail=Coalesce(Sum(F('quantity') * F('selling_price')), Decimal('0.00'), output_field=DecimalField()),
    )
    
    total_items = agg['total_items'] or 0
    total_cost = agg['total_cost'] or Decimal('0.00')
    total_retail = agg['total_retail'] or Decimal('0.00')
    expected_profit = total_retail - total_cost
    
    # Low stock and out of stock
    low_stock_count = products_qs.filter(quantity__gt=0, quantity__lte=F('low_stock_threshold')).count()
    out_of_stock_count = products_qs.filter(quantity=0).count()
    
    # Group by category
    try:
        categories = (
            products_qs
            .values('category')
            .annotate(
                count=Count('id'),
                total_qty=Sum('quantity'),
            )
            .order_by('-total_qty')[:10]
        )
        categories_list = [
            {
                'name': cat['category'] or 'Uncategorized',
                'count': cat['count'],
                'quantity': cat['total_qty'],
            }
            for cat in categories
        ]
    except Exception:
        categories_list = []
    
    return {
        'total_items': total_items,
        'total_cost_value': float(total_cost),
        'total_retail_value': float(total_retail),
        'expected_profit': float(expected_profit),
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'categories': categories_list,
    }


def _get_liquor_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for liquor vertical."""
    try:
        from inventory.models_verticals import LiquorProduct
    except ImportError:
        return _empty_overview()
    
    products_qs = LiquorProduct.objects.filter(business=business)
    
    if location and hasattr(LiquorProduct, 'location'):
        products_qs = products_qs.filter(location=location)
    
    agg = products_qs.aggregate(
        total_items=Count('id'),
        total_cost=Coalesce(Sum(F('quantity') * F('cost_price')), Decimal('0.00'), output_field=DecimalField()),
        total_retail=Coalesce(Sum(F('quantity') * F('selling_price')), Decimal('0.00'), output_field=DecimalField()),
    )
    
    total_items = agg['total_items'] or 0
    total_cost = agg['total_cost'] or Decimal('0.00')
    total_retail = agg['total_retail'] or Decimal('0.00')
    expected_profit = total_retail - total_cost
    
    low_stock_count = products_qs.filter(quantity__gt=0, quantity__lte=10).count()  # Assume 10 as threshold
    out_of_stock_count = products_qs.filter(quantity=0).count()
    
    return {
        'total_items': total_items,
        'total_cost_value': float(total_cost),
        'total_retail_value': float(total_retail),
        'expected_profit': float(expected_profit),
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'categories': [],
    }


def _get_clothing_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for clothing vertical."""
    try:
        from inventory.models_verticals import ClothingProduct
    except ImportError:
        return _empty_overview()
    
    products_qs = ClothingProduct.objects.filter(business=business)
    
    if location and hasattr(ClothingProduct, 'location'):
        products_qs = products_qs.filter(location=location)
    
    agg = products_qs.aggregate(
        total_items=Count('id'),
        total_cost=Coalesce(Sum(F('quantity') * F('cost_price')), Decimal('0.00'), output_field=DecimalField()),
        total_retail=Coalesce(Sum(F('quantity') * F('selling_price')), Decimal('0.00'), output_field=DecimalField()),
    )
    
    total_items = agg['total_items'] or 0
    total_cost = agg['total_cost'] or Decimal('0.00')
    total_retail = agg['total_retail'] or Decimal('0.00')
    expected_profit = total_retail - total_cost
    
    low_stock_count = products_qs.filter(quantity__gt=0, quantity__lte=5).count()
    out_of_stock_count = products_qs.filter(quantity=0).count()
    
    return {
        'total_items': total_items,
        'total_cost_value': float(total_cost),
        'total_retail_value': float(total_retail),
        'expected_profit': float(expected_profit),
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'categories': [],
    }


def _get_gym_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for gym vertical (memberships, not physical stock)."""
    try:
        from inventory.models_verticals import GymMember
    except ImportError:
        return _empty_overview()
    
    members_qs = GymMember.objects.filter(business=business, is_active=True)
    
    if location and hasattr(GymMember, 'location'):
        members_qs = members_qs.filter(location=location)
    
    total_members = members_qs.count()
    
    # Group by membership type
    try:
        categories = (
            members_qs
            .values('membership_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        categories_list = [
            {
                'name': cat['membership_type'] or 'Unknown',
                'count': cat['count'],
            }
            for cat in categories
        ]
    except Exception:
        categories_list = []
    
    return {
        'total_items': total_members,
        'total_cost_value': 0.0,
        'total_retail_value': 0.0,
        'expected_profit': 0.0,
        'low_stock_count': 0,
        'out_of_stock_count': 0,
        'categories': categories_list,
        'note': 'Gym vertical tracks memberships, not physical stock',
    }


def _get_grocery_stock_overview(business, location) -> Dict[str, Any]:
    """Get stock overview for grocery vertical."""
    return _get_generic_stock_overview(business, location)


def _get_generic_stock_overview(business, location) -> Dict[str, Any]:
    """Generic fallback for verticals without specific implementation."""
    try:
        from inventory.models import InventoryItem
    except ImportError:
        return _empty_overview()
    
    items_qs = InventoryItem.objects.filter(business=business, status='IN_STOCK')
    
    if location:
        items_qs = items_qs.filter(location=location)
    
    total_items = items_qs.count()
    
    return {
        'total_items': total_items,
        'total_cost_value': 0.0,
        'total_retail_value': 0.0,
        'expected_profit': 0.0,
        'low_stock_count': 0,
        'out_of_stock_count': 0,
        'categories': [],
    }


def _empty_overview() -> Dict[str, Any]:
    """Return empty overview structure."""
    return {
        'total_items': 0,
        'total_cost_value': 0.0,
        'total_retail_value': 0.0,
        'expected_profit': 0.0,
        'low_stock_count': 0,
        'out_of_stock_count': 0,
        'categories': [],
    }

