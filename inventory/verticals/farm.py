# inventory/verticals/farm.py
"""
Farm Manager vertical adapter.
Provides dashboard and view functions for farm profitability tracking.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmCropSeason,
    FarmEntryType,
    FarmExpenseCategory,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmLivestockEvent,
    FarmPaymentMethod,
    FarmSeasonStatus,
    FarmUnit,
)
from inventory.services.farm_manager import (
    AlertItem,
    compute_alerts,
    compute_livestock_snapshot,
    compute_monthly_profit,
    crop_season_to_data,
    ledger_entry_to_data,
    livestock_batch_to_data,
    livestock_event_to_data,
)
from inventory.verticals import base
from tenants.utils import require_business


# ==============================================================================
# DASHBOARD
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def dashboard(request: HttpRequest) -> HttpResponse:
    """Farm Manager dashboard with KPIs and quick actions."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    # Get all ledger entries for computations
    ledger_qs = FarmLedgerEntry.objects.filter(business=business)
    ledger_entries = [ledger_entry_to_data(e) for e in ledger_qs]
    
    # Current month profit
    current_profit = compute_monthly_profit(ledger_entries, current_year, current_month)
    
    # Previous month for comparison
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    previous_profit = compute_monthly_profit(ledger_entries, prev_year, prev_month)
    
    # Livestock snapshots
    batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
    all_events = FarmLivestockEvent.objects.filter(batch__business=business)
    events_data = [livestock_event_to_data(e) for e in all_events]
    
    livestock_snapshots = []
    for batch in batches:
        batch_data = livestock_batch_to_data(batch)
        snapshot = compute_livestock_snapshot(batch_data, events_data, today)
        livestock_snapshots.append(snapshot)
    
    # Days since last sale
    last_sale = ledger_qs.filter(entry_type=FarmEntryType.SALE).order_by("-date").first()
    days_since_last_sale = None
    if last_sale:
        days_since_last_sale = (today - last_sale.date).days
    
    # Compute alerts
    alerts = compute_alerts(
        current_month_profit=current_profit,
        previous_month_profit=previous_profit,
        livestock_snapshots=livestock_snapshots,
        days_since_last_sale=days_since_last_sale,
    )
    
    # Recent ledger entries
    recent_entries = ledger_qs.order_by("-date", "-created_at")[:10]
    
    # Active crop seasons
    active_seasons = FarmCropSeason.objects.filter(
        business=business,
        status__in=[FarmSeasonStatus.PLANNING, FarmSeasonStatus.ACTIVE],
    ).order_by("-start_date")[:5]
    
    # Total livestock value (if valuation enabled)
    total_livestock_value = Decimal("0")
    for snapshot in livestock_snapshots:
        if snapshot.estimated_value:
            total_livestock_value += snapshot.estimated_value
    
    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Farm Manager",
        "hero_blurb": "Track your farm profitability, livestock, and crops in one place.",
        
        # KPIs
        "profit_this_month": current_profit.net_profit,
        "income_this_month": current_profit.total_income,
        "expenses_this_month": current_profit.total_expenses,
        "sales_count_this_month": current_profit.sales_count,
        
        # Top expense categories
        "top_expense_categories": current_profit.top_expense_categories[:3],
        
        # Livestock summary
        "livestock_batches": batches,
        "livestock_snapshots": livestock_snapshots,
        "total_livestock_count": sum(s.count_current for s in livestock_snapshots),
        "total_livestock_value": total_livestock_value if total_livestock_value > 0 else None,
        
        # Crops
        "active_seasons": active_seasons,
        
        # Recent activity
        "recent_entries": recent_entries,
        
        # Alerts
        "alerts": alerts,
        "alerts_count": len(alerts),
        "critical_alerts_count": len([a for a in alerts if a.severity == "critical"]),
        
        # Quick action URLs
        "url_add_expense": "/verticals/farm/ledger/add-expense/",
        "url_add_sale": "/verticals/farm/ledger/add-sale/",
        "url_livestock_add_event": "/verticals/farm/livestock/add-event/",
        "url_season_create": "/verticals/farm/crops/create/",
    })
    
    return render(request, "verticals/farm/dashboard.html", ctx)


