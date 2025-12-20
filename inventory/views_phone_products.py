# inventory/views_phone_products.py
"""
Brand-first phone product management.

Simplified UX for PHONES businesses:
- 5 brand panels (Tecno, Itel, Samsung, Google Pixel, Redmi)
- Inline form to add models
- Display recent 10 models per brand
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Dict, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from tenants.utils import get_active_business, require_business
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind
from inventory.authz import require_business_kind
from core.decorators import manager_required


# =============================================================================
# BRAND CONFIG - 5 brands with colors
# =============================================================================
PHONE_BRANDS = [
    {
        "key": "tecno",
        "name": "Tecno",
        "display": "TECNO",
        "color": "#3b82f6",  # blue
        "description": "Africa's bestseller",
        "icon": "img/brands/tecno.svg"
    },
    {
        "key": "itel",
        "name": "Itel",
        "display": "ITEL",
        "color": "#ef4444",  # red
        "description": "Budget workhorse",
        "icon": "img/brands/itel.svg"
    },
    {
        "key": "samsung",
        "name": "Samsung",
        "display": "SAMSUNG",
        "color": "#f97316",  # orange
        "description": "Premium experience",
        "icon": "img/brands/samsung.svg"
    },
    {
        "key": "google_pixel",
        "name": "Google Pixel",
        "display": "GOOGLE PIXEL",
        "color": "#10b981",  # green
        "description": "Pure Android",
        "icon": "img/brands/google-pixel.svg"
    },
    {
        "key": "redmi",
        "name": "Redmi",
        "display": "REDMI",
        "color": "#8b5cf6",  # purple/neutral
        "description": "Value leader",
        "icon": "img/brands/redmi.svg"
    },
    {
        "key": "iphone",
        "name": "iPhone",
        "display": "IPHONE",
        "color": "#111827",  # dark gray/black
        "description": "Premium Apple experience",
        "icon": "img/brands/iphone.svg"
    },
    {
        "key": "huawei",
        "name": "Huawei",
        "display": "HUAWEI",
        "color": "#dc2626",  # red
        "description": "Innovation leader",
        "icon": "img/brands/default.svg"
    },
]


def get_brand_config(brand_key: str) -> Dict[str, Any] | None:
    """Get brand config by key"""
    for brand in PHONE_BRANDS:
        if brand["key"].lower() == brand_key.lower():
            return brand
    return None


def get_recent_models_for_brand(business, brand_display: str, limit: int = 10) -> List[PhoneProductCatalog]:
    """Get recent models for a brand"""
    if not business:
        return []
    
    return list(
        PhoneProductCatalog.objects
        .filter(business=business, brand__iexact=brand_display, is_active=True)
        .order_by("-created_at")[:limit]
    )


# =============================================================================
# MAIN VIEW: Add Products (Brand-First)
# =============================================================================
@login_required
@require_business
@manager_required
@require_http_methods(["GET", "POST"])
def add_phone_products(request: HttpRequest) -> HttpResponse:
    """
    Brand-first phone product creation.
    
    Shows 5 brand panels. When user clicks a brand, they can add a model
    for that brand. Recent 10 models are shown below each brand panel.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")
    
    # Only for PHONES businesses
    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        messages.warning(request, "This page is for phone businesses only.")
        return redirect("inventory:inventory_dashboard")
    
    # Handle POST: Add a new phone model
    if request.method == "POST":
        brand_key = request.POST.get("brand", "").strip()
        model_name = request.POST.get("model_name", "").strip()
        model_number = request.POST.get("model_number", "").strip()
        specs = request.POST.get("specs", "").strip()  # e.g., "4+128"
        order_price_str = request.POST.get("order_price", "").strip()
        
        # Validate brand
        brand_config = get_brand_config(brand_key)
        if not brand_config:
            messages.error(request, "Invalid brand selected.")
            return redirect(request.path)
        
        # Validate required fields
        if not model_name:
            messages.error(request, "Model name is required.")
            return redirect(request.path)
        
        if not specs:
            messages.error(request, "Specs (ROM+RAM, e.g., '128+4') are required.")
            return redirect(request.path)
        
        # Parse specs - Format: ROM+RAM (e.g., "128+4" or "256+8")
        try:
            parts = specs.replace(" ", "").split("+")
            if len(parts) != 2:
                raise ValueError("Invalid format")
            rom_gb = int(parts[0])  # First part is ROM (storage)
            ram_gb = int(parts[1])  # Second part is RAM (memory)
            if ram_gb <= 0 or rom_gb <= 0:
                raise ValueError("RAM and ROM must be positive")
        except (ValueError, IndexError):
            messages.error(request, "Invalid specs format. Use format like '128+4' or '256+8' (ROM+RAM).")
            return redirect(request.path)
        
        # Parse order price (optional)
        order_price = None
        if order_price_str:
            try:
                order_price = Decimal(order_price_str)
                if order_price < 0:
                    raise ValueError("Price must be non-negative")
            except (ValueError, Exception):
                messages.error(request, "Invalid order price.")
                return redirect(request.path)
        
        # Create or update product
        try:
            with transaction.atomic():
                product, created = PhoneProductCatalog.objects.update_or_create(
                    business=business,
                    brand=brand_config["display"],
                    model_name=model_name,
                    ram_gb=ram_gb,
                    rom_gb=rom_gb,
                    defaults={
                        "model_number": model_number,
                        "variant_label": specs,
                        "default_cost_price": order_price,
                        "is_active": True,
                        "created_by": request.user,
                    }
                )
                
                if created:
                    messages.success(
                        request,
                        f"✅ Added {brand_config['display']} {model_name} ({specs})"
                    )
                else:
                    messages.info(
                        request,
                        f"📝 Updated {brand_config['display']} {model_name} ({specs})"
                    )
        except Exception as e:
            messages.error(request, f"Error saving product: {e}")
        
        return redirect(request.path)
    
    # GET: Show brand panels with recent models and flagship suggestions
    from inventory.phone_catalog_seed import FLAGSHIP_PHONES
    
    brands_with_models = []
    for brand_config in PHONE_BRANDS:
        recent_models = get_recent_models_for_brand(business, brand_config["display"], limit=10)
        
        # Get flagship model suggestions for this brand
        flagship_models = [
            phone["model"] for phone in FLAGSHIP_PHONES 
            if phone["brand"].upper() == brand_config["display"].upper()
        ]
        
        brands_with_models.append({
            "config": brand_config,
            "recent_models": recent_models,
            "flagship_models": flagship_models,
        })
    
    context = {
        "business": business,
        "brands_with_models": brands_with_models,
        "page_title": "Add Products",
    }
    
    return render(request, "inventory/add_product_phones_v2.html", context)


