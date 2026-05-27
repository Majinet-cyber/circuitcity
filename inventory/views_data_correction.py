# inventory/views_data_correction.py
"""
Data Correction Views for the Phones vertical.

Provides manager-only access to:
- Data Correction dashboard with search and filters
- Edit capabilities for phones (including sold items)
- Edit capabilities for accessories
- Void (soft-delete) with audit trail
- Correction history/audit trail display

CRITICAL: All actions require Manager role and create audit logs.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect

from tenants.utils import get_active_business, require_business
from core.decorators import manager_required
from core.roles import is_manager

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import InventoryItem, Product, AuditLog
from inventory.models_accessories import AccessoryProduct, AccessoryStock, AccessoryStockLog
from inventory.models_data_correction import (
    CorrectionType,
    DataCorrectionLog,
    VoidedRecord,
)
from inventory.services_data_correction import DataCorrectionService, CorrectionResult
from inventory.verticals import base


# =============================================================================
# DATA CORRECTION DASHBOARD
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def data_correction_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Data Correction dashboard page.
    
    Shows searchable/filterable list of all correctable records:
    - Phone sales and stock-in
    - Accessories
    - Voided records
    
    With search by IMEI, SKU, product name, receipt ID, date.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get filter parameters
    search_query = request.GET.get("q", "").strip()
    filter_type = request.GET.get("filter", "all")
    page = request.GET.get("page", 1)
    
    # Valid filter types
    valid_filters = ["all", "sales", "stock_in", "accessories", "voided"]
    if filter_type not in valid_filters:
        filter_type = "all"
    
    # Initialize service
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    # Get correctable items
    items_per_page = 50
    try:
        page_num = int(page)
    except (ValueError, TypeError):
        page_num = 1
    
    offset = (page_num - 1) * items_per_page
    
    results = service.get_correctable_items(
        search=search_query if search_query else None,
        filter_type=filter_type,
        limit=items_per_page,
        offset=offset,
    )
    
    # Get recent correction history for sidebar
    recent_corrections = service.get_correction_history(limit=10)
    
    # Calculate pagination
    total_count = results["total_count"]
    total_pages = (total_count + items_per_page - 1) // items_per_page
    
    ctx.update({
        "page_title": "Data Correction",
        "hero_title": "Data Correction",
        "hero_blurb": "Safely fix wrong sales, stock, and pricing data with full audit trail.",
        
        # Search and filters
        "search_query": search_query,
        "filter_type": filter_type,
        "valid_filters": [
            {"key": "all", "label": "All Records"},
            {"key": "sales", "label": "Sales"},
            {"key": "stock_in", "label": "Stock-In"},
            {"key": "accessories", "label": "Accessories"},
            {"key": "voided", "label": "Voided"},
        ],
        
        # Results
        "phone_items": results["phones"],
        "accessory_items": results["accessories"],
        "voided_items": results["voided"],
        "total_count": total_count,
        
        # Pagination
        "current_page": page_num,
        "total_pages": total_pages,
        "has_previous": page_num > 1,
        "has_next": page_num < total_pages,
        "previous_page": page_num - 1,
        "next_page": page_num + 1,
        
        # Recent corrections
        "recent_corrections": recent_corrections,
        
        # UI flags
        "active_tab": "data_correction",
        "show_warning_banner": True,
    })
    
    return render(request, "verticals/phones/data_correction/dashboard.html", ctx)


# =============================================================================
# PHONE ITEM DETAIL / EDIT
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def phone_item_detail(request: HttpRequest, item_id: int) -> HttpResponse:
    """
    Show detail/edit form for a phone inventory item.
    
    Allows editing:
    - Selling price (even if sold)
    - Order/cost price
    - IMEI (with uniqueness validation)
    - Payment method
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    item = get_object_or_404(
        InventoryItem.objects.select_related("product", "current_location", "assigned_agent", "sold_by"),
        pk=item_id,
        business=business,
    )
    
    # Get correction history for this item
    correction_history = DataCorrectionLog.objects.filter(
        business=business,
        model_name="InventoryItem",
        object_id=item_id,
    ).select_related("corrected_by").order_by("-corrected_at")[:20]
    
    ctx.update({
        "page_title": f"Edit Phone · {item.imei or item.pk}",
        "item": item,
        "correction_history": correction_history,
        "is_sold": item.status == "SOLD",
        "payment_methods": [
            ("CASH", "Cash"),
            ("BANK", "Bank"),
            ("MOBILE_MONEY", "Mobile Money"),
        ],
        "active_tab": "data_correction",
    })
    
    return render(request, "verticals/phones/data_correction/phone_edit.html", ctx)


