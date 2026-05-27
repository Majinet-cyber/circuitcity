# inventory/views_electronics_sale_wizard.py
"""
Gamified 5-step Electronics Sale Wizard for Laptops and Desktops.

Mirrors the phone sale wizard (views_phone_sale_wizard_v2.py) pattern:
- Session-based state management
- Stepper/progress indicator
- Steps locked until valid data entered
- Atomic sale completion

Steps:
  1) Brand    – only brands with at least 1 in-stock unit for this category
  2) Model    – only models with count > 0; shows "In stock: N"
  3) Unit     – select/enter serial number; validated IN_STOCK
  4) Price    – cost + selling price with live margin warnings
  5) Payment  – CASH / MOBILE_MONEY / BANK; must choose one
  6) Confirm  – atomic: mark SOLD, save payment_method, create audit log if available
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from tenants.utils import get_active_business, require_business
from inventory.models_phone_products import (
    ElectronicsCategory,
    ElectronicsStockItem,
    PhoneProductCatalog,
)

WIZARD_SESSION_KEY = "electronics_sale_wizard"
VALID_PAYMENT_METHODS = ["CASH", "MOBILE_MONEY", "BANK"]
PAYMENT_METHOD_LABELS = {
    "CASH": "Cash",
    "MOBILE_MONEY": "Mobile Money",
    "BANK": "Bank Transfer",
}
# Margin threshold below which we warn (10%)
LOW_MARGIN_THRESHOLD = Decimal("10")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _clear_wizard(request: HttpRequest) -> None:
    if WIZARD_SESSION_KEY in request.session:
        del request.session[WIZARD_SESSION_KEY]
        request.session.modified = True


def _get_data(request: HttpRequest) -> dict:
    return request.session.get(WIZARD_SESSION_KEY, {})


def _save_data(request: HttpRequest, data: dict) -> None:
    request.session[WIZARD_SESSION_KEY] = data
    request.session.modified = True


def _wizard_url(category: str, step: int | None = None) -> str:
    slug = "laptop" if category == "laptops" else "desktop"
    url = reverse(f"inventory:{slug}_sale_wizard")
    if step:
        url += f"?step={step}"
    return url


def _reset_url(category: str) -> str:
    slug = "laptop" if category == "laptops" else "desktop"
    return reverse(f"inventory:{slug}_sale_wizard_reset")


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
def laptop_sale_wizard(request: HttpRequest) -> HttpResponse:
    return _electronics_wizard(request, "laptops")


@never_cache
@login_required
@require_business
@require_http_methods(["GET", "POST"])
def desktop_sale_wizard(request: HttpRequest) -> HttpResponse:
    return _electronics_wizard(request, "desktops")


@login_required
@require_business
@require_POST
def laptop_sale_wizard_reset(request: HttpRequest) -> HttpResponse:
    _clear_wizard(request)
    return redirect(reverse("inventory:laptop_sale_wizard"))


@login_required
@require_business
@require_POST
def desktop_sale_wizard_reset(request: HttpRequest) -> HttpResponse:
    _clear_wizard(request)
    return redirect(reverse("inventory:desktop_sale_wizard"))


def _electronics_wizard(request: HttpRequest, category: str) -> HttpResponse:
    """Route to correct wizard step."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("tenants:activate_mine")

    data = _get_data(request)
    # Reset if category changed
    if data.get("category") and data["category"] != category:
        _clear_wizard(request)
        data = {}

    step = int(request.GET.get("step", data.get("step", 1)))
    data["category"] = category

    if step == 1:
        return _step1_brand(request, business, category, data)
    elif step == 2:
        return _step2_model(request, business, category, data)
    elif step == 3:
        return _step3_unit(request, business, category, data)
    elif step == 4:
        return _step4_price(request, business, category, data)
    elif step == 5:
        return _step5_payment(request, business, category, data)
    else:
        _clear_wizard(request)
        return redirect(_wizard_url(category, 1))


# ---------------------------------------------------------------------------
# Step 1 – Brand selection
# ---------------------------------------------------------------------------

