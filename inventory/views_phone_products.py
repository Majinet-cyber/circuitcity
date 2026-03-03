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
from tenants.utils_roles import is_manager
from inventory.models_phone_products import PhoneProductCatalog, ElectronicsCategory
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
        "icon": "img/brands/tecno.svg",
    },
    {
        "key": "itel",
        "name": "Itel",
        "display": "ITEL",
        "color": "#ef4444",  # red
        "description": "Budget workhorse",
        "icon": "img/brands/itel.svg",
    },
    {
        "key": "samsung",
        "name": "Samsung",
        "display": "SAMSUNG",
        "color": "#f97316",  # orange
        "description": "Premium experience",
        "icon": "img/brands/samsung.svg",
    },
    {
        "key": "google_pixel",
        "name": "Google Pixel",
        "display": "GOOGLE PIXEL",
        "color": "#10b981",  # green
        "description": "Pure Android",
        "icon": "img/brands/google-pixel.svg",
    },
    {
        "key": "redmi",
        "name": "Redmi",
        "display": "REDMI",
        "color": "#8b5cf6",  # purple/neutral
        "description": "Value leader",
        "icon": "img/brands/redmi.svg",
    },
    {
        "key": "iphone",
        "name": "iPhone",
        "display": "IPHONE",
        "color": "#111827",  # dark gray/black
        "description": "Premium Apple experience",
        "icon": "img/brands/iphone.svg",
    },
    {
        "key": "huawei",
        "name": "Huawei",
        "display": "HUAWEI",
        "color": "#dc2626",  # red
        "description": "Innovation leader",
        "icon": "img/brands/default.svg",
    },
]


def get_brand_config(brand_key: str) -> Dict[str, Any] | None:
    """Get brand config by key"""
    for brand in PHONE_BRANDS:
        if brand["key"].lower() == brand_key.lower():
            return brand
    return None


def get_recent_models_for_brand(business, brand_display: str, limit: int = 10, category: str = None) -> List[PhoneProductCatalog]:
    """Get recent models for a brand (default: PHONE category only for backward compat)."""
    if not business:
        return []

    qs = PhoneProductCatalog.objects.filter(
        business=business, brand__iexact=brand_display, is_active=True
    )
    if category:
        qs = qs.filter(category=category)
    else:
        qs = qs.filter(category=ElectronicsCategory.PHONE)
    return list(qs.order_by("-created_at")[:limit])


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
                    category=ElectronicsCategory.PHONE,
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
                    },
                )

                if created:
                    messages.success(request, f"✅ Added {brand_config['display']} {model_name} ({specs})")
                else:
                    messages.info(request, f"📝 Updated {brand_config['display']} {model_name} ({specs})")
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
            phone["model"] for phone in FLAGSHIP_PHONES if phone["brand"].upper() == brand_config["display"].upper()
        ]

        brands_with_models.append(
            {
                "config": brand_config,
                "recent_models": recent_models,
                "flagship_models": flagship_models,
            }
        )

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
        ],
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
                    category=ElectronicsCategory.PHONE,
                    brand=brand_config["display"],
                    model_name=model_name,
                    ram_gb=ram_gb,
                    rom_gb=rom_gb,
                    defaults={
                        "variant_label": specs,
                        "default_cost_price": cost_price,
                        "default_selling_price": selling_price,
                        "is_active": True,
                        "created_by": request.user,
                    },
                )

                if created:
                    messages.success(request, f"✅ Added {brand_config['display']} {model_name} ({specs}) to catalog")
                else:
                    messages.info(request, f"📝 Updated {brand_config['display']} {model_name} ({specs})")

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
        product = PhoneProductCatalog.objects.get(id=product_id, business=business)

        # Soft delete: set is_active=False
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])

        messages.success(
            request, f"✅ Removed {product.display_name} from catalog. " "Historical sales and stock remain intact."
        )

    except PhoneProductCatalog.DoesNotExist:
        messages.error(request, "Product not found or does not belong to your business.")
    except Exception as e:
        messages.error(request, f"Error removing product: {e}")

    # Redirect back to products page
    return redirect("inventory:phone_products")


