# inventory/verticals/welding.py
"""
Welding Manager vertical adapter.
Provides dashboard, quotes, jobs, materials, and invoice generation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
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
    
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    # Quote stats
    quotes = WeldingQuote.objects.filter(business=business)
    quotes_this_month = quotes.filter(created_at__date__gte=month_start)
    quotes_pending = quotes.filter(status__in=[WeldingQuoteStatus.DRAFT, WeldingQuoteStatus.SENT])
    quotes_accepted = quotes.filter(status=WeldingQuoteStatus.ACCEPTED)
    
    # Job stats
    jobs = WeldingJob.objects.filter(business=business)
    jobs_active = jobs.filter(status__in=[WeldingJobStatus.PENDING, WeldingJobStatus.IN_PROGRESS])
    jobs_ready = jobs.filter(status=WeldingJobStatus.READY)
    jobs_completed_this_month = jobs.filter(
        status=WeldingJobStatus.DELIVERED,
        delivered_at__date__gte=month_start,
    )
    
    # Revenue this month (from delivered jobs)
    revenue_this_month = jobs_completed_this_month.aggregate(
        total=Coalesce(Sum("final_price"), Decimal("0"))
    )["total"]
    
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
    
    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Welding Manager",
        "hero_blurb": "Create quotes in seconds, track jobs, and generate invoices quickly.",
        
        # KPIs
        "quotes_this_month": quotes_this_month.count(),
        "quotes_pending": quotes_pending.count(),
        "jobs_active": jobs_active.count(),
        "jobs_ready": jobs_ready.count(),
        "revenue_this_month": revenue_this_month,
        "total_outstanding": total_outstanding.get("total", Decimal("0")),
        
        # Low stock alert
        "low_stock_count": low_stock_materials.count(),
        "low_stock_materials": low_stock_materials[:5],
        
        # Recent activity
        "recent_quotes": recent_quotes,
        "recent_jobs": recent_jobs,
        
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
    """List all welding materials."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure materials seeded
    ensure_materials_seeded(business)
    
    category_filter = request.GET.get("category", "")
    
    materials = WeldingMaterial.objects.filter(
        business=business,
        is_active=True,
    ).order_by("category", "name")
    
    if category_filter:
        materials = materials.filter(category=category_filter)
    
    ctx.update({
        "active_tab": "materials",
        "materials": materials,
        "categories": WeldingMaterialCategory.choices,
        "filter_category": category_filter,
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
    """Create a new quote from template."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure templates exist
    ensure_templates_seeded()
    
    templates = WeldingTemplate.objects.filter(
        models.Q(business=None) | models.Q(business=business),
        is_active=True,
    )
    
    if request.method == "POST":
        try:
            template_code = request.POST.get("template_code")
            template = templates.filter(code=template_code).first()
            
            customer_name = request.POST.get("customer_name", "")
            customer_phone = request.POST.get("customer_phone", "")
            
            # Get materials for pricing
            materials_qs = WeldingMaterial.objects.filter(business=business, is_active=True)
            materials_catalog = {m.code: material_to_data(m) for m in materials_qs}
            
            # Get tuning if exists
            tuning = None
            if template:
                tuning_obj = WeldingEstimatorTuning.objects.filter(
                    business=business,
                    template=template,
                ).first()
                if tuning_obj:
                    tuning = tuning_to_data(tuning_obj)
            
            # Labour rate (could be from settings, using default)
            labour_rate = Decimal(request.POST.get("labour_rate", "5000"))
            overhead_pct = Decimal(request.POST.get("overhead_pct", "10"))
            margin_pct = Decimal(request.POST.get("margin_pct", "25"))
            
            # Generate quote
            specs = {}  # Could parse from form
            result = generate_quote_from_template(
                template_code=template_code,
                specs=specs,
                materials_catalog=materials_catalog,
                tuning=tuning,
                labour_rate_per_hour=labour_rate,
                overhead_pct=overhead_pct,
                margin_pct=margin_pct,
            )
            
            # Create quote record
            quote = WeldingQuote.objects.create(
                business=business,
                customer_name=customer_name,
                customer_phone=customer_phone,
                template=template,
                specs=specs,
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
            
            messages.success(request, f"Quote {quote.quote_number} created for MWK {quote.total:,.2f}")
            return redirect(f"/verticals/welding/quotes/{quote.id}/")
            
        except Exception as e:
            messages.error(request, f"Error creating quote: {e}")
    
    ctx.update({
        "active_tab": "quotes",
        "templates": templates,
    })
    
    return render(request, "verticals/welding/quote_create.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.WELDING)
def quote_detail(request: HttpRequest, quote_id: int) -> HttpResponse:
    """View quote details."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    quote = get_object_or_404(WeldingQuote, id=quote_id, business=business)
    
    ctx.update({
        "active_tab": "quotes",
        "quote": quote,
    })
    
    return render(request, "verticals/welding/quote_detail.html", ctx)


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


# Required import for Q objects
from django.db import models

