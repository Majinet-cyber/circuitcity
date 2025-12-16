# inventory/views_phones.py
"""
Gamified phone scan-in and scan-sell views.

Brand-card UI for ITEL, TECNO, SAMSUNG with:
- Visual brand selection
- Model dropdown filtered by brand
- Gamification stats (daily targets, progress bars)
- Premium success screens with profit/sales stats
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

# Tenant/business scoping
from tenants.utils import get_active_business
from tenants.scope import resolve_location_for_user

# Models
from inventory.models import InventoryItem
from inventory.models_phone_products import PhoneProductCatalog

# Helpers
from inventory.phone_catalog_seed import get_brands_for_business, get_models_for_brand
from inventory.business_kinds import BusinessKind

# Decorators
from core.decorators import manager_required
from tenants.utils import require_business

# Role helpers
from core.roles import is_manager, is_agent


# =============================================================================
# BRAND CONFIG (with logos and taglines) - 5 BRANDS
# =============================================================================
PHONE_BRANDS = [
    {
        "key": "tecno",
        "name": "TECNO",
        "logo": "img/brands/tecno.svg",
        "tagline": "Africa's bestseller",
        "color": "#3b82f6",  # blue
    },
    {
        "key": "itel",
        "name": "ITEL",
        "logo": "img/brands/itel.svg",
        "tagline": "Budget workhorse",
        "color": "#ef4444",  # red
    },
    {
        "key": "samsung",
        "name": "SAMSUNG",
        "logo": "img/brands/samsung.svg",
        "tagline": "Premium experience",
        "color": "#f97316",  # orange
    },
    {
        "key": "google_pixel",
        "name": "GOOGLE PIXEL",
        "logo": "img/brands/pixel.svg",
        "tagline": "Pure Android",
        "color": "#10b981",  # green
    },
    {
        "key": "redmi",
        "name": "REDMI",
        "logo": "img/brands/redmi.svg",
        "tagline": "Value leader",
        "color": "#8b5cf6",  # purple
    },
    {
        "key": "iphone",
        "name": "IPHONE",
        "logo": "img/brands/iphone.svg",
        "tagline": "Premium Apple experience",
        "color": "#111827",  # dark gray/black
    },
]


# =============================================================================
# HELPER: Get phone models for a brand + business
# =============================================================================
def get_phone_models_for_brand(business, brand_key: str) -> List[Dict[str, Any]]:
    """
    Get available phone models for a brand, scoped to business.
    Returns list of dicts with id, model_name, variant_label, etc.
    """
    if not business:
        return []
    
    try:
        models = get_models_for_brand(business, brand_key.upper())
        return models
    except Exception:
        return []


# =============================================================================
# INTELLIGENT IMEI PICKER API
# =============================================================================
@never_cache
@login_required
@require_business
def phone_available_imeis(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    Return available IMEIs for a given product, scoped by business + location + role.
    
    Definition of "available":
    - IMEIs that currently exist in stock for this business
    - Status = IN_STOCK (not sold)
    - is_active = True
    
    Scoping rules:
    - Managers: see all IMEIs across all locations in their business
    - Agents: see only IMEIs in their current location
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    location_id = resolve_location_for_user(request)
    location = None
    if location_id:
        try:
            from inventory.models import Location
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    # Base queryset: in-stock items for this business and product
    qs = InventoryItem.objects.filter(
        business=business,
        product_id=product_id,
        status="IN_STOCK",
        is_active=True,
        imei__isnull=False,  # Only show items with IMEIs
    ).exclude(imei="")  # Exclude empty strings
    
    # Role-based scoping
    user = request.user
    if is_manager(user):
        # Managers see all IMEIs across all locations in their business
        pass  # No additional filtering needed
    else:
        # Agents see only their location's IMEIs
        if location:
            qs = qs.filter(current_location=location)
        else:
            # If no location, return empty (agents must have a location)
            return JsonResponse({"ok": True, "imeis": []})
    
    # Get IMEIs, ordered for consistency
    imeis = list(qs.values_list("imei", flat=True).order_by("imei"))
    
    return JsonResponse({
        "ok": True,
        "imeis": imeis,
        "count": len(imeis),
    })


# =============================================================================
# GAMIFIED SCAN-IN (Phones only)
# =============================================================================
@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
@transaction.atomic
def phone_scan_in(request: HttpRequest) -> HttpResponse:
    """
    Gamified scan-in page for PHONES vertical.
    
    Shows brand cards (ITEL, TECNO, SAMSUNG) → model dropdown → IMEI → submit.
    Displays daily scan target progress bar at top.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:inventory_dashboard")
    
    # Only for PHONES businesses
    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        # Redirect to generic scan-in
        return redirect("inventory:scan_in")
    
    location_id = resolve_location_for_user(request)
    
    # Get the actual Location object (required for creating InventoryItem)
    location = None
    if location_id:
        try:
            from inventory.models import Location
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    # If no location found, use business default
    if not location:
        from inventory.models import Location
        location = Location.default_for(business)
    
    if not location:
        messages.error(request, "No location available for this business.")
        return redirect("inventory:inventory_dashboard")
    
    # --- Gamification stats: today's scans (role-based) ---
    today = date.today()
    base_qs = InventoryItem.objects.filter(
        business=business,
        received_at=today,
        is_active=True,
    )
    
    # Role-based scoping for stats
    if is_manager(request.user):
        # Managers see all scans for the business (across all locations)
        scanned_today = base_qs.count()
    else:
        # Agents see only their own contributions in their location
        scanned_today = base_qs.filter(
            assigned_agent=request.user,
        ).count()
        
        # Further restrict to location if available
        if location:
            scanned_today = base_qs.filter(
                assigned_agent=request.user,
                current_location=location,
            ).count()
    
    # Daily target (could be made configurable per business later)
    daily_target = 50
    progress_pct = min(100, int(scanned_today * 100 / daily_target)) if daily_target else 0
    
    # --- GET: Render UI ---
    if request.method == "GET":
        # Get brands available in this business's catalog (safe: returns [] if empty)
        try:
            available_brands = get_brands_for_business(business)
        except Exception:
            available_brands = []
        
        # Filter PHONE_BRANDS to only those available
        brands_with_data = [
            b for b in PHONE_BRANDS
            if b["name"] in available_brands or b["key"].upper() in available_brands
        ]
        
        # DEFENSIVE: If no brands seeded, show empty state (fallback to all brand cards for UI)
        # Template must handle empty catalog gracefully with "No models/products yet" message
        context = {
            "brands": brands_with_data or PHONE_BRANDS,  # fallback to all brand cards for UI
            "has_catalog": len(available_brands) > 0,  # Flag for template to show empty state
            "scanned_today": scanned_today,
            "daily_target": daily_target,
            "progress_pct": progress_pct,
            "business": business,
            "location": location,
            "active_tab": "scan_in",  # For base.html bottom nav highlighting
        }
        return render(request, "inventory/phones_scan_in.html", context)
    
    # --- POST: Process scan-in ---
    brand_key = request.POST.get("brand", "").strip()
    catalog_id = request.POST.get("catalog_product_id", "").strip()
    imei = request.POST.get("imei", "").strip()
    
    # Basic validation
    if not (brand_key and catalog_id and imei):
        messages.error(request, "Please select a brand, model, and enter IMEI.")
        return redirect("inventory:phone_scan_in")
    
    # Security: Ensure the catalog product belongs to THIS business (prevent cross-business attacks)
    try:
        catalog_product_check = PhoneProductCatalog.objects.get(
            id=int(catalog_id),
            business=business,
            is_active=True,
        )
    except (ValueError, PhoneProductCatalog.DoesNotExist):
        messages.error(request, "Invalid phone model selected or product not found in your business.")
        return redirect("inventory:phone_scan_in")
    
    # Normalize IMEI: digits only, last 15 chars
    imei_clean = "".join(ch for ch in imei if ch.isdigit())
    if len(imei_clean) >= 15:
        imei_clean = imei_clean[-15:]
    
    if len(imei_clean) != 15:
        messages.error(request, f"IMEI must be exactly 15 digits. Got {len(imei_clean)} digits.")
        return redirect("inventory:phone_scan_in")
    
    # Check duplicate IMEI in this business
    existing = InventoryItem.objects.filter(business=business, imei=imei_clean).first()
    if existing:
        messages.error(
            request,
            f"IMEI {imei_clean} already exists in your inventory. "
            "We never stock the same device twice."
        )
        return redirect("inventory:phone_scan_in")
    
    # Resolve catalog product (already validated above for security)
    catalog_product = catalog_product_check
    
    # Use default cost price from catalog (or 0)
    order_price = catalog_product.default_cost_price or Decimal("0.00")
    
    # Get or create a Product entry for this catalog item (required by InventoryItem)
    from inventory.models import Product
    product, _ = Product.objects.get_or_create(
        brand=catalog_product.brand,
        model=catalog_product.model_name,
        variant=catalog_product.variant_label,
        defaults={
            "code": f"{catalog_product.brand}-{catalog_product.model_name}-{catalog_product.variant_label}".replace(" ", "-"),
            "name": catalog_product.display_name,
            "cost_price": catalog_product.default_cost_price or Decimal("0.00"),
            "sale_price": catalog_product.default_selling_price or Decimal("0.00"),
        }
    )
    
    # Create inventory item
    try:
        item = InventoryItem.objects.create(
            business=business,
            imei=imei_clean,
            product=product,
            order_price=order_price,
            status="IN_STOCK",
            current_location=location,
            is_active=True,
            received_at=date.today(),
            sold_at=None,
            assigned_agent=request.user if not request.user.is_staff else None,
        )
        
        # Success message with gamification
        messages.success(
            request,
            f"✅ {catalog_product.display_name} (IMEI: {imei_clean}) added to stock! "
            f"Scanned {scanned_today + 1} today. Keep going!"
        )
        
        return redirect("inventory:phone_scan_in")
        
    except Exception as e:
        messages.error(request, f"Failed to add phone to inventory: {str(e)}")
        return redirect("inventory:phone_scan_in")


