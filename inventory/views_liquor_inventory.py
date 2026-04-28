# inventory/views_liquor_inventory.py
"""
Liquor Inventory Dashboard with category-based "stock batteries"
"""
from __future__ import annotations

import logging
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

try:
    from cc.services.email_dispatcher import send_event_email, EmailEvent
except ImportError:
    send_event_email = None  # type: ignore[assignment]
    EmailEvent = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


LOW_STOCK_THRESHOLD = 10  # bottles — alert when stock drops to this or below


def _get_manager_email(business) -> str | None:
    """Get the manager/owner email for a business."""
    try:
        # Try to get manager email from membership
        from tenants.models import Membership
        mgr = Membership.objects.filter(business=business, role__in=["manager", "owner"]).select_related("user").first()
        if mgr and mgr.user and mgr.user.email:
            return mgr.user.email
    except Exception:
        pass
    # Fallback to business owner
    try:
        if hasattr(business, "owner") and business.owner and business.owner.email:
            return business.owner.email
    except Exception:
        pass
    return None


def _send_stock_alert_if_needed(product, business) -> None:
    """Send low-stock or out-of-stock email alert if threshold crossed."""
    current_qty = product.quantity_in_stock or 0
    if current_qty > LOW_STOCK_THRESHOLD:
        return  # Stock is fine, no alert needed

    manager_email = _get_manager_email(business)
    if not manager_email:
        logger.warning(f"No manager email found for business {business.id}, skipping stock alert")
        return

    try:
        from cc.services.email_dispatcher import send_event_email, EmailEvent
        if current_qty == 0:
            subject = f"🚨 OUT OF STOCK: {product.name} — {business.name}"
            alert_type = "out_of_stock"
            alert_msg = f"{product.name} is completely OUT OF STOCK."
        else:
            subject = f"⚠️ Low Stock Alert: {product.name} — {business.name}"
            alert_type = "low_stock"
            alert_msg = f"{product.name} is running LOW — only {current_qty} bottle(s) left."

        send_event_email(
            EmailEvent.IMPORTANT_ALERT,
            to=manager_email,
            context={
                "alert_title": f"Stock Alert: {product.name}",
                "alert_type": alert_type,
                "alert_message": alert_msg,
                "product_name": product.name,
                "product_category": product.category or "Unknown",
                "current_qty": current_qty,
                "threshold": LOW_STOCK_THRESHOLD,
                "business_name": business.name,
                "subject": subject,
            },
            business=business,
            force=True,
        )
        logger.info(f"Stock alert email sent for {product.name} (qty={current_qty}) to {manager_email}")
    except Exception as e:
        logger.error(f"Failed to send stock alert email for product {product.id}: {e}", exc_info=True)


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
        business=business, kind=BusinessKind.LIQUOR, is_active=True, category__iexact=category_key
    )

    # Get latest stock snapshots for these products
    # Subquery to get the most recent snapshot for each product
    latest_snapshots = LiquorShiftStock.objects.filter(product=OuterRef("pk"), shift__business=business).order_by(
        "-recorded_at"
    )

    # Calculate total stock from latest snapshots
    total_stock = 0
    products_with_stock = products.filter(track_inventory=True).annotate(
        latest_bottles=Subquery(latest_snapshots.values("bottles_count")[:1])
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

    all_liquor_products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True)

    total_skus = all_liquor_products.count()

    # Get latest stock snapshots
    latest_snapshots = LiquorShiftStock.objects.filter(product=OuterRef("pk"), shift__business=business).order_by(
        "-recorded_at"
    )

    # Calculate total stock from latest snapshots
    total_stock = 0
    products_with_stock = all_liquor_products.filter(track_inventory=True).annotate(
        latest_bottles=Subquery(latest_snapshots.values("bottles_count")[:1])
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
    if request.GET.get("added") == "1":
        messages.success(request, "✅ Stock added successfully! Add another product below.")

    if request.method == "POST":
        # POST logic: process stock-in
        try:
            product_id = int(request.POST.get("product_id", 0))
            quantity = int(request.POST.get("quantity", 1))
            unit_type = request.POST.get("unit_type", "bottle")  # "bottle", "crate", or "pack"
            cost_per_unit = Decimal(request.POST.get("cost_per_unit", "0.00"))

            product = MerchProduct.objects.get(
                pk=product_id, business=business, kind=BusinessKind.LIQUOR, is_active=True
            )

            # VALIDATION: Spirits cannot use crates
            if unit_type == "crate" and product.category in ["spirits", "whiskey"]:
                messages.error(request, "❌ Spirits cannot be stocked in crates. Please use bottles.")
                return redirect("liquor:scan_in")

            # Calculate actual bottles to add
            bottles_to_add = quantity
            bottles_per_crate = product.bottles_per_crate or 20

            if unit_type == "crate":
                bottles_to_add = quantity * bottles_per_crate
            elif unit_type == "pack":
                # Cider pack mode
                pack_size_raw = request.POST.get("pack_size", "6").strip()
                try:
                    pack_size = int(pack_size_raw)
                    if pack_size <= 0:
                        raise ValueError("Pack size must be > 0")
                except (ValueError, TypeError):
                    messages.error(request, "❌ Invalid pack size.")
                    return redirect("liquor:scan_in")
                bottles_to_add = quantity * pack_size
                # cost_per_unit is cost per pack; derive cost per bottle
                cost_per_bottle_from_pack = cost_per_unit / Decimal(pack_size) if cost_per_unit > 0 else Decimal("0.00")
                cost_per_unit = cost_per_bottle_from_pack  # reuse variable for unified path

            # Calculate cost per bottle (always store in per-bottle terms)
            cost_per_bottle = cost_per_unit
            if unit_type == "crate" and cost_per_unit > 0:
                cost_per_bottle = cost_per_unit / Decimal(bottles_per_crate)

            with transaction.atomic():
                # Update product stock (in bottles)
                product.quantity_in_stock = (product.quantity_in_stock or 0) + bottles_to_add

                # Store cost per bottle (single source of truth)
                if cost_per_bottle > 0:
                    product.cost_per_bottle = cost_per_bottle

                # Update selling price per bottle (canonical price — ALWAYS per bottle, never per crate)
                selling_price_raw = request.POST.get("selling_price", "").strip()
                selling_price = None
                if selling_price_raw:
                    try:
                        selling_price = Decimal(selling_price_raw)
                        if selling_price < 0:
                            raise ValueError("Selling price cannot be negative")
                        if selling_price > 0:
                            product.price_per_bottle = selling_price
                        else:
                            selling_price = None
                    except (ValueError, Exception):
                        selling_price = None

                # Handle spirits shots pricing (bottle-first approach)
                shots_per_bottle_raw = request.POST.get("shots_per_bottle", "").strip()
                price_per_shot_raw = request.POST.get("price_per_shot", "").strip()

                if product.category in ["spirits", "whiskey"] and shots_per_bottle_raw and price_per_shot_raw:
                    try:
                        shots_per_bottle = int(shots_per_bottle_raw)
                        price_per_shot = Decimal(price_per_shot_raw)

                        if shots_per_bottle <= 0:
                            raise ValueError("Shots per bottle must be greater than 0 for spirits sold by shot")
                        if price_per_shot < 0:
                            raise ValueError("Selling price per shot cannot be negative")

                        product.has_shots = True
                        product.shots_per_bottle = shots_per_bottle
                        if price_per_shot > 0:
                            product.price_per_shot = price_per_shot

                        # Compute cost per shot
                        if cost_per_bottle > 0:
                            product.cost_per_shot = cost_per_bottle / Decimal(shots_per_bottle)
                    except ValueError as ve:
                        messages.error(request, f"❌ Shots pricing error: {ve}")
                        return redirect("liquor:scan_in")
                    except Exception:
                        pass

                product.save()

                # Record LiquorStockInTransaction for COGS/history tracking
                from inventory.models_verticals import LiquorStockInTransaction
                total_cost_calc = cost_per_bottle * Decimal(bottles_to_add) if cost_per_bottle > 0 else Decimal("0.00")
                if unit_type == "pack":
                    note_str = f"Scan-in: {quantity} pack(s) of {pack_size} ({bottles_to_add} bottles)"
                elif unit_type == "crate":
                    note_str = f"Scan-in: {quantity} crate(s) ({bottles_to_add} bottles)"
                else:
                    note_str = f"Scan-in: {bottles_to_add} bottle(s)"
                LiquorStockInTransaction.objects.create(
                    business=business,
                    product=product,
                    quantity_added=bottles_to_add,
                    unit_cost=cost_per_bottle,
                    total_cost=total_cost_calc,
                    selling_price_at_time=selling_price,
                    created_by=request.user,
                    notes=note_str,
                )

                # Low stock / out-of-stock email alerts
                try:
                    _send_stock_alert_if_needed(product, business)
                except Exception as _email_err:
                    import logging as _log
                    _log.getLogger(__name__).error(
                        f"Stock alert email failed for product {product.id}: {_email_err}", exc_info=True
                    )

            # Build success message
            if unit_type == "crate":
                success_msg = f"✅ Added: {quantity} crate{'s' if quantity != 1 else ''} ({bottles_to_add} bottles) — {product.name}"
            elif unit_type == "pack":
                success_msg = f"✅ Added: {quantity} pack{'s' if quantity != 1 else ''} ({bottles_to_add} bottles) — {product.name}"
            else:
                success_msg = f"✅ Added: {bottles_to_add} bottle{'s' if bottles_to_add != 1 else ''} — {product.name}"

            # Add shots info if applicable
            if product.has_shots and product.shots_per_bottle:
                total_shots = bottles_to_add * product.shots_per_bottle
                success_msg += f" ({total_shots} shots)"

            messages.success(request, success_msg)
            return redirect("liquor:scan_in")

        except (ValueError, MerchProduct.DoesNotExist, KeyError) as e:
            messages.error(request, f"❌ Stock-in failed: {e}")
            return redirect("liquor:scan_in")

    # GET: Build category-grouped products
    products = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.LIQUOR, is_archived=False, is_active=True
    ).order_by("category", "name")

    products_by_category = defaultdict(list)
    for p in products:
        cat = (p.category or "").lower()
        if cat:
            products_by_category[cat].append(
                {
                    "id": p.id,
                    "name": p.name,
                    "quantity_in_stock": p.quantity_in_stock or 0,
                    "bottles_per_crate": p.bottles_per_crate or 20,  # MALAWI STANDARD: 20 bottles per crate
                    "pack_size": p.bottles_per_crate if cat == "cider" else None,  # 6 for ciders
                    "supports_crates": p.supports_crates,
                    "has_shots": p.has_shots,
                    "shots_per_bottle": p.shots_per_bottle,
                    "price_per_shot": float(p.price_per_shot) if p.price_per_shot else None,
                    "category": p.category,
                }
            )

    # Build categories list in order
    category_order = ["beer", "cider", "wine", "spirits", "whiskey"]
    categories = [cat for cat in category_order if cat in products_by_category]

    # Serialize products to JSON for JavaScript
    import json

    products_json = json.dumps(dict(products_by_category))

    return render(
        request,
        "verticals/liquor/scan_in.html",
        {
            "categories": categories,
            "products_by_category": products_json,
            "business": business,
            "active_tab": "scan_in",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_stock_list(request):
    """
    Liquor Stock List - Detailed view of liquor inventory.

    CRITICAL: This view is LIQUOR-ONLY. Phone businesses must NEVER access this.
    Supports filtering by category via ?category= param.
    """
    business = get_active_business(request)

    # Base queryset: liquor products for this business only
    products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True).select_related(
        "business"
    )

    # Category filter (if provided)
    category = request.GET.get("category", "").strip().lower()
    selected_category = None
    if category:
        products = products.filter(category__iexact=category)
        selected_category = category

    # Search filter (by name, SKU, barcode)
    search_query = request.GET.get("q", "").strip()
    if search_query:
        from django.db.models import Q

        products = products.filter(
            Q(name__icontains=search_query)
            | Q(sku__icontains=search_query)
            | Q(barcode__icontains=search_query)
            | Q(internal_sku__icontains=search_query)
        )

    # Sort by name
    products = products.order_by("category", "name")

    # Calculate aggregates
    total_products = products.count()
    total_quantity = sum(p.quantity_in_stock or 0 for p in products)

    # Cost and retail calculations
    total_cost_value = Decimal("0.00")
    total_retail_value = Decimal("0.00")

    for p in products:
        qty = p.quantity_in_stock or 0
        cost = p.cost_per_bottle or Decimal("0.00")
        price = p.price_per_bottle or Decimal("0.00")

        total_cost_value += qty * cost
        total_retail_value += qty * price

    expected_profit = total_retail_value - total_cost_value

    # Low stock and out of stock counts
    low_stock_threshold = 10
    low_stock_count = sum(1 for p in products if 0 < (p.quantity_in_stock or 0) <= low_stock_threshold)
    out_of_stock_count = sum(1 for p in products if (p.quantity_in_stock or 0) == 0)

    # Get all categories for filter dropdown
    all_categories = (
        MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True)
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )

    # Category display names
    category_display_map = {
        "beer": "Beer",
        "cider": "Cider",
        "wine": "Wine",
        "spirits": "Spirits",
        "whiskey": "Whiskey",
        "soft_drinks": "Soft Drinks",
        "water": "Water",
        "other": "Other",
    }

    categories_list = [
        {"key": cat, "display": category_display_map.get(cat, cat.title()) if cat else "Other"}
        for cat in all_categories
        if cat
    ]

    context = {
        "business": business,
        "products": products,
        "total_products": total_products,
        "total_quantity": total_quantity,
        "total_cost_value": total_cost_value,
        "total_retail_value": total_retail_value,
        "expected_profit": expected_profit,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "categories": categories_list,
        "selected_category": selected_category,
        "search_query": search_query,
        "low_stock_threshold": low_stock_threshold,
        "active_tab": "stock",
    }

    return render(request, "verticals/liquor/stock_list.html", context)