def _step1_brand(request: HttpRequest, business, category: str, data: dict) -> HttpResponse:
    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    cat_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        brand = request.POST.get("brand", "").strip()
        if not brand:
            messages.error(request, "Please select a brand.")
        else:
            data.update({"step": 2, "brand": brand})
            _save_data(request, data)
            return redirect(_wizard_url(category, 2))

    # Build brand list: only brands that have ≥1 in-stock unit
    from django.db.models import Count
    brands = (
        ElectronicsStockItem.objects
        .filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
            catalog_product__category=cat_filter,
        )
        .values("catalog_product__brand")
        .annotate(unit_count=Count("id"))
        .order_by("catalog_product__brand")
    )
    brand_list = [{"brand": r["catalog_product__brand"], "count": r["unit_count"]} for r in brands]

    ctx = _base_ctx(category, cat_label, 1, data)
    ctx["brand_list"] = brand_list
    ctx["empty"] = not brand_list
    return render(request, "inventory/electronics_sale_wizard.html", ctx)


# ---------------------------------------------------------------------------
# Step 2 – Model selection
# ---------------------------------------------------------------------------

def _step2_model(request: HttpRequest, business, category: str, data: dict) -> HttpResponse:
    if not data.get("brand"):
        return redirect(_wizard_url(category, 1))

    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    cat_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        catalog_id_str = request.POST.get("catalog_id", "").strip()
        try:
            catalog_id = int(catalog_id_str)
            catalog_product = PhoneProductCatalog.objects.get(
                pk=catalog_id, business=business, category=cat_filter, is_active=True
            )
        except (ValueError, PhoneProductCatalog.DoesNotExist):
            messages.error(request, "Invalid model selected. Please try again.")
            return redirect(_wizard_url(category, 2))

        # Confirm still has stock
        in_stock_count = ElectronicsStockItem.objects.filter(
            business=business,
            catalog_product=catalog_product,
            status="IN_STOCK",
            is_active=True,
        ).count()
        if in_stock_count == 0:
            messages.error(request, "No units in stock for this model. Choose another.")
            return redirect(_wizard_url(category, 2))

        data.update({
            "step": 3,
            "catalog_id": catalog_id,
            "catalog_display": catalog_product.display_name,
            "default_cost_price": float(catalog_product.default_cost_price or 0),
            "default_selling_price": float(catalog_product.default_selling_price or 0),
        })
        _save_data(request, data)
        return redirect(_wizard_url(category, 3))

    # GET: list models for this brand with stock counts
    from django.db.models import Count
    brand = data["brand"]
    models_qs = (
        ElectronicsStockItem.objects
        .filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
            catalog_product__category=cat_filter,
            catalog_product__brand=brand,
        )
        .values(
            "catalog_product__id",
            "catalog_product__model_name",
            "catalog_product__ram_str",
            "catalog_product__storage_str",
            "catalog_product__cpu",
            "catalog_product__screen_size",
        )
        .annotate(unit_count=Count("id"))
        .order_by("catalog_product__model_name")
    )
    model_list = [
        {
            "catalog_id": r["catalog_product__id"],
            "model_name": r["catalog_product__model_name"],
            "ram_str": r["catalog_product__ram_str"],
            "storage_str": r["catalog_product__storage_str"],
            "cpu": r["catalog_product__cpu"],
            "screen_size": r["catalog_product__screen_size"],
            "unit_count": r["unit_count"],
        }
        for r in models_qs
    ]

    ctx = _base_ctx(category, cat_label, 2, data)
    ctx["model_list"] = model_list
    ctx["brand"] = brand
    return render(request, "inventory/electronics_sale_wizard.html", ctx)


# ---------------------------------------------------------------------------
# Step 3 – Unit / serial selection
# ---------------------------------------------------------------------------

