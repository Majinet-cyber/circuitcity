# inventory/views_liquor_inventory.py
"""
Liquor Inventory Dashboard with category-based "stock batteries"
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, F, Subquery, OuterRef
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
    from inventory.models_verticals import LiquorShiftStock
    from django.db.models import Subquery, OuterRef
    
    # Query products in this category
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True,
        category__iexact=category_key
    )
    
    # Get latest stock snapshots for these products
    # Subquery to get the most recent snapshot for each product
    latest_snapshots = LiquorShiftStock.objects.filter(
        product=OuterRef('pk'),
        shift__business=business
    ).order_by('-recorded_at')
    
    # Calculate total stock from latest snapshots
    total_stock = 0
    products_with_stock = products.filter(track_inventory=True).annotate(
        latest_bottles=Subquery(latest_snapshots.values('bottles_count')[:1])
    )
    
    for product in products_with_stock:
        if product.latest_bottles is not None:
            total_stock += product.latest_bottles
    
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
    from inventory.models_verticals import LiquorShiftStock
    
    all_liquor_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True
    )
    
    total_skus = all_liquor_products.count()
    
    # Get latest stock snapshots
    latest_snapshots = LiquorShiftStock.objects.filter(
        product=OuterRef('pk'),
        shift__business=business
    ).order_by('-recorded_at')
    
    # Calculate total stock from latest snapshots
    total_stock = 0
    products_with_stock = all_liquor_products.filter(track_inventory=True).annotate(
        latest_bottles=Subquery(latest_snapshots.values('bottles_count')[:1])
    )
    
    low_stock_list = []
    out_of_stock_count = 0
    
    for product in products_with_stock:
        bottles = product.latest_bottles or 0
        total_stock += bottles
        
        if bottles == 0:
            out_of_stock_count += 1
        elif bottles < 10:
            low_stock_list.append((product, bottles))
    
    # Sort low stock items by quantity and take top 10
    low_stock_list.sort(key=lambda x: x[1])
    low_stock_items = [item[0] for item in low_stock_list[:10]]
    
    context = {
        "business": business,
        "category_batteries": category_batteries,
        "total_skus": total_skus,
        "total_stock": total_stock,
        "low_stock_items": low_stock_items,
        "out_of_stock_count": out_of_stock_count,
        "active_tab": "inventory",
    }
    
    return render(request, "verticals/liquor/inventory_dashboard.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_scan_in(request):
    """
    Gamified scan-in page for LIQUOR vertical.
    Mirrors the sell scanner: Beer cards, Bottle/crate panels, Quantity panels, Price panels.
    """
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.db import transaction
    from django.views.decorators.http import require_http_methods
    from collections import defaultdict
    
    business = get_active_business(request)
    
    # UX SAFETY: Show success message if redirected with ?added=1
    if request.GET.get('added') == '1':
        messages.success(request, "✅ Stock added successfully! Add another product below.")
    
    if request.method == "POST":
        # POST logic: process stock-in
        try:
            product_id = int(request.POST.get("product_id", 0))
            quantity = int(request.POST.get("quantity", 1))
            unit_type = request.POST.get("unit_type", "bottle")  # "bottle" or "crate"
            cost_per_unit = Decimal(request.POST.get("cost_per_unit", "0.00"))
            
            product = MerchProduct.objects.get(
                pk=product_id,
                business=business,
                kind=BusinessKind.LIQUOR,
                is_active=True
            )
            
            # Calculate actual bottles to add
            bottles_to_add = quantity
            if unit_type == "crate":
                # MALAWI STANDARD: Default 20 bottles per crate (Kuche Kuche, Carlsberg, etc.)
                bottles_per_crate = getattr(product, 'bottles_per_crate', 20)
                bottles_to_add = quantity * bottles_per_crate
            
            with transaction.atomic():
                # Update product stock
                product.quantity_in_stock = (product.quantity_in_stock or 0) + bottles_to_add
                
                # Update cost price if provided
                if cost_per_unit > 0:
                    # MALAWI STANDARD: Default 20 bottles per crate
                    bottles_per_crate = getattr(product, 'bottles_per_crate', 20)
                    if unit_type == "crate" and bottles_per_crate:
                        product.cost_per_bottle = cost_per_unit / bottles_per_crate
                    else:
                        product.cost_per_bottle = cost_per_unit
                
                # Optional: Update selling price if provided
                selling_price_raw = request.POST.get("selling_price", "").strip()
                if selling_price_raw:
                    try:
                        selling_price = Decimal(selling_price_raw)
                        if selling_price > 0:
                            product.price_per_bottle = selling_price
                    except (ValueError, InvalidOperation):
                        pass
                
                product.save()
            
            # UX SAFETY: Redirect with success param (clean state, no overlay confusion)
            return redirect("liquor:scan_in") + "?added=1"
            
        except (ValueError, MerchProduct.DoesNotExist, KeyError) as e:
            messages.error(request, f"Stock-in failed: {e}")
            return redirect("liquor:scan_in")
    
    # GET: Build category-grouped products
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_archived=False,
        is_active=True
    ).order_by("category", "name")
    
    products_by_category = defaultdict(list)
    for p in products:
        cat = (p.category or "").lower()
        if cat:
            products_by_category[cat].append({
                'id': p.id,
                'name': p.name,
                'quantity_in_stock': p.quantity_in_stock or 0,
                'bottles_per_crate': getattr(p, 'bottles_per_crate', 20),  # MALAWI STANDARD: 20 bottles per crate
            })
    
    # Build categories list in order
    category_order = ["beer", "cider", "wine", "spirits", "whiskey"]
    categories = [cat for cat in category_order if cat in products_by_category]
    
    # Serialize products to JSON for JavaScript
    import json
    products_json = json.dumps(dict(products_by_category))
    
    return render(request, "verticals/liquor/scan_in.html", {
        "categories": categories,
        "products_by_category": products_json,
        "business": business,
        "active_tab": "scan_in",
    })