# ==============================================================================
# LEDGER (EXPENSES & SALES)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def ledger_list(request: HttpRequest) -> HttpResponse:
    """List all ledger entries with filtering."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Filter parameters
    entry_type = request.GET.get("type", "")
    enterprise = request.GET.get("enterprise", "")
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")
    
    entries = FarmLedgerEntry.objects.filter(business=business).order_by("-date", "-created_at")
    
    if entry_type:
        entries = entries.filter(entry_type=entry_type)
    if enterprise:
        entries = entries.filter(enterprise_type=enterprise)
    if date_from:
        entries = entries.filter(date__gte=date_from)
    if date_to:
        entries = entries.filter(date__lte=date_to)
    
    # Summary totals
    totals = entries.aggregate(
        total_income=Coalesce(
            Sum("amount_mwk", filter=~models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        total_expenses=Coalesce(
            Sum("amount_mwk", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
    )
    
    ctx.update({
        "active_tab": "ledger",
        "entries": entries[:100],  # Paginate in production
        "total_entries": entries.count(),
        "total_income": totals["total_income"],
        "total_expenses": totals["total_expenses"],
        "net_profit": totals["total_income"] - totals["total_expenses"],
        "filter_type": entry_type,
        "filter_enterprise": enterprise,
        "filter_from": date_from,
        "filter_to": date_to,
        "entry_types": FarmEntryType.choices,
        "expense_categories": FarmExpenseCategory.choices,
    })
    
    return render(request, "verticals/farm/ledger_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def add_expense(request: HttpRequest) -> HttpResponse:
    """Add a new expense entry."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            entry = FarmLedgerEntry.objects.create(
                business=business,
                date=request.POST.get("date") or timezone.now().date(),
                entry_type=FarmEntryType.EXPENSE,
                enterprise_type=request.POST.get("enterprise_type", "general"),
                category=request.POST.get("category", "other"),
                description=request.POST.get("description", ""),
                amount_mwk=amount,
                quantity=request.POST.get("quantity") or None,
                unit=request.POST.get("unit", "item"),
                payment_method=request.POST.get("payment_method", "cash"),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            messages.success(request, f"Expense of MWK {amount:,.2f} recorded successfully.")
            
            # Return to dashboard or ledger
            next_url = request.POST.get("next", "/verticals/farm/dashboard/")
            return redirect(next_url)
        except Exception as e:
            messages.error(request, f"Error recording expense: {e}")
    
    ctx.update({
        "active_tab": "ledger",
        "form_title": "Add Expense",
        "entry_type": "expense",
        "expense_categories": FarmExpenseCategory.choices,
        "payment_methods": FarmPaymentMethod.choices,
        "units": FarmUnit.choices,
    })
    
    return render(request, "verticals/farm/ledger_add.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def add_sale(request: HttpRequest) -> HttpResponse:
    """Add a new sale entry."""
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
            
            next_url = request.POST.get("next", "/verticals/farm/dashboard/")
            return redirect(next_url)
        except Exception as e:
            messages.error(request, f"Error recording sale: {e}")
    
    ctx.update({
        "active_tab": "ledger",
        "form_title": "Add Sale",
        "entry_type": "sale",
        "payment_methods": FarmPaymentMethod.choices,
        "units": FarmUnit.choices,
    })
    
    return render(request, "verticals/farm/ledger_add.html", ctx)


# ==============================================================================
# LIVESTOCK
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_list(request: HttpRequest) -> HttpResponse:
    """List all livestock batches."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    batches = FarmLivestockBatch.objects.filter(business=business).order_by("-created_at")
    
    # Compute snapshots for each batch
    all_events = FarmLivestockEvent.objects.filter(batch__business=business)
    events_data = [livestock_event_to_data(e) for e in all_events]
    
    batch_snapshots = []
    for batch in batches:
        batch_data = livestock_batch_to_data(batch)
        snapshot = compute_livestock_snapshot(batch_data, events_data)
        batch_snapshots.append({
            "batch": batch,
            "snapshot": snapshot,
        })
    
    ctx.update({
        "active_tab": "livestock",
        "batch_snapshots": batch_snapshots,
        "total_animals": sum(bs["snapshot"].count_current for bs in batch_snapshots),
    })
    
    return render(request, "verticals/farm/livestock_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def livestock_batch_create(request: HttpRequest) -> HttpResponse:
    """Create a new livestock batch."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            batch = FarmLivestockBatch.objects.create(
                business=business,
                animal_type=request.POST.get("animal_type", "pigs"),
                name=request.POST.get("name", ""),
                count_current=int(request.POST.get("initial_count", 0)),
                valuation_enabled=request.POST.get("valuation_enabled") == "on",
                avg_weight_kg=request.POST.get("avg_weight_kg") or None,
                price_per_kg_mwk=request.POST.get("price_per_kg") or None,
                price_per_animal_mwk=request.POST.get("price_per_animal") or None,
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            
            # Create initial purchase event if initial_count > 0
            initial_count = int(request.POST.get("initial_count", 0))
            if initial_count > 0:
                FarmLivestockEvent.objects.create(
                    batch=batch,
                    event_type="purchase",
                    date=timezone.now().date(),
                    count=initial_count,
                    notes="Initial stock on batch creation",
                    created_by=request.user,
                )
            
            messages.success(request, f"Batch '{batch.name}' created successfully.")
            return redirect("/verticals/farm/livestock/")
        except Exception as e:
            messages.error(request, f"Error creating batch: {e}")
    
    from inventory.models_farm import FarmAnimalType
    ctx.update({
        "active_tab": "livestock",
        "animal_types": FarmAnimalType.choices,
    })
    
    return render(request, "verticals/farm/livestock_batch_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def livestock_add_event(request: HttpRequest) -> HttpResponse:
    """Add an event to a livestock batch."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
    
    if request.method == "POST":
        try:
            batch_id = request.POST.get("batch_id")
            batch = get_object_or_404(FarmLivestockBatch, id=batch_id, business=business)
            
            event_type = request.POST.get("event_type")
            count = int(request.POST.get("count", 0))
            
            event = FarmLivestockEvent.objects.create(
                batch=batch,
                event_type=event_type,
                date=request.POST.get("date") or timezone.now().date(),
                count=count,
                unit_price_mwk=request.POST.get("unit_price") or None,
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            
            # Update batch count
            if event_type in ("birth", "purchase", "transfer_in"):
                batch.count_current += count
            else:
                batch.count_current = max(0, batch.count_current - count)
            batch.save(update_fields=["count_current"])
            
            messages.success(request, f"Event recorded: {event.get_event_type_display()} x {count}")
            return redirect("/verticals/farm/livestock/")
        except Exception as e:
            messages.error(request, f"Error recording event: {e}")
    
    from inventory.models_farm import FarmLivestockEventType
    ctx.update({
        "active_tab": "livestock",
        "batches": batches,
        "event_types": FarmLivestockEventType.choices,
    })
    
    return render(request, "verticals/farm/livestock_add_event.html", ctx)


# ==============================================================================
# CROPS (SEASONS)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def crops_list(request: HttpRequest) -> HttpResponse:
    """List all crop seasons."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    seasons = FarmCropSeason.objects.filter(business=business).order_by("-start_date")
    
    ctx.update({
        "active_tab": "crops",
        "seasons": seasons,
        "status_choices": FarmSeasonStatus.choices,
    })
    
    return render(request, "verticals/farm/crops_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def crop_season_create(request: HttpRequest) -> HttpResponse:
    """Create a new crop season."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            season = FarmCropSeason.objects.create(
                business=business,
                crop_type=request.POST.get("crop_type", "maize"),
                name=request.POST.get("name", ""),
                start_date=request.POST.get("start_date"),
                end_date=request.POST.get("end_date") or None,
                area_value=Decimal(request.POST.get("area_value", "1")),
                area_unit=request.POST.get("area_unit", "acre"),
                projected_yield=request.POST.get("projected_yield") or None,
                yield_unit=request.POST.get("yield_unit", "bag"),
                projected_price_per_unit_mwk=request.POST.get("projected_price") or None,
                status=request.POST.get("status", "planning"),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            messages.success(request, f"Season '{season.name}' created successfully.")
            return redirect("/verticals/farm/crops/")
        except Exception as e:
            messages.error(request, f"Error creating season: {e}")
    
    from inventory.models_farm import FarmCropType
    ctx.update({
        "active_tab": "crops",
        "crop_types": FarmCropType.choices,
        "status_choices": FarmSeasonStatus.choices,
    })
    
    return render(request, "verticals/farm/crop_season_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def crop_season_detail(request: HttpRequest, season_id: int) -> HttpResponse:
    """View crop season details with projections vs actuals."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    season = get_object_or_404(FarmCropSeason, id=season_id, business=business)
    
    # Get ledger entries for this season
    ledger_entries = FarmLedgerEntry.objects.filter(crop_season=season)
    
    # Calculate totals
    totals = ledger_entries.aggregate(
        total_income=Coalesce(
            Sum("amount_mwk", filter=~models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        total_expenses=Coalesce(
            Sum("amount_mwk", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
    )
    
    ctx.update({
        "active_tab": "crops",
        "season": season,
        "ledger_entries": ledger_entries,
        "actual_income": totals["total_income"],
        "actual_expenses": totals["total_expenses"],
        "actual_profit": totals["total_income"] - totals["total_expenses"],
    })
    
    return render(request, "verticals/farm/crop_season_detail.html", ctx)


# ==============================================================================
# REPORTS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def reports(request: HttpRequest) -> HttpResponse:
    """Farm reports and exports."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    ctx.update({
        "active_tab": "reports",
    })
    
    return render(request, "verticals/farm/reports.html", ctx)


# Required import for aggregation
from django.db import models