def _step3_unit(request: HttpRequest, business, category: str, data: dict) -> HttpResponse:
    if not data.get("catalog_id"):
        return redirect(_wizard_url(category, 1))

    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    cat_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        serial = request.POST.get("serial_number", "").strip()
        if not serial:
            messages.error(request, "Serial number is required.")
            return redirect(_wizard_url(category, 3))

        # Validate unit exists, is IN_STOCK, belongs to correct catalog product
        try:
            unit = ElectronicsStockItem.objects.select_related("catalog_product").get(
                business=business,
                serial_number=serial,
                catalog_product_id=data["catalog_id"],
                status="IN_STOCK",
                is_active=True,
            )
        except ElectronicsStockItem.DoesNotExist:
            # Maybe wrong catalog product but serial exists in business?
            other = ElectronicsStockItem.objects.filter(
                business=business, serial_number=serial, is_active=True
            ).first()
            if other and other.status == "SOLD":
                messages.error(request, f"Serial '{serial}' has already been sold.")
            elif other:
                messages.error(request, f"Serial '{serial}' belongs to a different model ({other.catalog_product.display_name}). Please select its correct brand/model.")
            else:
                messages.error(request, f"Serial '{serial}' not found in stock. Please check and try again.")
            return redirect(_wizard_url(category, 3))

        data.update({
            "step": 4,
            "unit_id": unit.id,
            "serial_number": serial,
            "unit_display": unit.display_name,
            "unit_cost_price": float(unit.order_price or 0),
            "unit_suggested_price": float(unit.selling_price or data.get("default_selling_price") or 0),
            "battery_health": unit.battery_health or "",
        })
        _save_data(request, data)
        return redirect(_wizard_url(category, 4))

    # GET: list available units for this catalog product
    units = list(
        ElectronicsStockItem.objects
        .filter(
            business=business,
            catalog_product_id=data["catalog_id"],
            status="IN_STOCK",
            is_active=True,
        )
        .select_related("catalog_product", "current_location")
        .order_by("serial_number")
    )

    ctx = _base_ctx(category, cat_label, 3, data)
    ctx["units"] = units
    ctx["catalog_display"] = data.get("catalog_display", "")
    return render(request, "inventory/electronics_sale_wizard.html", ctx)


# ---------------------------------------------------------------------------
# Step 4 – Price & margin
# ---------------------------------------------------------------------------

def _step4_price(request: HttpRequest, business, category: str, data: dict) -> HttpResponse:
    if not data.get("unit_id"):
        return redirect(_wizard_url(category, 1))

    cat_label = "Laptops" if category == "laptops" else "Desktops"
    cost = Decimal(str(data.get("unit_cost_price", 0)))
    suggested = Decimal(str(data.get("unit_suggested_price", 0)))

    if request.method == "POST":
        price_str = request.POST.get("selling_price", "").strip().replace(",", "")
        try:
            selling_price = Decimal(price_str)
        except InvalidOperation:
            messages.error(request, "Invalid price. Please enter a number.")
            return redirect(_wizard_url(category, 4))

        if selling_price <= 0:
            messages.error(request, "Price must be greater than zero.")
            return redirect(_wizard_url(category, 4))

        # Margin warnings (non-blocking for laptops/desktops)
        if cost > 0:
            margin_pct = (selling_price - cost) / cost * 100
            if selling_price < cost:
                messages.warning(
                    request,
                    f"⚠️ Selling price is below cost (MWK {cost:,.0f}). "
                    f"You are selling at a loss of MWK {cost - selling_price:,.0f}."
                )
            elif margin_pct < LOW_MARGIN_THRESHOLD:
                messages.warning(
                    request,
                    f"⚡ Low margin ({margin_pct:.1f}%). "
                    f"Consider at least MWK {cost * Decimal('1.10'):,.0f} for 10% margin."
                )

        data.update({
            "step": 5,
            "selling_price": float(selling_price),
        })
        _save_data(request, data)
        return redirect(_wizard_url(category, 5))

    ctx = _base_ctx(category, cat_label, 4, data)
    ctx["cost_price"] = cost
    ctx["suggested_price"] = suggested
    ctx["unit_display"] = data.get("unit_display", "")
    ctx["serial_number"] = data.get("serial_number", "")
    ctx["battery_health"] = data.get("battery_health", "")
    return render(request, "inventory/electronics_sale_wizard.html", ctx)


# ---------------------------------------------------------------------------
# Step 5 – Payment method
# ---------------------------------------------------------------------------

