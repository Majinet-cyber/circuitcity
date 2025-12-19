# inventory/views_liquor_stock_in.py
"""
Liquor Stock In - Gamified UI for stocking liquor products
Supports crates and bottles with editable crate sizes
"""
from __future__ import annotations

from decimal import Decimal
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import LiquorShiftStock, LiquorShift
from tenants.utils import require_business


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
@require_http_methods(["GET", "POST"])
def liquor_stock_in(request):
    """
    Liquor Stock In page with gamified product cards.
    Supports crates and bottles with editable crate sizes.
    """
    business = get_active_business(request)
    
    if request.method == "POST":
        return _handle_stock_in_post(request, business)
    
    # GET: Show stock in form
    # Get all active liquor products grouped by category
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_archived=False,
        is_active=True
    ).order_by("category", "name")
    
    products_by_category = defaultdict(list)
    for p in products:
        cat = (p.category or "other").lower()
        products_by_category[cat].append(p)
    
    # Build categories list in order
    category_order = ["beer", "cider", "wine", "spirits", "whiskey", "other"]
    categories = [cat for cat in category_order if cat in products_by_category]
    
    # Get active shift (for context)
    active_shift = LiquorShift.objects.filter(
        business=business,
        closed_at__isnull=True
    ).order_by("-opened_at").first()
    
    # Get today's stock-in count (gamification)
    today = timezone.now().date()
    today_stock_in_count = LiquorShiftStock.objects.filter(
        shift__business=business,
        recorded_at__date=today,
        snapshot_type="opening"
    ).count()
    
    context = {
        "business": business,
        "categories": categories,
        "products_by_category": dict(products_by_category),
        "active_shift": active_shift,
        "today_stock_in_count": today_stock_in_count,
        "active_tab": "stock_in",
    }
    
    return render(request, "inventory/liquor/stock_in.html", context)


@transaction.atomic
def _handle_stock_in_post(request, business):
    """Handle stock in form submission"""
    product_id = request.POST.get("product_id")
    quantity_type = request.POST.get("quantity_type", "bottles")  # "crates" or "bottles"
    
    if not product_id:
        messages.error(request, "Product is required")
        return redirect("liquor:stock_in")
    
    try:
        product = MerchProduct.objects.get(pk=product_id, business=business, kind=BusinessKind.LIQUOR)
    except MerchProduct.DoesNotExist:
        messages.error(request, "Product not found")
        return redirect("liquor:stock_in")
    
    # Parse quantities
    try:
        if quantity_type == "crates":
            crates_count = int(request.POST.get("crates_count", 0))
            crate_size = int(request.POST.get("crate_size", 20))  # Default 20 bottles per crate
            
            if crates_count <= 0:
                messages.error(request, "Crates count must be greater than 0")
                return redirect("liquor:stock_in")
            
            if crate_size <= 0:
                messages.error(request, "Crate size must be greater than 0")
                return redirect("liquor:stock_in")
            
            bottles_count = crates_count * crate_size
        else:
            bottles_count = int(request.POST.get("bottles_count", 0))
            
            if bottles_count <= 0:
                messages.error(request, "Bottles count must be greater than 0")
                return redirect("liquor:stock_in")
    except (ValueError, TypeError):
        messages.error(request, "Invalid quantity")
        return redirect("liquor:stock_in")
    
    # Parse pricing
    try:
        price_per_bottle = Decimal(request.POST.get("price_per_bottle", "0"))
        price_per_shot = Decimal(request.POST.get("price_per_shot", "0")) if product.has_shots else None
        
        if price_per_bottle < 0:
            messages.error(request, "Price per bottle cannot be negative")
            return redirect("liquor:stock_in")
        
        if price_per_shot and price_per_shot < 0:
            messages.error(request, "Price per shot cannot be negative")
            return redirect("liquor:stock_in")
    except (ValueError, TypeError):
        messages.error(request, "Invalid price format")
        return redirect("liquor:stock_in")
    
    # Update product pricing if provided
    if price_per_bottle > 0:
        product.price_per_bottle = price_per_bottle
    
    if price_per_shot and price_per_shot > 0:
        product.price_per_shot = price_per_shot
    
    product.save(update_fields=["price_per_bottle", "price_per_shot"])
    
    # Get or create active shift (required for stock tracking)
    shift = LiquorShift.objects.filter(
        business=business,
        closed_at__isnull=True
    ).order_by("-opened_at").first()
    
    if not shift:
        # Auto-create a shift for stock-in
        shift = LiquorShift.objects.create(
            business=business,
            opened_by=request.user,
            opened_at=timezone.now(),
            location=getattr(request, "active_location", None)
        )
    
    # Create or update stock snapshot
    stock_snapshot, created = LiquorShiftStock.objects.get_or_create(
        shift=shift,
        product=product,
        snapshot_type="opening",
        defaults={
            "bottles_count": bottles_count,
            "shots_count": 0,
            "recorded_at": timezone.now(),
            "recorded_by": request.user
        }
    )
    
    if not created:
        # Update existing snapshot (add to existing stock)
        stock_snapshot.bottles_count += bottles_count
        stock_snapshot.recorded_at = timezone.now()
        stock_snapshot.recorded_by = request.user
        stock_snapshot.save(update_fields=["bottles_count", "recorded_at", "recorded_by"])
    
    # Success message with gamification
    if quantity_type == "crates":
        crates_count = int(request.POST.get("crates_count", 0))
        crate_size = int(request.POST.get("crate_size", 20))
        messages.success(
            request,
            f"✅ Stocked {crates_count} crate(s) of {product.name} ({bottles_count} bottles total, {crate_size} per crate). Keep going!"
        )
    else:
        messages.success(
            request,
            f"✅ Stocked {bottles_count} bottle(s) of {product.name}. Keep going!"
        )
    
    return redirect("liquor:stock_in")