# =============================================================================
# MANAGER ONLY: Update Product Prices (Order Price & Selling Price)
# =============================================================================
def _parse_price_input(price_str: str) -> Decimal:
    """
    Parse price input, handling commas, spaces, and various formats.

    Examples:
    - "3,500" -> Decimal("3500")
    - "3 500" -> Decimal("3500")
    - "3500" -> Decimal("3500")
    - "45,000.50" -> Decimal("45000.50")

    Raises ValueError if invalid.
    """
    if not price_str:
        raise ValueError("Price cannot be empty")

    # Strip whitespace and remove commas/spaces
    cleaned = price_str.strip().replace(",", "").replace(" ", "")

    if not cleaned:
        raise ValueError("Price cannot be empty")

    try:
        price = Decimal(cleaned)
        if price < 0:
            raise ValueError("Price cannot be negative")
        return price
    except (ValueError, Exception) as e:
        if isinstance(e, ValueError) and "negative" in str(e):
            raise
        raise ValueError(f"Invalid price format: {price_str}")


@login_required
@require_business
@require_http_methods(["POST"])
def update_phone_product_prices(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    Update order price (cost) and selling price for a phone product.

    MANAGER-ONLY: Server-side permission check enforced.

    Security:
    - Manager-only (server-side check)
    - Business-scoped (product must belong to active business)
    - Validates price inputs (handles commas/spaces)
    - Rejects negative values
    - Warns (but allows) if selling_price < order_price (clearance sales)

    Returns JSON response:
    - Success: {"ok": true, "order_price": "...", "selling_price": "...", "message": "..."}
    - Error: {"ok": false, "error": "..."}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business selected"}, status=400)

    # SERVER-SIDE PERMISSION CHECK (not just template hiding)
    if not is_manager(request.user, business):
        return JsonResponse({"ok": False, "error": "Manager access required"}, status=403)

    # Get product (must belong to business)
    try:
        product = PhoneProductCatalog.objects.get(id=product_id, business=business)
    except PhoneProductCatalog.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Product not found or does not belong to your business"}, status=404)

    # Parse and validate prices
    order_price_str = request.POST.get("order_price", "").strip()
    selling_price_str = request.POST.get("selling_price", "").strip()

    errors = []
    order_price = None
    selling_price = None

    # Parse order price
    if order_price_str:
        try:
            order_price = _parse_price_input(order_price_str)
        except ValueError as e:
            errors.append(f"Order price: {str(e)}")

    # Parse selling price
    if selling_price_str:
        try:
            selling_price = _parse_price_input(selling_price_str)
        except ValueError as e:
            errors.append(f"Selling price: {str(e)}")

    if errors:
        return JsonResponse({"ok": False, "error": "; ".join(errors)}, status=400)

    # At least one price must be provided
    if order_price is None and selling_price is None:
        return JsonResponse({"ok": False, "error": "At least one price must be provided"}, status=400)

    # Warn if selling_price < order_price (but allow it for clearance sales)
    warning = None
    if order_price is not None and selling_price is not None:
        if selling_price < order_price:
            warning = "Selling price is below order price. This may be intentional for clearance sales."

    # Update product atomically
    try:
        with transaction.atomic():
            old_order_price = product.default_cost_price
            old_selling_price = product.default_selling_price

            if order_price is not None:
                product.default_cost_price = order_price
            if selling_price is not None:
                product.default_selling_price = selling_price

            product.save(update_fields=["default_cost_price", "default_selling_price", "updated_at"])

            # TODO: If audit log system exists, log the change here
            # Example:
            # audit_log_price_change(
            #     product=product,
            #     user=request.user,
            #     business=business,
            #     old_order_price=old_order_price,
            #     new_order_price=product.default_cost_price,
            #     old_selling_price=old_selling_price,
            #     new_selling_price=product.default_selling_price,
            # )

            response_data = {
                "ok": True,
                "order_price": str(product.default_cost_price) if product.default_cost_price else None,
                "selling_price": str(product.default_selling_price) if product.default_selling_price else None,
                "message": "Prices updated successfully",
            }

            if warning:
                response_data["warning"] = warning

            return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Error updating prices: {str(e)}"}, status=500)


# =============================================================================
# LAPTOP / DESKTOP: Add Products (specs + optional photo)
# =============================================================================
ELECTRONICS_BRANDS_LAPTOP = [
    {"key": "dell", "name": "Dell", "display": "Dell", "color": "#007DB8"},
    {"key": "lenovo", "name": "Lenovo", "display": "Lenovo", "color": "#E2231A"},
    {"key": "apple", "name": "Apple", "display": "Apple", "color": "#555555"},
    {"key": "hp", "name": "HP", "display": "HP", "color": "#0096D6"},
    {"key": "samsung", "name": "Samsung", "display": "Samsung", "color": "#1428A0"},
    {"key": "toshiba", "name": "Toshiba", "display": "Toshiba", "color": "#FF0000"},
    {"key": "acer", "name": "Acer", "display": "Acer", "color": "#83B81A"},
    {"key": "asus", "name": "Asus", "display": "Asus", "color": "#00529B"},
]


def _get_electronics_brand_config(brand_key: str) -> Dict[str, Any] | None:
    for b in ELECTRONICS_BRANDS_LAPTOP:
        if b["key"].lower() == brand_key.lower():
            return b
    return None


@login_required
@require_business
@manager_required
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def add_laptop_products(request: HttpRequest) -> HttpResponse:
    """Add laptop catalog products (specs form, optional photo). Same UX style as phones."""
    return _add_electronics_products(request, ElectronicsCategory.LAPTOP)


@login_required
@require_business
@manager_required
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def add_desktop_products(request: HttpRequest) -> HttpResponse:
    """Add desktop catalog products (specs form, optional photo). Same UX style as phones."""
    return _add_electronics_products(request, ElectronicsCategory.DESKTOP)


def _add_electronics_products(request: HttpRequest, category: str) -> HttpResponse:
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    if request.method == "POST":
        brand_key = request.POST.get("brand", "").strip()
        model_name = request.POST.get("model_name", "").strip()
        cpu = request.POST.get("cpu", "").strip()
        ram_str = request.POST.get("ram_str", "").strip()
        storage_str = request.POST.get("storage_str", "").strip()
        screen_size = request.POST.get("screen_size", "").strip()
        gpu = request.POST.get("gpu", "").strip()
        os = request.POST.get("os", "").strip()
        condition = request.POST.get("condition", "").strip()
        cost_str = request.POST.get("order_price", "").strip()
        selling_str = request.POST.get("selling_price", "").strip()

        brand_config = _get_electronics_brand_config(brand_key)
        if not brand_config:
            messages.error(request, "Invalid brand selected.")
            return redirect(request.path)

        if not model_name:
            messages.error(request, "Model name is required.")
            return redirect(request.path)

        order_price = None
        if cost_str:
            try:
                order_price = Decimal(cost_str.replace(",", "").replace(" ", ""))
                if order_price < 0:
                    raise ValueError("negative")
            except (ValueError, Exception):
                messages.error(request, "Invalid order price.")
                return redirect(request.path)

        selling_price = None
        if selling_str:
            try:
                selling_price = Decimal(selling_str.replace(",", "").replace(" ", ""))
                if selling_price < 0:
                    raise ValueError("negative")
            except (ValueError, Exception):
                messages.error(request, "Invalid selling price.")
                return redirect(request.path)

        main_image = request.FILES.get("main_image")

        try:
            with transaction.atomic():
                product, created = PhoneProductCatalog.objects.update_or_create(
                    business=business,
                    category=category,
                    brand=brand_config["display"],
                    model_name=model_name,
                    ram_gb=0,
                    rom_gb=0,
                    ram_str=ram_str or "",
                    storage_str=storage_str or "",
                    defaults={
                        "cpu": cpu,
                        "screen_size": screen_size,
                        "gpu": gpu,
                        "os": os,
                        "condition": condition,
                        "default_cost_price": order_price,
                        "default_selling_price": selling_price,
                        "is_active": True,
                        "created_by": request.user,
                    },
                )
                if main_image:
                    product.main_image = main_image
                    product.save(update_fields=["main_image", "updated_at"])

                if created:
                    messages.success(request, f"✅ Added {product.display_name} to catalog.")
                else:
                    messages.info(request, f"📝 Updated {product.display_name}.")
        except Exception as e:
            messages.error(request, f"Error saving product: {e}")

        if category == ElectronicsCategory.LAPTOP:
            return redirect("inventory:laptop_products")
        return redirect("inventory:desktop_products")

    # GET: ensure seed then show form
    try:
        from inventory.electronics_catalog_seed import seed_laptop_desktop_catalog
        seed_laptop_desktop_catalog(business, category, created_by=request.user)
    except Exception:
        pass

    from inventory.models_phone_products import ElectronicsStockItem as _ESI
    recent_qs = list(
        PhoneProductCatalog.objects.filter(
            business=business, category=category, is_active=True
        ).order_by("-created_at")[:20]
    )
    # annotate in-stock count per catalog product (batch query)
    product_ids = [m.id for m in recent_qs]
    stock_counts: dict = {}
    if product_ids:
        from django.db.models import Count as _Count
        for row in _ESI.objects.filter(
            catalog_product_id__in=product_ids, status="IN_STOCK", is_active=True
        ).values("catalog_product_id").annotate(cnt=_Count("id")):
            stock_counts[row["catalog_product_id"]] = row["cnt"]
    for m in recent_qs:
        m.stock_count = stock_counts.get(m.id, 0)
    recent = recent_qs

    category_label = "Laptops" if category == ElectronicsCategory.LAPTOP else "Desktops"
    context = {
        "business": business,
        "category": category,
        "category_label": category_label,
        "brands": ELECTRONICS_BRANDS_LAPTOP,
        "recent_models": recent,
        "page_title": f"Add {category_label}",
    }

    return render(request, "inventory/add_product_electronics.html", context)


# =============================================================================
# Electronics (Laptop/Desktop) Stock In and Sell
# =============================================================================
@login_required
@require_business
@manager_required
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def electronics_stock_in(request: HttpRequest) -> HttpResponse:
    """Stock in a laptop or desktop by serial number. Creates ElectronicsStockItem."""
    from inventory.models_phone_products import ElectronicsStockItem
    from inventory.models import Location
    from tenants.scope import resolve_location_for_user

    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    location_id = resolve_location_for_user(request)
    location = None
    if location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    if not location:
        location = Location.default_for(business) if hasattr(Location, "default_for") else None
    if not location:
        try:
            location = Location.ensure_default_for_business(business)
        except Exception:
            pass
    if not location:
        messages.error(request, "No location available. Please create a location first.")
        return redirect("inventory:inventory_dashboard")

    if request.method == "POST":
        catalog_id = request.POST.get("catalog_id", "").strip()
        serial_number = request.POST.get("serial_number", "").strip()
        loc_id = request.POST.get("location_id", "").strip()
        order_price_str = request.POST.get("order_price", "0").strip()
        selling_price_str = request.POST.get("selling_price", "").strip()

        if not catalog_id or not serial_number:
            messages.error(request, "Product and serial number are required.")
            return redirect("inventory:electronics_stock_in")

        try:
            catalog_product = PhoneProductCatalog.objects.get(
                pk=int(catalog_id),
                business=business,
                category__in=[ElectronicsCategory.LAPTOP, ElectronicsCategory.DESKTOP],
                is_active=True,
            )
        except (PhoneProductCatalog.DoesNotExist, ValueError):
            messages.error(request, "Invalid product selected.")
            return redirect("inventory:electronics_stock_in")

        if ElectronicsStockItem.objects.filter(
            business=business, serial_number=serial_number, is_active=True
        ).exists():
            messages.error(request, f"Serial number '{serial_number[:30]}...' already exists. Use a unique serial.")
            return redirect("inventory:electronics_stock_in")

        try:
            order_price = Decimal(order_price_str.replace(",", "").replace(" ", "")) if order_price_str else Decimal("0")
            selling_price = None
            if selling_price_str:
                selling_price = Decimal(selling_price_str.replace(",", "").replace(" ", ""))
        except Exception:
            messages.error(request, "Invalid price format.")
            return redirect("inventory:electronics_stock_in")

        loc = location
        if loc_id:
            try:
                loc = Location.objects.get(pk=int(loc_id), business=business)
            except (Location.DoesNotExist, ValueError):
                pass

        if not loc:
            messages.error(request, "Please select a location.")
            return redirect("inventory:electronics_stock_in")

        try:
            with transaction.atomic():
                ElectronicsStockItem.objects.create(
                    business=business,
                    catalog_product=catalog_product,
                    serial_number=serial_number,
                    current_location=loc,
                    order_price=order_price,
                    selling_price=selling_price or catalog_product.default_selling_price,
                    status="IN_STOCK",
                    is_active=True,
                )
            messages.success(request, f"✅ {catalog_product.display_name} (SN: {serial_number[:20]}...) stocked.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect("inventory:electronics_stock_in")

    catalog_products = list(
        PhoneProductCatalog.objects.filter(
            business=business,
            category__in=[ElectronicsCategory.LAPTOP, ElectronicsCategory.DESKTOP],
            is_active=True,
        ).order_by("category", "brand", "model_name")[:200]
    )
    locations = list(Location.objects.filter(business=business).order_by("name")[:50])

    context = {
        "business": business,
        "catalog_products": catalog_products,
        "locations": locations,
        "default_location": location,
        "page_title": "Stock In Laptop / Desktop",
    }
    return render(request, "inventory/electronics_stock_in.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def electronics_sell(request: HttpRequest) -> HttpResponse:
    """Sell a laptop or desktop by selecting an in-stock item (by serial or list)."""
    from inventory.models_phone_products import ElectronicsStockItem
    from django.utils import timezone

    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    if request.method == "POST":
        item_id = request.POST.get("item_id", "").strip()
        if not item_id:
            messages.error(request, "Please select an item to sell.")
            return redirect("inventory:electronics_sell")

        try:
            item = ElectronicsStockItem.objects.get(
                pk=int(item_id),
                business=business,
                status="IN_STOCK",
                is_active=True,
            )
        except (ElectronicsStockItem.DoesNotExist, ValueError):
            messages.error(request, "Item not found or already sold.")
            return redirect("inventory:electronics_sell")

        # Optionally update selling price if provided at sell time
        sell_price_str = request.POST.get("selling_price_display", "").strip()
        update_fields = ["status", "sold_at", "sold_by", "updated_at"]
        if sell_price_str:
            try:
                item.selling_price = Decimal(sell_price_str.replace(",", "").replace(" ", ""))
                update_fields.append("selling_price")
            except Exception:
                pass

        with transaction.atomic():
            item.status = "SOLD"
            item.sold_at = timezone.now()
            item.sold_by = request.user
            item.save(update_fields=update_fields)

        messages.success(request, f"✅ Sold: {item.catalog_product.display_name} (SN: {item.serial_number[:20]}...)")
        return redirect("inventory:electronics_sell")

    available = list(
        ElectronicsStockItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
        ).select_related("catalog_product", "current_location").order_by("catalog_product__brand", "catalog_product__model_name")
    )

    context = {
        "business": business,
        "available_items": available,
        "page_title": "Sell Laptop / Desktop",
    }
    return render(request, "inventory/electronics_sell.html", context)
