# inventory/views_electronics_unified.py
"""
Unified Scan IN and Scan & Sell for Phones, Laptops, Desktops.

Category selector at top, then:
- Phones: redirect to existing phone flows (unchanged)
- Laptops/Desktops: electronics stock-in and sell flows
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from tenants.utils import get_active_business, require_business
from tenants.scope import resolve_location_for_user
from inventory.models_phone_products import (
    PhoneProductCatalog,
    ElectronicsStockItem,
    ElectronicsCategory,
)
from inventory.business_kinds import BusinessKind

# Valid category values
VALID_CATEGORIES = ("phones", "laptops", "desktops")


def _get_category(request: HttpRequest) -> str:
    """Get category from query param or session. Default phones."""
    cat = (request.GET.get("category") or "").strip().lower()
    if cat in VALID_CATEGORIES:
        request.session["electronics_scan_category"] = cat
        return cat
    cat = (request.session.get("electronics_scan_category") or "phones").strip().lower()
    return cat if cat in VALID_CATEGORIES else "phones"


def _build_scan_in_url(category: str) -> str:
    return f"{reverse('inventory:scan_in')}?category={category}"


def _build_scan_sell_url(category: str) -> str:
    return f"{reverse('inventory:scan_sell')}?category={category}"


# =============================================================================
# SCAN IN UNIFIED
# =============================================================================
@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
def scan_in_unified(request: HttpRequest) -> HttpResponse:
    """
    Unified Scan IN: category selector (Phones / Laptops / Desktops).
    - Phones: redirect to phone_scan_in (exact existing flow)
    - Laptops/Desktops: electronics stock-in flow
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    category = _get_category(request)

    # Phones: use existing phone scan-in (unchanged); pass flag to show category selector
    if category == "phones":
        request._show_electronics_category_selector = True
        request._electronics_scan_in_url = reverse("inventory:scan_in")
        from inventory.views_phones import phone_scan_in
        return phone_scan_in(request)

    # Laptops/Desktops: electronics stock-in (PHONES biz only)
    return _electronics_stock_in_view(request, category)


def _electronics_stock_in_view(request: HttpRequest, category: str) -> HttpResponse:
    """Handle laptops/desktops stock-in. Supports batch serial entry."""
    from inventory.models import Location

    business = get_active_business(request)
    if not business:
        return redirect("tenants:activate_mine")

    # Require PHONES business kind for electronics (phones vertical includes laptops/desktops)
    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        messages.warning(request, "Electronics stock-in is for phone/electronics businesses.")
        return redirect("inventory:inventory_dashboard")

    location_id = resolve_location_for_user(request)
    location = None
    if location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    if not location:
        location = getattr(Location, "default_for", lambda b: None)(business)
    if not location:
        try:
            location = Location.ensure_default_for_business(business)
        except Exception:
            pass
    if not location:
        messages.error(request, "No location available. Please create a location first.")
        return redirect("inventory:inventory_dashboard")

    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    category_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        catalog_id = request.POST.get("catalog_id", "").strip()
        serial_numbers_raw = request.POST.get("serial_numbers", "").strip()
        loc_id = request.POST.get("location_id", "").strip()
        order_price_str = request.POST.get("order_price", "0").strip()
        selling_price_str = request.POST.get("selling_price", "").strip()

        if not catalog_id:
            messages.error(request, "Please select a model.")
            return redirect(_build_scan_in_url(category))

        # Parse serial numbers (comma/newline separated)
        serials = [
            s.strip()
            for s in serial_numbers_raw.replace("\n", ",").split(",")
            if s.strip()
        ]
        if not serials:
            messages.error(request, "At least one serial number is required.")
            return redirect(_build_scan_in_url(category))

        try:
            catalog_product = PhoneProductCatalog.objects.get(
                pk=int(catalog_id),
                business=business,
                category=cat_filter,
                is_active=True,
            )
        except (PhoneProductCatalog.DoesNotExist, ValueError):
            messages.error(request, "Invalid product selected.")
            return redirect(_build_scan_in_url(category))

        # Check duplicates
        for sn in serials:
            if ElectronicsStockItem.objects.filter(
                business=business, serial_number=sn, is_active=True
            ).exists():
                messages.error(
                    request,
                    f"Serial '{sn[:30]}{'...' if len(sn) > 30 else ''}' already exists.",
                )
                return redirect(_build_scan_in_url(category))

        try:
            order_price = (
                Decimal(order_price_str.replace(",", "").replace(" ", ""))
                if order_price_str
                else Decimal("0")
            )
            selling_price = None
            if selling_price_str:
                selling_price = Decimal(
                    selling_price_str.replace(",", "").replace(" ", "")
                )
        except Exception:
            messages.error(request, "Invalid price format.")
            return redirect(_build_scan_in_url(category))

        loc = location
        if loc_id:
            try:
                loc = Location.objects.get(pk=int(loc_id), business=business)
            except (Location.DoesNotExist, ValueError):
                pass

        if not loc:
            messages.error(request, "Please select a location.")
            return redirect(_build_scan_in_url(category))

        try:
            with transaction.atomic():
                for sn in serials:
                    ElectronicsStockItem.objects.create(
                        business=business,
                        catalog_product=catalog_product,
                        serial_number=sn,
                        current_location=loc,
                        order_price=order_price,
                        selling_price=selling_price or catalog_product.default_selling_price,
                        status="IN_STOCK",
                        is_active=True,
                    )
            msg = f"✅ {len(serials)} unit(s) of {catalog_product.display_name} stocked."
            messages.success(request, msg)
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect(_build_scan_in_url(category))

    # GET: show form
    catalog_products = list(
        PhoneProductCatalog.objects.filter(
            business=business,
            category=cat_filter,
            is_active=True,
        )
        .order_by("brand", "model_name")[:200]
    )
    locations = list(Location.objects.filter(business=business).order_by("name")[:50])

    context = {
        "business": business,
        "catalog_products": catalog_products,
        "locations": locations,
        "default_location": location,
        "category": category,
        "category_label": category_label,
        "page_title": f"Scan In {category_label}",
        "scan_in_url": reverse("inventory:scan_in"),
        "add_laptops_url": reverse("inventory:laptop_products"),
        "add_desktops_url": reverse("inventory:desktop_products"),
        "active_tab": "scan_in",
    }
    return render(request, "inventory/scan_in_unified.html", context)


