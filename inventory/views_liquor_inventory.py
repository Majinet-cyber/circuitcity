# inventory/views_liquor_inventory.py
"""
Liquor Inventory Dashboard with category-based "stock batteries"
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, F
from django.shortcuts import render
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from tenants.utils import require_business


# Category configurations with default capacities
LIQUOR_CATEGORIES = {
    "beer": {"label": "Beers", "capacity": 200, "icon": "bi-cup-straw"},
    "cider": {"label": "Ciders", "capacity": 150, "icon": "bi-droplet-half"},
    "spirits": {"label": "Spirits", "capacity": 100, "icon": "bi-lightning"},
    "wine": {"label": "Wine", "capacity": 80, "icon": "bi-wine"},
    "soft_drinks": {"label": "Soft Drinks", "capacity": 300, "icon": "bi-cup"},
    "water": {"label": "Water", "capacity": 200, "icon": "bi-droplet"},
    "other": {"label": "Other", "capacity": 100, "icon": "bi-box"},
}


def _calculate_days_in_stock(products) -> int:
    """Calculate average days since products were stocked in"""
    now = timezone.now()
    total_days = 0
    count = 0
    
    for product in products:
        if hasattr(product, "created_at") and product.created_at:
            days = (now - product.created_at).days
            total_days += days
            count += 1
    
    return int(total_days / count) if count > 0 else 0


def _get_category_data(business, category_key: str, config: dict) -> dict:
    """Get stock data for a specific category"""
    # Query products in this category
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        category__iexact=category_key
    )
    
    # Calculate metrics
    total_stock = products.filter(track_inventory=True).aggregate(
        total=Sum("quantity")
    )["total"] or 0
    
    sku_count = products.count()
    capacity = config.get("capacity", 100)
    percentage = min(100, int((total_stock / capacity) * 100)) if capacity > 0 else 0
    days_in_stock = _calculate_days_in_stock(products)
    
    return {
        "key": category_key,
        "label": config["label"],
        "icon": config.get("icon", "bi-box"),
        "current_stock": total_stock,
        "capacity": capacity,
        "percentage": percentage,
        "sku_count": sku_count,
        "days_in_stock": days_in_stock,
    }


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_inventory_dashboard(request):
    """
    Liquor Inventory Dashboard with category-based stock batteries
    """
    business = get_active_business(request)
    
    # Build category data
    category_batteries = []
    for category_key, config in LIQUOR_CATEGORIES.items():
        data = _get_category_data(business, category_key, config)
        # Only include categories with products
        if data["sku_count"] > 0 or data["current_stock"] > 0:
            category_batteries.append(data)
    
    # Overall stats
    all_liquor_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True
    )
    
    total_skus = all_liquor_products.count()
    total_stock = all_liquor_products.filter(track_inventory=True).aggregate(
        total=Sum("quantity")
    )["total"] or 0
    
    # Low stock items (quantity < 10)
    low_stock_items = all_liquor_products.filter(
        track_inventory=True,
        quantity__lt=10,
        quantity__gt=0
    ).order_by("quantity")[:10]
    
    # Out of stock items
    out_of_stock_items = all_liquor_products.filter(
        track_inventory=True,
        quantity=0
    ).count()
    
    context = {
        "business": business,
        "category_batteries": category_batteries,
        "total_skus": total_skus,
        "total_stock": total_stock,
        "low_stock_items": low_stock_items,
        "out_of_stock_count": out_of_stock_items,
    }
    
    return render(request, "verticals/liquor/inventory_dashboard.html", context)