# =============================================================================
# API: Get models for a brand (JSON)
# =============================================================================
@login_required
@require_business
def api_phone_models_for_brand(request: HttpRequest, brand_key: str) -> JsonResponse:
    """
    API endpoint to fetch models for a specific brand.
    Used for dynamic loading in UI.
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"error": "No active business"}, status=400)
    
    brand_config = get_brand_config(brand_key)
    if not brand_config:
        return JsonResponse({"error": "Invalid brand"}, status=400)
    
    models = get_recent_models_for_brand(business, brand_config["display"], limit=50)
    
    data = {
        "brand": brand_config["display"],
        "models": [
            {
                "id": m.id,
                "model_name": m.model_name,
                "variant": m.variant_label,
                "display": f"{m.model_name} ({m.variant_label})",
                "cost_price": float(m.default_cost_price) if m.default_cost_price else None,
            }
            for m in models
        ]
    }
    
    return JsonResponse(data)


# =============================================================================
# Gamified Phone Product Wizard
# =============================================================================
@login_required
@require_business
@manager_required
@require_business_kind(BusinessKind.PHONES)
def phone_product_wizard(request: HttpRequest) -> HttpResponse:
    """
    Gamified phone product wizard - matches clothing wizard quality.
    
    Multi-step flow:
    1. Choose Brand (Tecno, Itel, Infinix, Samsung, iPhone, Redmi, Huawei, Other)
    2. Choose Model (show popular models + allow custom)
    3. Choose Specs (2/32, 3/64, 4/64, 4/128, 6/128, 8/128, 8/256)
    4. Price + Cost
    5. Tracking (IMEI / Barcode / Both)
    6. Save
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")
    
    # Handle POST - save the product
    if request.method == "POST":
        try:
            brand_key = request.POST.get("brand", "").strip()
            model_name = request.POST.get("model", "").strip()
            specs = request.POST.get("specs", "").strip()  # e.g., "4/128"
            cost_price_str = request.POST.get("cost_price", "").strip()
            selling_price_str = request.POST.get("selling_price", "").strip()
            tracking_type = request.POST.get("tracking_type", "imei").strip()
            
            # Validate brand
            brand_config = get_brand_config(brand_key)
            if not brand_config:
                messages.error(request, "Invalid brand selected.")
                return redirect(request.path)
            
            # Validate required fields
            if not model_name:
                messages.error(request, "Model name is required.")
                return redirect(request.path)
            
            if not specs:
                messages.error(request, "Specs (RAM/ROM) are required.")
                return redirect(request.path)
            
            # Parse specs (e.g., "4/128" or "8/256")
            try:
                parts = specs.replace(" ", "").split("/")
                if len(parts) != 2:
                    raise ValueError("Invalid format")
                ram_gb = int(parts[0])
                rom_gb = int(parts[1])
                if ram_gb <= 0 or rom_gb <= 0:
                    raise ValueError("RAM and ROM must be positive")
            except (ValueError, IndexError):
                messages.error(request, "Invalid specs format. Use format like '4/128' or '8/256'.")
                return redirect(request.path)
            
            # Parse prices
            cost_price = None
            if cost_price_str:
                try:
                    cost_price = Decimal(cost_price_str)
                    if cost_price < 0:
                        raise ValueError("Cost must be non-negative")
                except (ValueError, Exception):
                    messages.error(request, "Invalid cost price.")
                    return redirect(request.path)
            
            selling_price = None
            if selling_price_str:
                try:
                    selling_price = Decimal(selling_price_str)
                    if selling_price < 0:
                        raise ValueError("Price must be non-negative")
                except (ValueError, Exception):
                    messages.error(request, "Invalid selling price.")
                    return redirect(request.path)
            
            # Create or update product
            with transaction.atomic():
                product, created = PhoneProductCatalog.objects.update_or_create(
                    business=business,
                    brand=brand_config["display"],
                    model_name=model_name,
                    ram_gb=ram_gb,
                    rom_gb=rom_gb,
                    defaults={
                        "variant_label": specs,
                        "default_cost_price": cost_price,
                        "is_active": True,
                        "created_by": request.user,
                    }
                )
                
                if created:
                    messages.success(
                        request,
                        f"✅ Added {brand_config['display']} {model_name} ({specs}) to catalog"
                    )
                else:
                    messages.info(
                        request,
                        f"📝 Updated {brand_config['display']} {model_name} ({specs})"
                    )
                
                # Redirect to products list or dashboard
                return redirect("inventory:phone_products")
                
        except Exception as e:
            messages.error(request, f"Error saving product: {e}")
            return redirect(request.path)
    
    # GET: Show wizard
    context = {
        "business": business,
        "brands": PHONE_BRANDS,
        "page_title": "Add Phone Product",
    }
    
    return render(request, "inventory/wizards/phone_product_wizard.html", context)


# =============================================================================
# MANAGER ONLY: Remove/Soft Delete Phone Product
# =============================================================================
@login_required
@require_business
@manager_required
@require_http_methods(["POST"])
def remove_phone_product(request: HttpRequest, product_id: int) -> HttpResponse:
    """
    Soft-delete a phone product (manager only).
    
    This sets is_active=False so the product is hidden from selectable products
    going forward, but does NOT delete historical sales/stock records.
    
    Security:
    - Manager-only (via decorator)
    - Business-scoped (product must belong to active business)
    - Preserves historical data (soft delete only)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")
    
    try:
        product = PhoneProductCatalog.objects.get(
            id=product_id,
            business=business
        )
        
        # Soft delete: set is_active=False
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        
        messages.success(
            request,
            f"✅ Removed {product.display_name} from catalog. "
            "Historical sales and stock remain intact."
        )
        
    except PhoneProductCatalog.DoesNotExist:
        messages.error(request, "Product not found or does not belong to your business.")
    except Exception as e:
        messages.error(request, f"Error removing product: {e}")
    
    # Redirect back to products page
    return redirect("inventory:phone_products")