# =============================================================================
# SCAN & SELL UNIFIED
# =============================================================================
@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
def scan_sell_unified(request: HttpRequest) -> HttpResponse:
    """
    Unified Scan & Sell: category selector.
    - Phones: phone_scan_sell (PHONES biz) or legacy scan_sold (other biz)
    - Laptops/Desktops: electronics sell flow with margin warnings (PHONES only)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    category = _get_category(request)

    # Phones: use existing phone scan-sell for PHONES biz, else legacy scan_sold
    if category == "phones":
        if getattr(business, "business_kind", None) == BusinessKind.PHONES:
            request._show_electronics_category_selector = True
            request._electronics_scan_sell_url = reverse("inventory:scan_sell")
            from inventory.views_phones import phone_scan_sell
            return phone_scan_sell(request)
        # Non-PHONES: use legacy scan_sold
        from inventory.views import scan_sold
        return scan_sold(request)

    # Laptops/Desktops: redirect to gamified sale wizard
    if category == "laptops":
        return redirect(reverse("inventory:laptop_sale_wizard"))
    return redirect(reverse("inventory:desktop_sale_wizard"))


# =============================================================================
# SCAN & SELL LANDING PAGE
# =============================================================================
@never_cache
@login_required
@require_business
@require_http_methods(["GET"])
def scan_sell_landing(request: HttpRequest) -> HttpResponse:
    """
    Polished Scan & Sell category landing page.
    Shows three cards: Phones, Laptops, Desktops.
    Phones → existing phone-sale-wizard (unchanged).
    Laptops → laptop-sale-wizard.
    Desktops → desktop-sale-wizard.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    context = {
        "business": business,
        "phone_wizard_url": reverse("inventory:phone_sale_wizard"),
        "laptop_wizard_url": reverse("inventory:laptop_sale_wizard"),
        "desktop_wizard_url": reverse("inventory:desktop_sale_wizard"),
        "scan_in_url": reverse("inventory:scan_in"),
        "stock_list_url": reverse("inventory:stock_list"),
        "page_title": "Scan & Sell",
    }
    return render(request, "inventory/scan_sell_landing.html", context)


def _electronics_sell_view(request: HttpRequest, category: str) -> HttpResponse:
    """Handle laptops/desktops sell with margin warnings."""
    business = get_active_business(request)
    if not business:
        return redirect("tenants:activate_mine")

    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        messages.warning(request, "Electronics sell is for phone/electronics businesses.")
        return redirect("inventory:inventory_dashboard")

    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    category_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        item_id = request.POST.get("item_id", "").strip()
        if not item_id:
            messages.error(request, "Please select an item to sell.")
            return redirect(_build_scan_sell_url(category))

        try:
            item = ElectronicsStockItem.objects.get(
                pk=int(item_id),
                business=business,
                status="IN_STOCK",
                is_active=True,
            )
        except (ElectronicsStockItem.DoesNotExist, ValueError):
            messages.error(request, "Item not found or already sold.")
            return redirect(_build_scan_sell_url(category))

        sell_price_str = request.POST.get("selling_price_display", "").strip()
        update_fields = ["status", "sold_at", "sold_by", "updated_at"]
        if sell_price_str:
            try:
                item.selling_price = Decimal(
                    sell_price_str.replace(",", "").replace(" ", "")
                )
                update_fields.append("selling_price")
            except Exception:
                pass

        with transaction.atomic():
            item.status = "SOLD"
            item.sold_at = timezone.now()
            item.sold_by = request.user
            item.save(update_fields=update_fields)

        messages.success(
            request,
            f"✅ Sold: {item.catalog_product.display_name} (SN: {item.serial_number[:20]}...)",
        )
        return redirect(_build_scan_sell_url(category))

    # GET: list available items (filter by category)
    available = list(
        ElectronicsStockItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
            catalog_product__category=cat_filter,
        )
        .select_related("catalog_product", "current_location")
        .order_by("catalog_product__brand", "catalog_product__model_name")
    )

    context = {
        "business": business,
        "available_items": available,
        "category": category,
        "category_label": category_label,
        "page_title": f"Sell {category_label}",
        "scan_sell_url": reverse("inventory:scan_sell"),
        "scan_in_url": reverse("inventory:scan_in"),
        "electronics_stock_in_url": reverse("inventory:electronics_stock_in"),
        "active_tab": "scan_sold",
    }
    return render(request, "inventory/scan_sell_unified.html", context)