@csrf_protect
@require_POST
@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def phone_item_edit(request: HttpRequest, item_id: int) -> HttpResponse:
    """
    Handle POST to edit a phone inventory item.
    """
    business = get_active_business(request)
    
    # Get form data
    reason = request.POST.get("reason", "").strip()
    new_selling_price = request.POST.get("selling_price", "").strip()
    new_order_price = request.POST.get("order_price", "").strip()
    new_imei = request.POST.get("imei", "").strip()
    new_payment_method = request.POST.get("payment_method", "").strip()
    
    # Parse prices
    try:
        selling_price = Decimal(new_selling_price) if new_selling_price else None
    except InvalidOperation:
        messages.error(request, f"Invalid selling price: {new_selling_price}")
        return redirect("verticals:phones_data_correction_phone_detail", item_id=item_id)
    
    try:
        order_price = Decimal(new_order_price) if new_order_price else None
    except InvalidOperation:
        messages.error(request, f"Invalid order price: {new_order_price}")
        return redirect("verticals:phones_data_correction_phone_detail", item_id=item_id)
    
    # Initialize service
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    # Apply correction
    result = service.edit_phone_sale(
        item_id=item_id,
        reason=reason,
        new_selling_price=selling_price,
        new_order_price=order_price,
        new_imei=new_imei if new_imei else None,
        new_payment_method=new_payment_method if new_payment_method else None,
    )
    
    if result.success:
        if result.revenue_impact != Decimal("0.00") or result.profit_impact != Decimal("0.00"):
            messages.success(
                request,
                f"✅ {result.message} Revenue impact: MK {result.revenue_impact:,.0f}, "
                f"Profit impact: MK {result.profit_impact:,.0f}"
            )
        else:
            messages.success(request, f"✅ {result.message}")
        
        return redirect("verticals:phones_data_correction")
    else:
        messages.error(request, f"❌ {result.message}")
        return redirect("verticals:phones_data_correction_phone_detail", item_id=item_id)


@csrf_protect
@require_POST
@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def phone_item_void(request: HttpRequest, item_id: int) -> HttpResponse:
    """
    Void (soft-delete) a phone inventory item.
    """
    business = get_active_business(request)
    
    reason = request.POST.get("reason", "").strip()
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.void_phone_item(
        item_id=item_id,
        reason=reason,
    )
    
    if result.success:
        messages.success(
            request,
            f"✅ {result.message} Revenue impact: MK {result.revenue_impact:,.0f}, "
            f"Profit impact: MK {result.profit_impact:,.0f}"
        )
    else:
        messages.error(request, f"❌ {result.message}")
    
    return redirect("verticals:phones_data_correction")