def _step5_payment(request: HttpRequest, business, category: str, data: dict) -> HttpResponse:
    if not data.get("selling_price"):
        return redirect(_wizard_url(category, 1))

    cat_label = "Laptops" if category == "laptops" else "Desktops"

    if request.method == "POST":
        payment_method = request.POST.get("payment_method", "").strip()
        if payment_method not in VALID_PAYMENT_METHODS:
            messages.error(request, "Please choose a valid payment method.")
            return redirect(_wizard_url(category, 5))

        # Execute sale
        try:
            result = _complete_sale(request, business, data, payment_method)
        except ValueError as exc:
            messages.error(request, f"❌ Sale failed: {exc}")
            return redirect(_wizard_url(category, 5))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Electronics sale error: %s", exc, exc_info=True)
            messages.error(request, "❌ An unexpected error occurred. Please try again.")
            return redirect(_wizard_url(category, 5))

        _clear_wizard(request)
        messages.success(
            request,
            f"🎉 Sale complete! {result['unit_display']} sold for "
            f"MWK {result['selling_price']:,.0f} via {PAYMENT_METHOD_LABELS.get(payment_method, payment_method)}."
        )
        return redirect("inventory_verticals:phones_dashboard")

    ctx = _base_ctx(category, cat_label, 5, data)
    ctx["payment_methods"] = [
        {"value": "CASH", "label": "Cash", "icon": "💵"},
        {"value": "MOBILE_MONEY", "label": "Mobile Money", "icon": "📱"},
        {"value": "BANK", "label": "Bank Transfer", "icon": "🏦"},
    ]
    ctx["selling_price"] = Decimal(str(data.get("selling_price", 0)))
    ctx["unit_display"] = data.get("unit_display", "")
    ctx["serial_number"] = data.get("serial_number", "")
    return render(request, "inventory/electronics_sale_wizard.html", ctx)


# ---------------------------------------------------------------------------
# Sale completion (atomic)
# ---------------------------------------------------------------------------

@transaction.atomic
def _complete_sale(request: HttpRequest, business, data: dict, payment_method: str) -> dict:
    """
    Complete the electronics sale atomically:
    1. Lock the unit (select_for_update)
    2. Validate still IN_STOCK
    3. Mark SOLD with payment_method, sold_at, sold_by, selling_price
    4. Return result dict
    """
    unit_id = data["unit_id"]
    selling_price = Decimal(str(data["selling_price"]))

    try:
        unit = ElectronicsStockItem.objects.select_for_update().select_related(
            "catalog_product"
        ).get(pk=unit_id, business=business)
    except ElectronicsStockItem.DoesNotExist:
        raise ValueError("Unit not found. It may have been removed.")

    if unit.status != "IN_STOCK":
        raise ValueError(
            f"This unit is no longer available (status: {unit.status}). "
            "It may have been sold by another agent."
        )

    unit.status = "SOLD"
    unit.sold_at = timezone.now()
    unit.sold_by = request.user
    unit.selling_price = selling_price
    unit.payment_method = payment_method
    unit.save(update_fields=[
        "status", "sold_at", "sold_by", "selling_price", "payment_method", "updated_at"
    ])

    return {
        "unit_id": unit.id,
        "unit_display": unit.display_name,
        "serial_number": unit.serial_number,
        "selling_price": selling_price,
        "cost_price": unit.order_price,
        "payment_method": payment_method,
    }


# ---------------------------------------------------------------------------
# Context helper
# ---------------------------------------------------------------------------

def _base_ctx(category: str, cat_label: str, step: int, data: dict) -> dict:
    slug = "laptop" if category == "laptops" else "desktop"
    return {
        "category": category,
        "cat_label": cat_label,
        "cat_icon": "💻" if category == "laptops" else "🖥️",
        "current_step": step,
        "total_steps": 5,
        "wizard_data": data,
        "reset_url": reverse(f"inventory:{slug}_sale_wizard_reset"),
        "scan_sell_url": reverse("inventory:scan_sell"),
        "steps": [
            {"num": 1, "label": "Brand"},
            {"num": 2, "label": "Model"},
            {"num": 3, "label": "Unit"},
            {"num": 4, "label": "Price"},
            {"num": 5, "label": "Payment"},
        ],
    }
