# inventory/views_electronics_stock_list.py
"""
Electronics (Laptops / Desktops) Stock List.

Separate from the phones stock list (views.py::stock_list) to avoid
any regression risk.  Phones remain at /inventory/list/ (default).
Electronics live at /inventory/electronics/stock/.

Features:
- Category panel: Phones (link to stock_list) / Laptops / Desktops
- Search: brand, model_name, serial_number
- Status filter: in_stock / sold / all
- CSV export via ?format=csv
- Pagination (50 per page)
"""
from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from tenants.utils import get_active_business, require_business
from inventory.models_phone_products import (
    ElectronicsCategory,
    ElectronicsStockItem,
)


@never_cache
@login_required
@require_business
def electronics_stock_list(request: HttpRequest) -> HttpResponse:
    """
    Stock list for laptops and desktops.
    Default: laptops.  Switch via ?category=desktops.
    """
    business = get_active_business(request)
    if not business:
        return redirect("tenants:activate_mine")

    raw_cat = (request.GET.get("category") or "laptops").strip().lower()
    category = raw_cat if raw_cat in ("laptops", "desktops") else "laptops"
    cat_filter = ElectronicsCategory.LAPTOP if category == "laptops" else ElectronicsCategory.DESKTOP
    cat_label = "Laptops" if category == "laptops" else "Desktops"

    # Status filter
    raw_status = (request.GET.get("status") or "in_stock").strip().lower()
    if raw_status not in ("in_stock", "sold", "all"):
        raw_status = "in_stock"

    # Search
    q = (request.GET.get("q") or "").strip()

    # Base queryset
    qs = (
        ElectronicsStockItem.objects
        .filter(business=business, catalog_product__category=cat_filter, is_active=True)
        .select_related("catalog_product", "current_location", "sold_by")
        .order_by("-received_at", "-created_at")
    )

    if raw_status == "in_stock":
        qs = qs.filter(status="IN_STOCK")
    elif raw_status == "sold":
        qs = qs.filter(status="SOLD")
    # "all" → no additional filter

    if q:
        qs = qs.filter(
            Q(serial_number__icontains=q)
            | Q(catalog_product__brand__icontains=q)
            | Q(catalog_product__model_name__icontains=q)
            | Q(catalog_product__ram_str__icontains=q)
            | Q(catalog_product__storage_str__icontains=q)
        )

    # CSV export
    if request.GET.get("format") == "csv":
        return _export_csv(qs, category)

    # Aggregate counters (business-wide, no search filter)
    all_qs = ElectronicsStockItem.objects.filter(
        business=business, catalog_product__category=cat_filter, is_active=True
    )
    total_in_stock = all_qs.filter(status="IN_STOCK").count()
    total_sold = all_qs.filter(status="SOLD").count()
    stock_value = all_qs.filter(status="IN_STOCK").aggregate(
        v=Coalesce(Sum("order_price"), Decimal("0.00"))
    )["v"]
    sold_revenue = all_qs.filter(status="SOLD").aggregate(
        v=Coalesce(Sum("selling_price"), Decimal("0.00"))
    )["v"]

    # Pagination
    paginator = Paginator(qs, 50)
    page_num = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_num)
    except Exception:
        page_obj = paginator.get_page(1)

    context = {
        "business": business,
        "category": category,
        "cat_label": cat_label,
        "cat_icon": "💻" if category == "laptops" else "🖥️",
        "status": raw_status,
        "q": q,
        "page_obj": page_obj,
        "total_in_stock": total_in_stock,
        "total_sold": total_sold,
        "stock_value": stock_value,
        "sold_revenue": sold_revenue,
        "phones_stock_url": reverse("inventory:stock_list"),
        "laptops_url": reverse("inventory:electronics_stock_list") + "?category=laptops",
        "desktops_url": reverse("inventory:electronics_stock_list") + "?category=desktops",
        "csv_url": request.get_full_path().split("?")[0] + "?" + _build_csv_qs(request),
        "scan_in_url": reverse("inventory:scan_in"),
    }
    return render(request, "inventory/electronics_stock_list.html", context)


def _build_csv_qs(request: HttpRequest) -> str:
    p = request.GET.copy()
    p["format"] = "csv"
    return p.urlencode()


def _export_csv(qs, category: str) -> HttpResponse:
    cat_label = "Laptops" if category == "laptops" else "Desktops"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{cat_label.lower()}_stock.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Brand", "Model", "Specs", "Serial Number", "Status",
        "Cost Price", "Selling Price", "Battery Health",
        "Payment Method", "Location", "Received At", "Sold At", "Sold By",
    ])
    for item in qs.iterator():
        specs = " / ".join(filter(None, [
            item.catalog_product.ram_str,
            item.catalog_product.storage_str,
            item.catalog_product.cpu,
        ]))
        writer.writerow([
            item.catalog_product.brand,
            item.catalog_product.model_name,
            specs,
            item.serial_number,
            item.status,
            item.order_price,
            item.selling_price or "",
            item.battery_health or "",
            item.payment_method or "",
            str(item.current_location) if item.current_location else "",
            item.received_at,
            item.sold_at or "",
            str(item.sold_by) if item.sold_by else "",
        ])
    return response