# =============================================================================
# ACCESSORY DETAIL / EDIT
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def accessory_stock_detail(request: HttpRequest, stock_id: int) -> HttpResponse:
    """
    Show detail/edit form for accessory stock.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    stock = get_object_or_404(
        AccessoryStock.objects.select_related("product", "location"),
        pk=stock_id,
        business=business,
    )
    
    # Get correction history
    correction_history = DataCorrectionLog.objects.filter(
        business=business,
        model_name="AccessoryStock",
        object_id=stock_id,
    ).select_related("corrected_by").order_by("-corrected_at")[:20]
    
    ctx.update({
        "page_title": f"Edit Accessory · {stock.product.name}",
        "stock": stock,
        "product": stock.product,
        "correction_history": correction_history,
        "active_tab": "data_correction",
    })
    
    return render(request, "verticals/phones/data_correction/accessory_edit.html", ctx)


@csrf_protect
@require_POST
@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def accessory_stock_edit(request: HttpRequest, stock_id: int) -> HttpResponse:
    """
    Handle POST to edit accessory stock.
    """
    business = get_active_business(request)
    
    reason = request.POST.get("reason", "").strip()
    new_qty = request.POST.get("qty_on_hand", "").strip()
    new_avg_cost = request.POST.get("avg_cost", "").strip()
    
    try:
        qty = int(new_qty) if new_qty else None
    except ValueError:
        messages.error(request, f"Invalid quantity: {new_qty}")
        return redirect("verticals:phones_data_correction_accessory_detail", stock_id=stock_id)
    
    try:
        avg_cost = Decimal(new_avg_cost) if new_avg_cost else None
    except InvalidOperation:
        messages.error(request, f"Invalid average cost: {new_avg_cost}")
        return redirect("verticals:phones_data_correction_accessory_detail", stock_id=stock_id)
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.edit_accessory_stock(
        stock_id=stock_id,
        reason=reason,
        new_qty=qty,
        new_avg_cost=avg_cost,
    )
    
    if result.success:
        messages.success(request, f"✅ {result.message}")
        return redirect("verticals:phones_data_correction")
    else:
        messages.error(request, f"❌ {result.message}")
        return redirect("verticals:phones_data_correction_accessory_detail", stock_id=stock_id)


# =============================================================================
# AUDIT TRAIL
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def correction_audit_trail(request: HttpRequest) -> HttpResponse:
    """
    Show full audit trail of all data corrections.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get all corrections with pagination
    page = request.GET.get("page", 1)
    
    corrections_qs = DataCorrectionLog.objects.filter(
        business=business,
    ).select_related("corrected_by").order_by("-corrected_at")
    
    paginator = Paginator(corrections_qs, 50)
    
    try:
        corrections = paginator.page(page)
    except PageNotAnInteger:
        corrections = paginator.page(1)
    except EmptyPage:
        corrections = paginator.page(paginator.num_pages)
    
    ctx.update({
        "page_title": "Correction Audit Trail",
        "corrections": corrections,
        "active_tab": "data_correction",
    })
    
    return render(request, "verticals/phones/data_correction/audit_trail.html", ctx)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def api_search_items(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for searching correctable items.
    
    Query params:
    - q: Search query
    - filter: all, sales, stock_in, accessories, voided
    - limit: Max results (default 50)
    - offset: Pagination offset
    """
    business = get_active_business(request)
    
    search = request.GET.get("q", "").strip()
    filter_type = request.GET.get("filter", "all")
    limit = min(int(request.GET.get("limit", 50)), 100)
    offset = int(request.GET.get("offset", 0))
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    results = service.get_correctable_items(
        search=search if search else None,
        filter_type=filter_type,
        limit=limit,
        offset=offset,
    )
    
    # Convert Decimal to float for JSON serialization
    def convert_decimals(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(item) for item in obj]
        return obj
    
    return JsonResponse({
        "ok": True,
        "phones": convert_decimals(results["phones"]),
        "accessories": convert_decimals(results["accessories"]),
        "voided": convert_decimals(results["voided"]),
        "total_count": results["total_count"],
    })


@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def api_item_history(request: HttpRequest, model_name: str, object_id: int) -> JsonResponse:
    """
    API endpoint to get correction history for a specific item.
    """
    business = get_active_business(request)
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    history = service.get_correction_history(
        model_name=model_name,
        object_id=object_id,
        limit=50,
    )
    
    return JsonResponse({
        "ok": True,
        "history": [
            {
                "id": log.pk,
                "correction_type": log.get_correction_type_display(),
                "corrected_by": log.corrected_by.get_full_name() or log.corrected_by.username,
                "corrected_at": log.corrected_at.isoformat(),
                "reason": log.reason,
                "field_changes": log.field_changes,
                "revenue_impact": float(log.revenue_impact),
                "profit_impact": float(log.profit_impact),
            }
            for log in history
        ],
    })


@csrf_protect
@require_POST
@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def api_edit_phone(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to edit a phone item.
    
    POST body (JSON):
    - item_id: int
    - reason: str (required)
    - selling_price: str (optional)
    - order_price: str (optional)
    - imei: str (optional)
    - payment_method: str (optional)
    """
    business = get_active_business(request)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    item_id = data.get("item_id")
    reason = data.get("reason", "").strip()
    
    if not item_id:
        return JsonResponse({"ok": False, "error": "item_id is required"}, status=400)
    
    # Parse prices
    try:
        selling_price = Decimal(data["selling_price"]) if data.get("selling_price") else None
    except (InvalidOperation, KeyError):
        selling_price = None
    
    try:
        order_price = Decimal(data["order_price"]) if data.get("order_price") else None
    except (InvalidOperation, KeyError):
        order_price = None
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.edit_phone_sale(
        item_id=item_id,
        reason=reason,
        new_selling_price=selling_price,
        new_order_price=order_price,
        new_imei=data.get("imei"),
        new_payment_method=data.get("payment_method"),
    )
    
    if result.success:
        return JsonResponse({
            "ok": True,
            "message": result.message,
            "revenue_impact": float(result.revenue_impact),
            "profit_impact": float(result.profit_impact),
        })
    else:
        return JsonResponse({
            "ok": False,
            "error": result.message,
            "errors": result.errors,
        }, status=400)


@csrf_protect
@require_POST
@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def api_void_phone(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to void a phone item.
    
    POST body (JSON):
    - item_id: int
    - reason: str (required)
    """
    business = get_active_business(request)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    item_id = data.get("item_id")
    reason = data.get("reason", "").strip()
    
    if not item_id:
        return JsonResponse({"ok": False, "error": "item_id is required"}, status=400)
    
    service = DataCorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.void_phone_item(
        item_id=item_id,
        reason=reason,
    )
    
    if result.success:
        return JsonResponse({
            "ok": True,
            "message": result.message,
            "revenue_impact": float(result.revenue_impact),
            "profit_impact": float(result.profit_impact),
        })
    else:
        return JsonResponse({
            "ok": False,
            "error": result.message,
            "errors": result.errors,
        }, status=400)


# =============================================================================
# EXPORT CORRECTIONS LOG
# =============================================================================

@never_cache
@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@manager_required
def export_corrections_csv(request: HttpRequest) -> HttpResponse:
    """
    Export all corrections to CSV.
    """
    import csv
    
    business = get_active_business(request)
    
    corrections = DataCorrectionLog.objects.filter(
        business=business,
    ).select_related("corrected_by").order_by("-corrected_at")
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="data_corrections_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    )
    
    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "Time",
        "Type",
        "Model",
        "Object ID",
        "Corrected By",
        "Reason",
        "Changes",
        "Revenue Impact",
        "Profit Impact",
    ])
    
    for log in corrections:
        local_time = timezone.localtime(log.corrected_at)
        writer.writerow([
            local_time.strftime("%Y-%m-%d"),
            local_time.strftime("%H:%M:%S"),
            log.get_correction_type_display(),
            log.model_name,
            log.object_id,
            log.corrected_by.get_full_name() or log.corrected_by.username,
            log.reason,
            log.changes_summary,
            f"{log.revenue_impact:.2f}",
            f"{log.profit_impact:.2f}",
        ])
    
    return response


# Export views
__all__ = [
    "data_correction_dashboard",
    "phone_item_detail",
    "phone_item_edit",
    "phone_item_void",
    "accessory_stock_detail",
    "accessory_stock_edit",
    "correction_audit_trail",
    "api_search_items",
    "api_item_history",
    "api_edit_phone",
    "api_void_phone",
    "export_corrections_csv",
]

