# inventory/verticals/welding.py
"""
Welding Manager vertical adapter.
Provides dashboard, quotes, jobs, materials, and invoice generation.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_welding import (
    WeldingEstimatorTuning,
    WeldingInvoice,
    WeldingInvoiceStatus,
    WeldingJob,
    WeldingJobStatus,
    WeldingMaterial,
    WeldingMaterialCategory,
    WeldingMaterialStockMove,
    WeldingMaterialUnit,
    WeldingQuote,
    WeldingQuoteStatus,
    WeldingTemplate,
)
from inventory.services.welding_estimator import (
    bom_items_to_json,
    cost_breakdown_to_json,
    generate_quote_from_template,
    get_default_materials,
    get_default_templates,
    material_to_data,
    seed_default_materials,
    tuning_to_data,
)
from inventory.services.welding_pdf import generate_quote_pdf
from inventory.verticals import base
from tenants.utils import require_business


# ==============================================================================
# SEEDING HELPER
# ==============================================================================


def ensure_materials_seeded(business):
    """
    Ensure default welding materials are seeded for this business.
    Idempotent: only creates materials that don't exist.
    """
    existing_codes = list(
        WeldingMaterial.objects.filter(business=business).values_list("code", flat=True)
    )
    
    to_seed = seed_default_materials(existing_codes)
    
    created_materials = []
    for mat in to_seed:
        material = WeldingMaterial.objects.create(
            business=business,
            code=mat["code"],
            name=mat["name"],
            category=mat["category"],
            unit=mat["unit"],
            price_mwk=mat["default_price"],
            is_seeded=True,
        )
        created_materials.append(material)
    
    return created_materials


def ensure_templates_seeded():
    """
    Ensure default welding templates exist.
    Templates are global (business=null).
    """
    existing_codes = set(WeldingTemplate.objects.values_list("code", flat=True))
    
    for tpl in get_default_templates():
        if tpl["code"] not in existing_codes:
            WeldingTemplate.objects.create(
                business=None,  # Global template
                code=tpl["code"],
                name=tpl["name"],
                params_schema=tpl.get("params_schema", {}),
                base_bom=tpl.get("base_bom", {}),
                default_labour_hours=Decimal(str(tpl.get("default_labour_hours", 4))),
            )


# ==============================================================================
# DASHBOARD
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def dashboard(request: HttpRequest) -> HttpResponse:
    """Welding Manager dashboard with KPIs and quick actions."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    # Ensure materials are seeded on first visit
    seeded = ensure_materials_seeded(business)
    if seeded:
        messages.info(request, f"Initialized {len(seeded)} default materials for your workshop.")
    
    # Ensure templates exist
    ensure_templates_seeded()
    
    # Import the Revenue and Cost models
    from inventory.models_welding import WeldingRevenue, WeldingCost
    
    today = timezone.now().date()
    
    # Parse date range from request
    from inventory.verticals.base import parse_date_range_from_request
    date_range = parse_date_range_from_request(request)
    active_range = date_range["active_range"]
    start_date = date_range["start_date"]
    end_date = date_range["end_date"]
    
    # Support custom start/end dates
    start_param = request.GET.get("start", "")
    end_param = request.GET.get("end", "")
    
    if start_param and end_param:
        try:
            from datetime import date as date_class
            start_date = date_class.fromisoformat(start_param)
            end_date = date_class.fromisoformat(end_param) + timedelta(days=1)  # Make end_date exclusive
            active_range = "custom"
            range_label = f"{start_date.strftime('%b %d')} - {(end_date - timedelta(days=1)).strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Invalid dates, fall back to active_range
            pass
    
    # Generate range label
    if active_range == "custom":
        pass  # Already set above
    elif active_range == "7d":
        range_label = "Last 7 Days"
    elif active_range == "30d":
        range_label = "Last 30 Days"
    else:  # mtd
        range_label = "Month to Date"
    
    # Convert dates to timezone-aware datetimes for filtering
    start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
    end_dt = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.min.time()))
    
    # Quote stats (filtered by date range)
    quotes = WeldingQuote.objects.filter(business=business)
    quotes_in_range = quotes.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    quotes_pending = quotes.filter(status__in=[WeldingQuoteStatus.DRAFT, WeldingQuoteStatus.SENT])
    quotes_accepted = quotes.filter(status=WeldingQuoteStatus.ACCEPTED)
    
    # Job stats (filtered by date range)
    jobs = WeldingJob.objects.filter(business=business)
    jobs_active = jobs.filter(status__in=[WeldingJobStatus.PENDING, WeldingJobStatus.IN_PROGRESS])
    jobs_ready = jobs.filter(status=WeldingJobStatus.READY)
    jobs_completed_in_range = jobs.filter(
        status=WeldingJobStatus.DELIVERED,
        delivered_at__gte=start_dt,
        delivered_at__lt=end_dt,
    )
    
    # Revenue in range (from delivered jobs)
    job_revenue_in_range = jobs_completed_in_range.aggregate(
        total=Coalesce(Sum("final_price"), Decimal("0"))
    )["total"]
    
    # Additional revenue from WeldingRevenue entries
    additional_revenue = WeldingRevenue.objects.filter(
        business=business,
        received_on__gte=start_date,
        received_on__lt=end_date,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0"))
    )["total"]
    
    # Total revenue = job revenue + additional revenue
    total_revenue_in_range = job_revenue_in_range + additional_revenue
    
    # Costs in range from WeldingCost entries
    total_costs_in_range = WeldingCost.objects.filter(
        business=business,
        incurred_on__gte=start_date,
        incurred_on__lt=end_date,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0"))
    )["total"]
    
    # Profit = Revenue - Costs
    profit_in_range = total_revenue_in_range - total_costs_in_range
    
    # Invoice stats
    invoices = WeldingInvoice.objects.filter(business=business)
    invoices_unpaid = invoices.filter(status__in=[
        WeldingInvoiceStatus.SENT,
        WeldingInvoiceStatus.PARTIAL,
        WeldingInvoiceStatus.OVERDUE,
    ])
    total_outstanding = invoices_unpaid.aggregate(
        total=Coalesce(Sum("total"), Decimal("0")) - Coalesce(Sum("amount_paid"), Decimal("0"))
    )
    
    # Materials low stock
    low_stock_materials = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).filter(
        quantity_in_stock__lte=F("low_stock_threshold"),
    ).exclude(low_stock_threshold__isnull=True)
    
    # Recent quotes
    recent_quotes = quotes.order_by("-created_at")[:5]
    
    # Recent jobs
    recent_jobs = jobs.order_by("-created_at")[:5]
    
    # Build chart data for the selected range (show up to 30 days, or actual range if smaller)
    days_to_show = min((end_date - start_date).days, 30)
    if days_to_show > 14:
        # Show last 14 days of the range
        chart_start_date = end_date - timedelta(days=14)
    else:
        chart_start_date = start_date
    
    # Revenue trend (from delivered jobs)
    revenue_by_day = (
        WeldingJob.objects.filter(
            business=business,
            status=WeldingJobStatus.DELIVERED,
            delivered_at__date__gte=chart_start_date,
            delivered_at__date__lt=end_date,
        )
        .annotate(date=TruncDate("delivered_at"))
        .values("date")
        .annotate(revenue=Sum("final_price"))
        .order_by("date")
    )
    
    # Create date lookup for revenue (keep as integers for proper MWK display)
    revenue_lookup = {r["date"]: int(r["revenue"] or 0) for r in revenue_by_day}
    
    # Quotes & Jobs trend by creation date
    quotes_by_day = (
        WeldingQuote.objects.filter(
            business=business,
            created_at__date__gte=chart_start_date,
            created_at__date__lt=end_date,
        )
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    jobs_by_day = (
        WeldingJob.objects.filter(
            business=business,
            created_at__date__gte=chart_start_date,
            created_at__date__lt=end_date,
        )
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    
    quotes_lookup = {q["date"]: q["count"] for q in quotes_by_day}
    jobs_lookup = {j["date"]: j["count"] for j in jobs_by_day}
    
    # Build chart data arrays
    revenue_trend = []
    quotes_jobs_trend = []
    chart_days = (end_date - chart_start_date).days
    for i in range(chart_days):
        d = chart_start_date + timedelta(days=i)
        date_str = d.strftime("%b %d")
        revenue_trend.append({
            "date": date_str,
            "revenue": revenue_lookup.get(d, 0),
        })
        quotes_jobs_trend.append({
            "date": date_str,
            "quotes": quotes_lookup.get(d, 0),
            "jobs": jobs_lookup.get(d, 0),
        })
    
    # Insights section - stats for the selected period
    jobs_created_in_range = jobs.filter(created_at__gte=start_dt, created_at__lt=end_dt).count()
    jobs_completed_count = jobs_completed_in_range.count()
    avg_job_value = job_revenue_in_range / jobs_completed_count if jobs_completed_count > 0 else Decimal("0")
    
    # Top job category (if template is used)
    top_categories = (
        jobs_completed_in_range.filter(template__isnull=False)
        .values("template__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:1]
    )
    top_job_category = top_categories[0]["template__name"] if top_categories else "N/A"
    
    # Outstanding jobs (not delivered)
    outstanding_jobs = jobs.exclude(status=WeldingJobStatus.DELIVERED).count()

    # Top clients by total quote value (all time)
    top_clients = (
        WeldingQuote.objects.filter(business=business)
        .exclude(customer_name="")
        .values("customer_name", "customer_phone")
        .annotate(
            total_value=Coalesce(Sum("total"), Decimal("0")),
            quote_count=Count("id"),
        )
        .order_by("-total_value")[:5]
    )

    # Overdue / delayed jobs: active jobs older than 14 days
    cutoff = timezone.now() - timedelta(days=14)
    delayed_jobs = jobs.filter(
        status__in=[WeldingJobStatus.PENDING, WeldingJobStatus.IN_PROGRESS],
        created_at__lt=cutoff,
    ).count()

    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Welding Manager",
        "hero_blurb": "Create quotes in seconds, track jobs, and generate invoices quickly.",
        
        # Date range context
        "active_range": active_range,
        "range_label": range_label,
        "start_date_param": start_param,
        "end_date_param": end_param,
        
        # KPIs (filtered by date range)
        "quotes_this_month": quotes_in_range.count(),
        "quotes_pending": quotes_pending.count(),
        "jobs_active": jobs_active.count(),
        "jobs_ready": jobs_ready.count(),
        "revenue_this_month": total_revenue_in_range,
        "costs_this_month": total_costs_in_range,
        "profit_this_month": profit_in_range,
        "total_outstanding": total_outstanding.get("total", Decimal("0")),
        
        # Low stock alert
        "low_stock_count": low_stock_materials.count(),
        "low_stock_materials": low_stock_materials[:5],
        
        # Recent activity
        "recent_quotes": recent_quotes,
        "recent_jobs": recent_jobs,
        
        # Chart data (JSON for JavaScript)
        "revenue_trend_json": json.dumps(revenue_trend),
        "quotes_jobs_trend_json": json.dumps(quotes_jobs_trend),
        
        # Insights
        "jobs_created_in_range": jobs_created_in_range,
        "jobs_completed_in_range": jobs_completed_count,
        "avg_job_value": avg_job_value,
        "top_job_category": top_job_category,
        "outstanding_jobs": outstanding_jobs,
        "delayed_jobs": delayed_jobs,
        "top_clients": list(top_clients),

        # Quick action URLs
        "url_create_quote": "/verticals/welding/quotes/create/",
        "url_stock_in": "/verticals/welding/stock-in/",
        "url_materials": "/verticals/welding/materials/",
    })
    
    return render(request, "verticals/welding/dashboard.html", ctx)


# ==============================================================================
# MATERIALS CATALOG
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def materials_list(request: HttpRequest) -> HttpResponse:
    """List all welding materials with search and category filter."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure materials seeded
    ensure_materials_seeded(business)
    
    category_filter = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    
    materials = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).order_by("category", "name")
    
    if category_filter:
        materials = materials.filter(category=category_filter)
    
    if search_query:
        # Search in name, code, and category
        materials = materials.filter(
            models.Q(name__icontains=search_query) |
            models.Q(code__icontains=search_query)
        )
    
    # Count low stock items
    low_stock_count = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).filter(
        quantity_in_stock__lte=F("low_stock_threshold"),
    ).exclude(low_stock_threshold__isnull=True).count()
    
    ctx.update({
        "active_tab": "materials",
        "materials": materials,
        "categories": WeldingMaterialCategory.choices,
        "filter_category": category_filter,
        "search_query": search_query,
        "low_stock_count": low_stock_count,
    })
    
    return render(request, "verticals/welding/materials_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def material_edit(request: HttpRequest, material_id: int) -> HttpResponse:
    """Edit material price and details."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    material = get_object_or_404(WeldingMaterial, id=material_id, business=business)
    
    if request.method == "POST":
        try:
            material.name = request.POST.get("name", material.name)
            material.price_mwk = Decimal(request.POST.get("price", str(material.price_mwk)))
            material.low_stock_threshold = request.POST.get("low_stock_threshold") or None
            material.save()
            
            messages.success(request, f"Material '{material.name}' updated.")
            return redirect("/verticals/welding/materials/")
        except Exception as e:
            messages.error(request, f"Error updating material: {e}")
    
    ctx.update({
        "active_tab": "materials",
        "material": material,
        "categories": WeldingMaterialCategory.choices,
        "units": WeldingMaterialUnit.choices,
    })
    
    return render(request, "verticals/welding/material_edit.html", ctx)


# ==============================================================================
# STOCK IN
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def stock_in(request: HttpRequest) -> HttpResponse:
    """Stock in materials (purchases)."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    materials = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).order_by("category", "name")
    
    if request.method == "POST":
        try:
            material_id = request.POST.get("material_id")
            material = get_object_or_404(WeldingMaterial, id=material_id, business=business)
            
            quantity = Decimal(request.POST.get("quantity", "0"))
            unit_cost = request.POST.get("unit_cost")
            
            # Create stock move
            move = WeldingMaterialStockMove.objects.create(
                material=material,
                move_type="in",
                quantity=quantity,
                unit_cost_mwk=Decimal(unit_cost) if unit_cost else None,
                date=request.POST.get("date") or timezone.now().date(),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            
            # Update material stock
            material.quantity_in_stock += quantity
            
            # Update price if provided
            if unit_cost:
                material.price_mwk = Decimal(unit_cost)
            
            material.save()
            
            messages.success(request, f"Stocked in {quantity} x {material.name}")
            
            # Check if more items to add
            if request.POST.get("add_another"):
                return redirect("/verticals/welding/stock-in/")
            return redirect("/verticals/welding/dashboard/")
            
        except Exception as e:
            messages.error(request, f"Error stocking in: {e}")
    
    ctx.update({
        "active_tab": "stock_in",
        "materials": materials,
    })
    
    return render(request, "verticals/welding/stock_in.html", ctx)


# ==============================================================================
# QUOTES
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def quotes_list(request: HttpRequest) -> HttpResponse:
    """List all quotes."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    status_filter = request.GET.get("status", "")
    
    quotes = WeldingQuote.objects.filter(business=business).order_by("-created_at")
    
    if status_filter:
        quotes = quotes.filter(status=status_filter)
    
    ctx.update({
        "active_tab": "quotes",
        "quotes": quotes[:50],
        "status_choices": WeldingQuoteStatus.choices,
        "filter_status": status_filter,
    })
    
    return render(request, "verticals/welding/quotes_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def quote_create(request: HttpRequest) -> HttpResponse:
    """
    Create a new quote - MANUAL MODE.
    Manager picks materials, enters quantities/prices, adds costs/profit.
    Template selection is OPTIONAL and DOES NOT auto-add materials.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure templates exist (for optional guidance)
    ensure_templates_seeded()
    
    templates = WeldingTemplate.objects.filter(
        models.Q(business=None) | models.Q(business=business),
        is_active=True,
    ).order_by("name")
    
    # Get all materials for picker
    materials = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).order_by("category", "name")
    
    if request.method == "POST":
        try:
            # Basic quote info
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()
            customer_email = request.POST.get("customer_email", "").strip()
            
            if not customer_name:
                messages.error(request, "Customer name is required.")
                raise ValueError("Missing customer name")
            
            # Template is optional (only for labeling/guidance)
            template_id = request.POST.get("template_id")
            template = None
            if template_id:
                template = templates.filter(id=template_id).first()
            
            # Create empty quote
            quote = WeldingQuote.objects.create(
                business=business,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                template=template,
                status=WeldingQuoteStatus.DRAFT,
                created_by=request.user,
                # Start with zero totals - manager will build it
                materials_cost=Decimal("0"),
                labour_cost=Decimal("0"),
                overhead_cost=Decimal("0"),
                subtotal=Decimal("0"),
                total=Decimal("0"),
            )
            
            messages.success(request, f"Quote {quote.quote_number} created. Now add materials and costs.")
            # Redirect to quote builder (detail page with edit mode)
            return redirect(f"/verticals/welding/quotes/{quote.id}/")
            
        except Exception as e:
            messages.error(request, f"Error creating quote: {e}")
    
    ctx.update({
        "active_tab": "quotes",
        "templates": templates,
        "materials": materials,
        "categories": WeldingMaterialCategory.choices,
    })
    
    return render(request, "verticals/welding/quote_create.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def quote_detail(request: HttpRequest, quote_id: int) -> HttpResponse:
    """
    View/edit quote details.
    Shows line items + costs that manager has added.
    Allows editing if status is DRAFT.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    # Get line items and costs
    line_items = quote.line_items.all()
    costs = quote.costs.all()
    
    # Calculate totals dynamically
    materials_total = sum((item.line_total for item in line_items), Decimal("0"))
    labour_total = costs.filter(cost_type="labour").aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    transport_total = costs.filter(cost_type="transport").aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    other_total = costs.filter(cost_type="other").aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    profit_total = costs.filter(cost_type="profit").aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    
    grand_total = materials_total + labour_total + transport_total + other_total + profit_total
    
    # Check if editable
    is_editable = quote.status == WeldingQuoteStatus.DRAFT
    
    # Get all materials for picker (if editing)
    materials = None
    if is_editable:
        materials = WeldingMaterial.objects.filter(
            business=business,
            is_active=True,
        ).order_by("category", "name")
    
    ctx.update({
        "active_tab": "quotes",
        "quote": quote,
        "line_items": line_items,
        "costs": costs,
        "materials_total": materials_total,
        "labour_total": labour_total,
        "transport_total": transport_total,
        "other_total": other_total,
        "profit_total": profit_total,
        "grand_total": grand_total,
        "is_editable": is_editable,
        "materials": materials,
        "categories": WeldingMaterialCategory.choices,
    })
    
    return render(request, "verticals/welding/quote_detail.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_add_line_item(request: HttpRequest, quote_id: int) -> JsonResponse:
    """Add a line item to a quote (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    # Only allow editing draft quotes
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        material_id = request.POST.get("material_id")
        quantity = Decimal(request.POST.get("quantity", "1"))
        unit_price = request.POST.get("unit_price")
        notes = request.POST.get("notes", "")
        
        # Validation: quantity must be > 0
        if quantity <= 0:
            return JsonResponse({"success": False, "error": "Quantity must be greater than 0"}, status=400)
        
        # Get material
        material = get_object_or_404(WeldingMaterial, id=material_id, business=business)
        
        # Unit price is optional (manager can leave blank)
        unit_price_decimal = None
        if unit_price and unit_price.strip():
            unit_price_decimal = Decimal(unit_price)
            # Validation: price must be >= 0
            if unit_price_decimal < 0:
                return JsonResponse({"success": False, "error": "Unit price cannot be negative"}, status=400)
        
        # Create line item
        from inventory.models_welding import WeldingQuoteLineItem
        line_item = WeldingQuoteLineItem.objects.create(
            quote=quote,
            material=material,
            material_name=material.name,
            material_unit=material.unit,
            quantity=quantity,
            unit_price=unit_price_decimal,
            notes=notes,
        )
        
        return JsonResponse({
            "success": True,
            "line_item": {
                "id": line_item.id,
                "material_name": line_item.material_name,
                "quantity": str(line_item.quantity),
                "unit": line_item.material_unit,
                "unit_price": str(line_item.unit_price) if line_item.unit_price else "",
                "line_total": str(line_item.line_total),
                "notes": line_item.notes,
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_update_line_item(request: HttpRequest, quote_id: int, item_id: int) -> JsonResponse:
    """Update a line item (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        from inventory.models_welding import WeldingQuoteLineItem
        line_item = get_object_or_404(WeldingQuoteLineItem, id=item_id, quote=quote)
        
        # Update fields
        if "quantity" in request.POST:
            line_item.quantity = Decimal(request.POST["quantity"])
        if "unit_price" in request.POST:
            price_str = request.POST["unit_price"]
            line_item.unit_price = Decimal(price_str) if price_str.strip() else None
        if "notes" in request.POST:
            line_item.notes = request.POST["notes"]
        
        line_item.save()
        
        return JsonResponse({
            "success": True,
            "line_item": {
                "id": line_item.id,
                "quantity": str(line_item.quantity),
                "unit_price": str(line_item.unit_price) if line_item.unit_price else "",
                "line_total": str(line_item.line_total),
                "notes": line_item.notes,
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_delete_line_item(request: HttpRequest, quote_id: int, item_id: int) -> JsonResponse:
    """Delete a line item (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        from inventory.models_welding import WeldingQuoteLineItem
        line_item = get_object_or_404(WeldingQuoteLineItem, id=item_id, quote=quote)
        line_item.delete()
        
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_add_cost(request: HttpRequest, quote_id: int) -> JsonResponse:
    """Add a cost item to a quote (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        cost_type = request.POST.get("cost_type")
        description = request.POST.get("description", "")
        amount = Decimal(request.POST.get("amount", "0"))
        notes = request.POST.get("notes", "")
        
        # Validation: amount must be >= 0
        if amount < 0:
            return JsonResponse({"success": False, "error": "Amount cannot be negative"}, status=400)
        
        from inventory.models_welding import WeldingQuoteCost
        cost = WeldingQuoteCost.objects.create(
            quote=quote,
            cost_type=cost_type,
            description=description,
            amount=amount,
            notes=notes,
        )
        
        return JsonResponse({
            "success": True,
            "cost": {
                "id": cost.id,
                "cost_type": cost.cost_type,
                "cost_type_display": cost.get_cost_type_display(),
                "description": cost.description,
                "amount": str(cost.amount),
                "notes": cost.notes,
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_update_cost(request: HttpRequest, quote_id: int, cost_id: int) -> JsonResponse:
    """Update a cost item (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        from inventory.models_welding import WeldingQuoteCost
        cost = get_object_or_404(WeldingQuoteCost, id=cost_id, quote=quote)
        
        if "description" in request.POST:
            cost.description = request.POST["description"]
        if "amount" in request.POST:
            cost.amount = Decimal(request.POST["amount"])
        if "notes" in request.POST:
            cost.notes = request.POST["notes"]
        
        cost.save()
        
        return JsonResponse({
            "success": True,
            "cost": {
                "id": cost.id,
                "description": cost.description,
                "amount": str(cost.amount),
                "notes": cost.notes,
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_delete_cost(request: HttpRequest, quote_id: int, cost_id: int) -> JsonResponse:
    """Delete a cost item (AJAX endpoint)."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.DRAFT:
        return JsonResponse({"error": "Quote is not editable"}, status=400)
    
    try:
        from inventory.models_welding import WeldingQuoteCost
        cost = get_object_or_404(WeldingQuoteCost, id=cost_id, quote=quote)
        cost.delete()
        
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_GET
def quote_pdf(request: HttpRequest, quote_id: int) -> HttpResponse:
    """Generate and download PDF for a quote."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    # Generate PDF
    pdf_bytes = generate_quote_pdf(quote, business)
    
    if pdf_bytes is None:
        # PDF generation failed - return error response
        messages.error(request, "PDF generation failed. Please try again.")
        return redirect(f"/verticals/welding/quotes/{quote_id}/")
    
    # Return PDF response
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="quote_{quote.quote_number}.pdf"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def quote_accept(request: HttpRequest, quote_id: int) -> HttpResponse:
    """Accept a quote and create a job."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    if quote.status != WeldingQuoteStatus.ACCEPTED:
        quote.status = WeldingQuoteStatus.ACCEPTED
        quote.save(update_fields=["status"])
        
        # Create job from quote
        job = WeldingJob.objects.create(
            business=business,
            quote=quote,
            customer_name=quote.customer_name,
            customer_phone=quote.customer_phone,
            template=quote.template,
            product_description=quote.template.name if quote.template else "",
            estimated_bom=quote.bom,
            quoted_price=quote.total,
            status=WeldingJobStatus.PENDING,
            created_by=request.user,
        )
        
        messages.success(request, f"Quote accepted. Job {job.job_number} created.")
    
    return redirect(f"/verticals/welding/quotes/{quote_id}/")


# ==============================================================================
# JOBS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def jobs_list(request: HttpRequest) -> HttpResponse:
    """List all jobs."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    status_filter = request.GET.get("status", "")
    
    jobs = WeldingJob.objects.filter(business=business).order_by("-created_at")
    
    if status_filter:
        jobs = jobs.filter(status=status_filter)
    
    ctx.update({
        "active_tab": "jobs",
        "jobs": jobs[:50],
        "status_choices": WeldingJobStatus.choices,
        "filter_status": status_filter,
    })
    
    return render(request, "verticals/welding/jobs_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def job_detail(request: HttpRequest, job_id: int) -> HttpResponse:
    """View job details."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    job = get_object_or_404(WeldingJob, id=job_id, business=business)
    
    ctx.update({
        "active_tab": "jobs",
        "job": job,
        "status_choices": WeldingJobStatus.choices,
    })
    
    return render(request, "verticals/welding/job_detail.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def job_update_status(request: HttpRequest, job_id: int) -> HttpResponse:
    """Update job status."""
    business = request.active_business
    job = get_object_or_404(WeldingJob, id=job_id, business=business)
    
    new_status = request.POST.get("status")
    if new_status in dict(WeldingJobStatus.choices):
        job.status = new_status
        
        if new_status == WeldingJobStatus.IN_PROGRESS and not job.started_at:
            job.started_at = timezone.now()
        elif new_status == WeldingJobStatus.READY and not job.completed_at:
            job.completed_at = timezone.now()
        elif new_status == WeldingJobStatus.DELIVERED and not job.delivered_at:
            job.delivered_at = timezone.now()
            if not job.final_price:
                job.final_price = job.quoted_price
        
        job.save()
        messages.success(request, f"Job status updated to {job.get_status_display()}")
    
    return redirect(f"/verticals/welding/jobs/{job_id}/")


# ==============================================================================
# INVOICES
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def invoices_list(request: HttpRequest) -> HttpResponse:
    """List all invoices."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    invoices = WeldingInvoice.objects.filter(business=business).order_by("-created_at")
    
    ctx.update({
        "active_tab": "invoices",
        "invoices": invoices[:50],
        "status_choices": WeldingInvoiceStatus.choices,
    })
    
    return render(request, "verticals/welding/invoices_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def invoice_from_quote(request: HttpRequest, quote_id: int) -> HttpResponse:
    """Generate invoice from a quote."""
    business = request.active_business
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    # Build line items from BOM
    line_items = []
    for item in quote.bom:
        line_items.append({
            "description": item.get("material_name", "Item"),
            "quantity": item.get("quantity", "1"),
            "unit_price": item.get("unit_price_mwk", "0"),
            "total": item.get("line_total_mwk", "0"),
        })
    
    # Add labour line
    if quote.labour_cost > 0:
        line_items.append({
            "description": "Labour",
            "quantity": "1",
            "unit_price": str(quote.labour_cost),
            "total": str(quote.labour_cost),
        })
    
    invoice = WeldingInvoice.objects.create(
        business=business,
        quote=quote,
        customer_name=quote.customer_name,
        customer_phone=quote.customer_phone,
        line_items=line_items,
        subtotal=quote.subtotal,
        total=quote.total,
        status=WeldingInvoiceStatus.DRAFT,
        issue_date=timezone.now().date(),
        created_by=request.user,
    )
    
    messages.success(request, f"Invoice {invoice.invoice_number} generated.")
    return redirect(f"/verticals/welding/invoices/{invoice.id}/")


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def invoice_detail(request: HttpRequest, invoice_id: int) -> HttpResponse:
    """View invoice details (printable)."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    invoice = get_object_or_404(WeldingInvoice, id=invoice_id, business=business)
    
    ctx.update({
        "active_tab": "invoices",
        "invoice": invoice,
        "printable": request.GET.get("print") == "1",
    })
    
    template = "verticals/welding/invoice_print.html" if ctx["printable"] else "verticals/welding/invoice_detail.html"
    return render(request, template, ctx)


# ==============================================================================
# REPORTS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def reports(request: HttpRequest) -> HttpResponse:
    """Welding reports and exports."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    ctx.update({
        "active_tab": "reports",
    })
    
    return render(request, "verticals/welding/reports.html", ctx)


# ==============================================================================
# JOB COST SIMULATOR ("THE BRAIN")
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def job_simulator(request: HttpRequest) -> HttpResponse:
    """
    Job cost simulator - the "brain" for estimating materials and costs.
    Allows users to select a job template and get realistic material estimates.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure materials and templates are seeded
    ensure_materials_seeded(business)
    ensure_templates_seeded()
    
    templates = WeldingTemplate.objects.filter(
        models.Q(business=None) | models.Q(business=business),
        is_active=True,
    ).order_by("name")
    
    materials_qs = WeldingMaterial.objects.filter(business=business, is_active=True)
    materials_catalog = {m.code: material_to_data(m) for m in materials_qs}
    
    simulation_result = None
    selected_template = None
    
    if request.method == "POST":
        template_code = request.POST.get("template_code", "")
        wastage_pct = Decimal(request.POST.get("wastage_pct", "10"))
        labour_rate = Decimal(request.POST.get("labour_rate", "5000"))
        
        selected_template = templates.filter(code=template_code).first()
        
        if selected_template:
            # Get tuning if exists
            tuning = None
            tuning_obj = WeldingEstimatorTuning.objects.filter(
                business=business,
                template=selected_template,
            ).first()
            if tuning_obj:
                tuning = tuning_to_data(tuning_obj)
            
            # Generate quote/estimate
            result = generate_quote_from_template(
                template_code=template_code,
                specs={},
                materials_catalog=materials_catalog,
                tuning=tuning,
                labour_rate_per_hour=labour_rate,
                overhead_pct=wastage_pct,
                margin_pct=Decimal("0"),  # No margin for simulator - just costs
            )
            
            simulation_result = {
                "template": selected_template,
                "bom": result.bom,
                "materials_cost": result.cost_breakdown["materials_cost"],
                "labour_cost": result.cost_breakdown["labour_cost"],
                "overhead_cost": result.cost_breakdown["overhead_cost"],
                "total_cost": result.cost_breakdown["subtotal_before_margin"],
                "recommended_price_25": result.cost_breakdown["subtotal_before_margin"] * Decimal("1.25"),
                "recommended_price_30": result.cost_breakdown["subtotal_before_margin"] * Decimal("1.30"),
            }
    
    ctx.update({
        "active_tab": "simulator",
        "templates": templates,
        "selected_template": selected_template,
        "simulation_result": simulation_result,
    })
    
    return render(request, "verticals/welding/job_simulator.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_POST
def simulator_to_quote(request: HttpRequest) -> HttpResponse:
    """Convert a simulator result into a new quote."""
    business = request.active_business
    
    template_code = request.POST.get("template_code", "")
    customer_name = request.POST.get("customer_name", "Customer")
    customer_phone = request.POST.get("customer_phone", "")
    margin_pct = Decimal(request.POST.get("margin_pct", "25"))
    
    # Get template
    template = WeldingTemplate.objects.filter(
        models.Q(business=None) | models.Q(business=business),
        code=template_code,
        is_active=True,
    ).first()
    
    if not template:
        messages.error(request, "Template not found.")
        return redirect("/verticals/welding/simulator/")
    
    # Get materials
    materials_qs = WeldingMaterial.objects.filter(business=business, is_active=True)
    materials_catalog = {m.code: material_to_data(m) for m in materials_qs}
    
    # Get tuning if exists
    tuning = None
    tuning_obj = WeldingEstimatorTuning.objects.filter(
        business=business,
        template=template,
    ).first()
    if tuning_obj:
        tuning = tuning_to_data(tuning_obj)
    
    # Generate quote
    result = generate_quote_from_template(
        template_code=template_code,
        specs={},
        materials_catalog=materials_catalog,
        tuning=tuning,
        labour_rate_per_hour=Decimal("5000"),
        overhead_pct=Decimal("10"),
        margin_pct=margin_pct,
    )
    
    # Create quote
    quote = WeldingQuote.objects.create(
        business=business,
        customer_name=customer_name,
        customer_phone=customer_phone,
        template=template,
        specs={},
        bom=bom_items_to_json(result.bom),
        cost_breakdown=cost_breakdown_to_json(result.cost_breakdown),
        materials_cost=result.cost_breakdown["materials_cost"],
        labour_cost=result.cost_breakdown["labour_cost"],
        overhead_cost=result.cost_breakdown["overhead_cost"],
        subtotal=result.cost_breakdown["subtotal_before_margin"],
        total=result.cost_breakdown["total"],
        min_price=result.cost_breakdown["min_price"],
        status=WeldingQuoteStatus.DRAFT,
        created_by=request.user,
    )
    
    messages.success(request, f"Quote {quote.quote_number} created from simulator.")
    return redirect(f"/verticals/welding/quotes/{quote.id}/")


# ==============================================================================
# SALES PAGE
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def sales(request: HttpRequest) -> HttpResponse:
    """
    Welding Sales page - shows all revenue from invoices.
    Uses invoices/payments as the definition of sales.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # Get filter parameters
    filter_range = request.GET.get("range", "mtd")
    
    if filter_range == "today":
        start_date = today
        end_date = today
        range_label = "Today"
    elif filter_range == "7d":
        start_date = today - timedelta(days=7)
        end_date = today
        range_label = "Last 7 Days"
    elif filter_range == "30d":
        start_date = today - timedelta(days=30)
        end_date = today
        range_label = "Last 30 Days"
    else:  # mtd
        start_date = month_start
        end_date = today
        range_label = "This Month"
    
    # Get all paid/partial invoices in date range
    invoices = WeldingInvoice.objects.filter(
        business=business,
        issue_date__gte=start_date,
        issue_date__lte=end_date,
    ).order_by("-issue_date")
    
    # Calculate KPIs
    total_invoiced = invoices.aggregate(
        total=Coalesce(Sum("total"), Decimal("0"))
    )["total"]
    
    total_paid = invoices.aggregate(
        total=Coalesce(Sum("amount_paid"), Decimal("0"))
    )["total"]
    
    total_outstanding = total_invoiced - total_paid
    
    num_invoices = invoices.count()
    average_sale = total_invoiced / num_invoices if num_invoices > 0 else Decimal("0")
    
    # Get paid invoices for the sales list
    paid_invoices = invoices.filter(
        status__in=[WeldingInvoiceStatus.PAID, WeldingInvoiceStatus.PARTIAL]
    )
    
    # Build sales trend data - FIXED: Backend-safe date grouping for SQLite
    from django.db import connection
    from django.db.models import DateField
    from django.db.models import Func as DbFunc
    
    sales_lookup = {}
    try:
        # SQLite-safe date grouping
        if connection.vendor == "sqlite":
            # Use SQLite's built-in date() function
            date_expr = DbFunc(F("issue_date"), function="date", output_field=DateField())
        else:
            # Use Django's efficient TruncDate for PostgreSQL/MySQL
            date_expr = TruncDate("issue_date")
        
        sales_by_day = (
            invoices.annotate(date=date_expr)
            .values("date")
            .annotate(revenue=Sum("amount_paid"), count=Count("id"))
            .order_by("date")
        )
        
        sales_lookup = {s["date"]: {"revenue": float(s["revenue"] or 0), "count": s["count"]} for s in sales_by_day}
    except Exception as e:
        # Fallback: If DB aggregation fails, do Python grouping for the small window
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Sales page date aggregation failed: {e}. Falling back to Python grouping.")
        
        # Python fallback for small date range (safe for all DBs)
        from collections import defaultdict
        daily_sales = defaultdict(lambda: {"revenue": 0, "count": 0})
        for inv in invoices:
            day = inv.issue_date
            daily_sales[day]["revenue"] += float(inv.amount_paid or 0)
            daily_sales[day]["count"] += 1
        sales_lookup = dict(daily_sales)
    
    # Build chart data
    sales_trend = []
    for i in range(14):
        d = today - timedelta(days=13 - i)
        date_str = d.strftime("%b %d")
        day_data = sales_lookup.get(d, {"revenue": 0, "count": 0})
        sales_trend.append({
            "date": date_str,
            "revenue": day_data["revenue"],
            "count": day_data["count"],
        })
    
    ctx.update({
        "active_tab": "sales",
        "page_title": "Sales",
        
        # Filter state
        "filter_range": filter_range,
        "range_label": range_label,
        
        # KPIs
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "num_invoices": num_invoices,
        "average_sale": average_sale,
        
        # Sales list
        "invoices": invoices[:50],
        "paid_invoices": paid_invoices[:50],
        
        # Chart data
        "sales_trend_json": json.dumps(sales_trend),
    })
    
    return render(request, "verticals/welding/sales.html", ctx)


# Required import for Q objects
from django.db import models


# ==============================================================================
# REVENUE TRACKING
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def revenue_list(request: HttpRequest) -> HttpResponse:
    """Revenue tracking page for Welding vertical."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    from inventory.models_welding import WeldingRevenue
    
    today = timezone.now().date()
    
    # Parse date range from request
    from inventory.verticals.base import parse_date_range_from_request
    date_range = parse_date_range_from_request(request)
    active_range = date_range["active_range"]
    start_date = date_range["start_date"]
    end_date = date_range["end_date"]
    
    # Support custom start/end dates
    start_param = request.GET.get("start", "")
    end_param = request.GET.get("end", "")
    
    if start_param and end_param:
        try:
            from datetime import date as date_class
            start_date = date_class.fromisoformat(start_param)
            end_date = date_class.fromisoformat(end_param) + timedelta(days=1)  # Make end_date exclusive
            active_range = "custom"
            range_label = f"{start_date.strftime('%b %d')} - {(end_date - timedelta(days=1)).strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Invalid dates, fall back to active_range
            pass
    
    # Generate range label
    if active_range == "custom":
        pass  # Already set above
    elif active_range == "7d":
        range_label = "Last 7 Days"
    elif active_range == "30d":
        range_label = "Last 30 Days"
    else:  # mtd
        range_label = "Month to Date"
    
    # Get revenues in range
    revenues = WeldingRevenue.objects.filter(
        business=business,
        received_on__gte=start_date,
        received_on__lt=end_date,
    ).order_by("-received_on")
    
    # Calculate total
    total_revenue = revenues.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0"))
    )["total"]
    
    ctx.update({
        "active_tab": "revenue",
        "page_title": "Revenue",
        "active_range": active_range,
        "range_label": range_label,
        "start_date_param": start_param,
        "end_date_param": end_param,
        "revenues": revenues,
        "total_revenue": total_revenue,
        "revenue_count": revenues.count(),
    })
    
    return render(request, "verticals/welding/revenue.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def revenue_add(request: HttpRequest) -> HttpResponse:
    """Add a revenue entry."""
    business = request.active_business
    
    from inventory.models_welding import WeldingRevenue
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0.")
                return redirect("/verticals/welding/revenue/")
            
            category = request.POST.get("category", "other")
            description = request.POST.get("description", "").strip()
            notes = request.POST.get("notes", "")
            received_on = request.POST.get("received_on") or timezone.now().date()
            
            if not description:
                messages.error(request, "Description is required.")
                return redirect("/verticals/welding/revenue/")
            
            revenue = WeldingRevenue.objects.create(
                business=business,
                amount=amount,
                category=category,
                description=description,
                notes=notes,
                received_on=received_on,
                created_by=request.user,
            )
            
            messages.success(request, f"Revenue entry added: MWK {amount:,.0f}")
            return redirect("/verticals/welding/revenue/")
        except Exception as e:
            messages.error(request, f"Error adding revenue: {e}")
            return redirect("/verticals/welding/revenue/")
    
    # GET - render form
    ctx = base.base_context(request)
    ctx.update({
        "active_tab": "revenue",
    })
    return render(request, "verticals/welding/revenue_add.html", ctx)


# ==============================================================================
# COSTS TRACKING
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def costs_list(request: HttpRequest) -> HttpResponse:
    """Costs tracking page for Welding vertical."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    from inventory.models_welding import WeldingCost
    
    today = timezone.now().date()
    
    # Parse date range from request
    from inventory.verticals.base import parse_date_range_from_request
    date_range = parse_date_range_from_request(request)
    active_range = date_range["active_range"]
    start_date = date_range["start_date"]
    end_date = date_range["end_date"]
    
    # Support custom start/end dates
    start_param = request.GET.get("start", "")
    end_param = request.GET.get("end", "")
    
    if start_param and end_param:
        try:
            from datetime import date as date_class
            start_date = date_class.fromisoformat(start_param)
            end_date = date_class.fromisoformat(end_param) + timedelta(days=1)  # Make end_date exclusive
            active_range = "custom"
            range_label = f"{start_date.strftime('%b %d')} - {(end_date - timedelta(days=1)).strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Invalid dates, fall back to active_range
            pass
    
    # Generate range label
    if active_range == "custom":
        pass  # Already set above
    elif active_range == "7d":
        range_label = "Last 7 Days"
    elif active_range == "30d":
        range_label = "Last 30 Days"
    else:  # mtd
        range_label = "Month to Date"
    
    # Get costs in range
    costs = WeldingCost.objects.filter(
        business=business,
        incurred_on__gte=start_date,
        incurred_on__lt=end_date,
    ).order_by("-incurred_on")
    
    # Calculate total
    total_costs = costs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0"))
    )["total"]
    
    ctx.update({
        "active_tab": "costs",
        "page_title": "Costs",
        "active_range": active_range,
        "range_label": range_label,
        "start_date_param": start_param,
        "end_date_param": end_param,
        "costs": costs,
        "total_costs": total_costs,
        "costs_count": costs.count(),
    })
    
    return render(request, "verticals/welding/costs.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
@require_http_methods(["GET", "POST"])
def costs_add(request: HttpRequest) -> HttpResponse:
    """Add a cost entry."""
    business = request.active_business
    
    from inventory.models_welding import WeldingCost
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0.")
                return redirect("/verticals/welding/costs/")
            
            category = request.POST.get("category", "other")
            description = request.POST.get("description", "").strip()
            notes = request.POST.get("notes", "")
            incurred_on = request.POST.get("incurred_on") or timezone.now().date()
            
            if not description:
                messages.error(request, "Description is required.")
                return redirect("/verticals/welding/costs/")
            
            cost = WeldingCost.objects.create(
                business=business,
                amount=amount,
                category=category,
                description=description,
                notes=notes,
                incurred_on=incurred_on,
                created_by=request.user,
            )
            
            messages.success(request, f"Cost entry added: MWK {amount:,.0f}")
            return redirect("/verticals/welding/costs/")
        except Exception as e:
            messages.error(request, f"Error adding cost: {e}")
            return redirect("/verticals/welding/costs/")
    
    # GET - render form
    ctx = base.base_context(request)
    ctx.update({
        "active_tab": "costs",
    })
    return render(request, "verticals/welding/costs_add.html", ctx)


# ---------------------------------------------------------------------------
# Phase 2: Workshop Intelligence Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def workshop_intelligence(request):
    """Enhanced workshop analytics with production intelligence."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    if not business:
        return redirect("verticals:no_business")

    try:
        from inventory.services.welding_intelligence import (
            get_workshop_intelligence, get_production_insights,
        )
        workshop_data = get_workshop_intelligence(business)
        production_insights = get_production_insights(business)
    except Exception:
        workshop_data = {}
        production_insights = []

    ctx.update({
        "active_tab": "intelligence",
        "workshop": workshop_data,
        "insights": production_insights,
    })
    return render(request, "verticals/welding/workshop_intelligence.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def client_management(request):
    """Client analytics and management for welding workshop."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    if not business:
        return redirect("verticals:no_business")

    try:
        from inventory.services.welding_intelligence import get_client_analytics
        client_data = get_client_analytics(business)
    except Exception:
        client_data = {}

    ctx.update({
        "active_tab": "clients",
        "clients": client_data,
    })
    return render(request, "verticals/welding/client_management.html", ctx)
