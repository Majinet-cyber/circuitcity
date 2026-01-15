# inventory/verticals/farm_sales.py
"""
Farm Sales view with gamified Malawi-specific crop and livestock quick-pick cards.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmLedgerEntry,
    FarmEntryType,
    FarmUnit,
    FarmPaymentMethod,
)
from tenants.utils import require_business
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_landing(request: HttpRequest) -> HttpResponse:
    """
    Farm Sales landing: Choose between Crops or Livestock.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    from inventory.services.farm_filters import parse_farm_filters, get_available_filter_options
    filter_state = parse_farm_filters(request, business)
    filter_options = get_available_filter_options(business)
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Farm Sales",
        "hero_blurb": "Record your crop and livestock sales quickly",
        "filter_state": filter_state,
        "filter_options": filter_options,
    })
    
    return render(request, "verticals/farm/sales_landing.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_crops(request: HttpRequest) -> HttpResponse:
    """Crop Sales: Quick-pick Malawi crop cards."""
    ctx = base.base_context(request)
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Crop Sales",
        "hero_blurb": "Select the crop you sold",
    })
    
    return render(request, "verticals/farm/sales_crops.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_livestock(request: HttpRequest) -> HttpResponse:
    """Livestock Sales: Quick-pick animal type cards."""
    ctx = base.base_context(request)
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Livestock Sales",
        "hero_blurb": "Select the animal type you sold",
    })
    
    return render(request, "verticals/farm/sales_livestock.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def sales_record(request: HttpRequest) -> HttpResponse:
    """Record a new farm sale."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            entry = FarmLedgerEntry.objects.create(
                business=business,
                date=request.POST.get("date") or timezone.now().date(),
                entry_type=FarmEntryType.SALE,
                enterprise_type=request.POST.get("enterprise_type", "general"),
                category="sale",
                description=request.POST.get("description", ""),
                amount_mwk=amount,
                quantity=request.POST.get("quantity") or None,
                unit=request.POST.get("unit", "item"),
                payment_method=request.POST.get("payment_method", "cash"),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            messages.success(request, f"Sale of MWK {amount:,.2f} recorded successfully.")
            return redirect("verticals:farm_sales")
        except Exception as e:
            messages.error(request, f"Error recording sale: {e}")
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Record Sale",
        "payment_methods": FarmPaymentMethod.choices,
        "units": FarmUnit.choices,
    })
    
    return render(request, "verticals/farm/sales_record.html", ctx)