# =============================================================================
# GAMIFIED SCAN-SELL (Phones only)
# =============================================================================
@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
@transaction.atomic
def phone_scan_sell(request: HttpRequest) -> HttpResponse:
    """
    Gamified scan-sell page for PHONES vertical.
    
    Shows brand cards → in-stock models dropdown → IMEI → selling price → submit.
    Displays daily sales target progress bar and premium success screen with profit.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:inventory_dashboard")
    
    # Only for PHONES businesses
    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        # Redirect to generic scan-sold
        return redirect("inventory:scan_sold")
    
    location_id = resolve_location_for_user(request)
    
    # Get the actual Location object (required for querying InventoryItem)
    location = None
    if location_id:
        try:
            from inventory.models import Location
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    # If no location found, use business default
    if not location:
        from inventory.models import Location
        location = Location.default_for(business)
    
    if not location:
        messages.error(request, "No location available for this business.")
        return redirect("inventory:inventory_dashboard")
    
    # --- Gamification stats: today's sales ---
    today = date.today()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))
    
    sold_today = InventoryItem.objects.filter(
        business=business,
        status="SOLD",
        sold_at__range=(today_start, today_end),
    ).count()
    
    # Filter by location if available
    if location:
        sold_today = InventoryItem.objects.filter(
            business=business,
            current_location=location,
            status="SOLD",
            sold_at__range=(today_start, today_end),
        ).count()
    
    # Daily sales target
    daily_sales_target = 30
    sales_progress_pct = min(100, int(sold_today * 100 / daily_sales_target)) if daily_sales_target else 0
    
    # --- GET: Render UI ---
    if request.method == "GET":
        # Get brands available in this business's catalog
        available_brands = get_brands_for_business(business)
        
        # Filter PHONE_BRANDS to only those available
        brands_with_data = [
            b for b in PHONE_BRANDS
            if b["name"] in available_brands or b["key"].upper() in available_brands
        ]
        
        context = {
            "brands": brands_with_data or PHONE_BRANDS,
            "sold_today": sold_today,
            "daily_sales_target": daily_sales_target,
            "sales_progress_pct": sales_progress_pct,
            "business": business,
            "location": location,
            "active_tab": "sell",  # For base.html bottom nav highlighting
        }
        return render(request, "inventory/phones_scan_sell.html", context)
    
    # --- POST: Process sale ---
    brand_key = request.POST.get("brand", "").strip()
    imei = request.POST.get("imei", "").strip()
    selling_price_raw = request.POST.get("selling_price", "").strip()
    payment_method = request.POST.get("payment_method", "CASH").strip()
    
    # Basic validation
    if not (brand_key and imei and selling_price_raw):
        messages.error(request, "Please select a brand, enter IMEI, and selling price.")
        return redirect("inventory:phone_scan_sell")
    
    # Normalize IMEI
    imei_clean = "".join(ch for ch in imei if ch.isdigit())
    if len(imei_clean) >= 15:
        imei_clean = imei_clean[-15:]
    
    if len(imei_clean) != 15:
        messages.error(request, f"IMEI must be exactly 15 digits. Got {len(imei_clean)} digits.")
        return redirect("inventory:phone_scan_sell")
    
    # Find in-stock item
    item_qs = InventoryItem.objects.filter(
        business=business,
        imei=imei_clean,
        status="IN_STOCK",
        is_active=True,
    )
    
    if location:
        item_qs = item_qs.filter(current_location=location)
    
    item = item_qs.first()
    
    if not item:
        messages.error(
            request,
            f"IMEI {imei_clean} not found in stock. "
            "Please scan in the phone first or check the IMEI."
        )
        return redirect("inventory:phone_scan_sell")
    
    # Parse selling price
    try:
        selling_price = Decimal(selling_price_raw)
        if selling_price <= 0:
            raise ValueError("Selling price must be positive")
    except (ValueError, Decimal.InvalidOperation):
        messages.error(request, f"Invalid selling price: {selling_price_raw}")
        return redirect("inventory:phone_scan_sell")
    
    # Calculate profit
    cost = item.order_price or Decimal("0.00")
    profit = selling_price - cost
    
    # Mark as sold
    try:
        item.status = "SOLD"
        item.selling_price = selling_price
        item.sold_at = timezone.now()
        item.payment_method = payment_method
        item.save(update_fields=["status", "selling_price", "sold_at", "payment_method", "updated_at"])
        
        # Premium success message with profit
        sales_left = max(0, daily_sales_target - (sold_today + 1))
        profit_msg = f"💰 Profit: MK {profit:,.0f}" if profit > 0 else ""
        target_msg = f"🎯 {sales_left} sales away from today's target!" if sales_left > 0 else "🎉 Target reached!"
        
        messages.success(
            request,
            f"✅ Sold! {item.product or 'Phone'} (IMEI: {imei_clean}) · "
            f"{profit_msg} · {target_msg}"
        )
        
        return redirect("inventory:phone_scan_sell")
        
    except Exception as e:
        messages.error(request, f"Failed to record sale: {str(e)}")
        return redirect("inventory:phone_scan_sell")

