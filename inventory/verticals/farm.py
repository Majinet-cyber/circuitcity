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
    get_farm_dashboard_snapshot,
    ledger_entry_to_data,
    livestock_batch_to_data,
    livestock_event_to_data,
)
from inventory.verticals import base
from tenants.utils import require_business
from django.urls import reverse


# ==============================================================================
# DASHBOARD
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def dashboard(request: HttpRequest) -> HttpResponse:
    """Farm Manager dashboard with KPIs, insights, and filter integration."""
    import json
    import logging
    from django.db import OperationalError
    from django.db.models import Sum
    
    logger = logging.getLogger(__name__)
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return redirect("verticals:no_business")
    
    # Get filter state
    from inventory.services.farm_filters import parse_farm_filters, get_available_filter_options, apply_filters_to_ledger, apply_filters_to_seasons
    filter_state = parse_farm_filters(request, business)
    filter_options = get_available_filter_options(business)
    
    today = timezone.now().date()
    
    # Get all ledger entries for computations (FILTERED)
    # FAIL-SAFE: Handle missing table gracefully (if migrations not applied)
    try:
        ledger_qs = FarmLedgerEntry.objects.filter(business=business)
        # Apply filters
        ledger_qs = apply_filters_to_ledger(ledger_qs, filter_state)
        ledger_entries = [ledger_entry_to_data(e) for e in ledger_qs]
    except OperationalError as e:
        if "no such table: inventory_farmledgerentry" in str(e):
            logger.warning(
                "Farm migrations not applied; missing inventory_farmledgerentry table. "
                "Run 'python manage.py migrate inventory' to fix."
            )
            ledger_qs = FarmLedgerEntry.objects.none()
            ledger_entries = []
            ctx["farm_setup_required"] = True
        else:
            # Re-raise other database errors
            raise
    
    # Livestock snapshots
    # FAIL-SAFE: Handle missing tables gracefully
    try:
        batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
        all_events = FarmLivestockEvent.objects.filter(batch__business=business)
        events_data = [livestock_event_to_data(e) for e in all_events]
        
        livestock_snapshots = []
        for batch in batches:
            batch_data = livestock_batch_to_data(batch)
            snapshot = compute_livestock_snapshot(batch_data, events_data, today)
            livestock_snapshots.append(snapshot)
        
        # === NEW: Livestock breakdown by type for dashboard ===
        livestock_by_type = {}
        for batch in batches:
            atype = batch.get_animal_type_display()
            if atype not in livestock_by_type:
                livestock_by_type[atype] = {"count": 0, "icon": _get_animal_emoji(batch.animal_type)}
            livestock_by_type[atype]["count"] += batch.count_current
        
    except OperationalError as e:
        if "no such table" in str(e):
            logger.warning(f"Farm migrations not applied; missing table: {e}")
            batches = FarmLivestockBatch.objects.none()
            livestock_snapshots = []
            livestock_by_type = {}
            ctx["farm_setup_required"] = True
        else:
            raise
    
    # Days since last sale
    last_sale = ledger_qs.filter(entry_type=FarmEntryType.SALE).order_by("-date").first()
    days_since_last_sale = None
    if last_sale:
        days_since_last_sale = (today - last_sale.date).days
    
    # Active crop seasons (apply filter if needed)
    # FAIL-SAFE: Handle missing table gracefully
    try:
        active_seasons = FarmCropSeason.objects.filter(
            business=business,
            status__in=[FarmSeasonStatus.PLANNING, FarmSeasonStatus.ACTIVE],
        )
        # Apply filters
        active_seasons = apply_filters_to_seasons(active_seasons, filter_state)
        active_seasons = active_seasons.order_by("-start_date")[:5]
        
        # Compute totals for crop summary (inside try block to handle lazy evaluation)
        active_seasons_count = active_seasons.count()
        total_crop_area = sum((s.area_value for s in active_seasons), Decimal("0"))
        projected_crop_income = sum(
            (s.projected_income_mwk for s in active_seasons if s.projected_income_mwk),
            Decimal("0"),
        ) or None
        
        # === NEW: Detailed crop breakdown for Farm Snapshot ===
        crops_breakdown = []
        for season in active_seasons:
            weeks_since_planting = max(0, (today - season.start_date).days // 7)
            crops_breakdown.append({
                "id": season.id,
                "name": season.name,
                "crop_type": season.get_crop_type_display(),
                "area": float(season.area_value),
                "area_unit": season.area_unit,
                "year": season.start_date.year,
                "weeks_since_planting": weeks_since_planting,
                "stage": f"Week {weeks_since_planting}",
                "status": season.get_status_display(),
                "emoji": _get_crop_emoji(season.crop_type),
            })
        
    except OperationalError as e:
        if "no such table" in str(e):
            logger.warning(f"Farm migrations not applied; missing table: {e}")
            active_seasons = FarmCropSeason.objects.none()
            active_seasons_count = 0
            total_crop_area = Decimal("0")
            projected_crop_income = None
            crops_breakdown = []
            ctx["farm_setup_required"] = True
        else:
            raise
    
    # === NEW: Assets preview for dashboard ===
    from inventory.models_farm import FarmAsset
    try:
        assets = FarmAsset.objects.filter(business=business, is_active=True)
        assets_preview = list(assets.order_by("-value_mwk", "-created_at")[:6])
        total_assets_value = assets.aggregate(total=Sum("value_mwk"))["total"] or Decimal("0")
        assets_count = assets.count()
    except OperationalError:
        assets_preview = []
        total_assets_value = Decimal("0")
        assets_count = 0
    
    # === NEW: AI Insights using farm insights engine ===
    from inventory.services.farm_insights import generate_all_insights
    try:
        ai_insights = generate_all_insights(
            business=business,
            seasons=list(active_seasons),
            batches=list(batches),
            today=today,
            limit=10,
        )
        # Convert to dicts for template
        ai_insights_data = [insight.to_dict() for insight in ai_insights]
    except Exception as e:
        logger.warning(f"Failed to generate AI insights: {e}")
        ai_insights_data = []
    
    # === SSOT: Get complete dashboard snapshot ===
    snapshot = get_farm_dashboard_snapshot(
        ledger_entries=ledger_entries,
        livestock_snapshots=livestock_snapshots,
        active_seasons_count=active_seasons_count,
        total_crop_area=total_crop_area,
        projected_crop_income=projected_crop_income,
        today=today,
        days_since_last_sale=days_since_last_sale,
    )
    
    # Recent ledger entries (for display only, not computation)
    recent_entries = ledger_qs.order_by("-date", "-created_at")[:10]
    
    # Serialize chart data to JSON for template
    profit_trend_json = json.dumps(snapshot.profit_trend_data)
    expense_breakdown_json = json.dumps(snapshot.expense_breakdown)
    
    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Farm Manager",
        "hero_blurb": "Track your farm profitability, livestock, and crops in one place.",
        
        # SSOT snapshot (all computed values)
        "snapshot": snapshot,
        
        # Filter state (NEW)
        "filter_state": filter_state,
        "filter_options": filter_options,
        
        # Chart data (JSON for Chart.js)
        "profit_trend_json": profit_trend_json,
        "expense_breakdown_json": expense_breakdown_json,
        
        # For backwards compatibility with existing template parts
        "profit_this_month": snapshot.net_profit_mwk,
        "income_this_month": snapshot.total_income_mwk,
        "expenses_this_month": snapshot.total_expenses_mwk,
        "sales_count_this_month": snapshot.sales_count,
        "top_expense_categories": snapshot.expense_breakdown,
        
        # Livestock display data
        "livestock_batches": batches,
        "livestock_snapshots": livestock_snapshots,
        "total_livestock_count": snapshot.total_livestock_count,
        "total_livestock_value": snapshot.total_livestock_value,
        "livestock_by_type": livestock_by_type,  # NEW: for dashboard breakdown
        
        # Crops
        "active_seasons": active_seasons,
        "crops_breakdown": crops_breakdown,  # NEW: detailed crop info
        
        # Assets preview (NEW)
        "assets_preview": assets_preview,
        "total_assets_value": total_assets_value,
        "assets_count": assets_count,
        
        # AI Insights (NEW)
        "ai_insights": ai_insights_data,
        
        # Recent activity
        "recent_entries": recent_entries,
        
        # Alerts (from SSOT)
        "alerts": snapshot.alerts,
        "alerts_count": len(snapshot.alerts),
        "critical_alerts_count": snapshot.critical_alerts_count,
        
        # NOTE: Quick action buttons (Add Expense, Add Sale, Livestock Event, New Season)
        # were REMOVED from dashboard per Jan 2026 redesign. These actions are accessible
        # via sidebar navigation to their respective pages (Expenses, Sales, Livestock, Seasons).
    })
    
    return render(request, "verticals/farm/dashboard.html", ctx)


def _get_animal_emoji(animal_type: str) -> str:
    """Get emoji for an animal type."""
    ANIMAL_EMOJIS = {
        "pigs": "🐖",
        "cattle": "🐄",
        "goats": "🐐",
        "chickens": "🐔",
        "ducks": "🦆",
        "rabbits": "🐇",
        "sheep": "🐑",
        "fish": "🐟",
    }
    return ANIMAL_EMOJIS.get(animal_type, "🐾")


def _get_crop_emoji(crop_type: str) -> str:
    """Get emoji for a crop type."""
    CROP_EMOJIS = {
        "maize": "🌽",
        "soya": "🫘",
        "groundnuts": "🥜",
        "tobacco": "🍂",
        "cotton": "🧶",
        "rice": "🍚",
        "beans": "🫘",
        "cassava": "🥔",
        "sweet_potato": "🍠",
        "vegetables": "🥬",
    }
    return CROP_EMOJIS.get(crop_type, "🌱")


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
    """Add an event to a livestock batch with smart recommendations."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
    
    # Pre-select batch if specified in URL
    preselect_batch_id = request.GET.get("batch_id")
    preselect_type = request.GET.get("type", "")
    
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
    
    # === Smart Entry: Get recommended actions for selected batch ===
    from inventory.services.farm_insights import (
        get_recommended_actions_for_season,
        LIVESTOCK_ENTRY_TYPES,
    )
    
    recommended_actions = []
    if preselect_batch_id:
        try:
            selected_batch = FarmLivestockBatch.objects.get(id=preselect_batch_id, business=business)
            today = timezone.now().date()
            actions = get_recommended_actions_for_season(selected_batch, today, limit=4)
            recommended_actions = [action.to_dict() for action in actions]
        except FarmLivestockBatch.DoesNotExist:
            pass
    
    from inventory.models_farm import FarmLivestockEventType
    ctx.update({
        "active_tab": "livestock",
        "batches": batches,
        "event_types": FarmLivestockEventType.choices,
        "entry_types": LIVESTOCK_ENTRY_TYPES,
        "recommended_actions": recommended_actions,
        "preselect_batch_id": preselect_batch_id,
        "preselect_type": preselect_type,
        "season_type": "livestock",
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
    """Create a new crop season with Smart Agronomy integration."""
    import json
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
            
            # Handle agronomy recommendations if applied
            apply_rec = request.POST.get("apply_recommendations", "")
            if apply_rec == "true":
                # Create draft expense items for fertiliser
                from inventory.services.farm_agronomy import create_draft_expense_items
                try:
                    draft_items = create_draft_expense_items(
                        season.crop_type,
                        season.area_value,
                        use_high_estimate=False  # Conservative
                    )
                    # Create actual expense entries
                    for item in draft_items:
                        FarmLedgerEntry.objects.create(
                            business=business,
                            date=season.start_date,
                            entry_type=FarmEntryType.EXPENSE,
                            enterprise_type="crop",
                            category=item["category"],
                            description=item["description"],
                            amount_mwk=Decimal("0"),  # User can fill in actual cost later
                            quantity=Decimal(str(item["quantity"])),
                            unit=item["unit"],
                            notes=f"[Auto-generated from Smart Agronomy] {item['notes']}",
                            crop_season=season,
                            created_by=request.user,
                        )
                    messages.info(request, "Smart Agronomy fertiliser plan added as draft expenses.")
                except Exception as e:
                    # Don't fail season creation if agronomy fails
                    pass
            
            messages.success(request, f"Season '{season.name}' created successfully.")
            return redirect("/verticals/farm/crops/")
        except Exception as e:
            messages.error(request, f"Error creating season: {e}")
    
    # Handle crop prefill from query param (from crops index cards)
    prefill_crop = request.GET.get("crop", "")
    prefill_name = ""
    if prefill_crop:
        # Generate default name
        from datetime import datetime
        year = datetime.now().year
        crop_label = prefill_crop.replace("_", " ").title()
        prefill_name = f"{crop_label} {year} Season"
    
    from inventory.models_farm import FarmCropType
    ctx.update({
        "active_tab": "crops",
        "crop_types": FarmCropType.choices,
        "status_choices": FarmSeasonStatus.choices,
        "prefill_crop": prefill_crop,
        "prefill_name": prefill_name,
        "agronomy_data": json.dumps({}),  # Placeholder for server-side agronomy data
    })
    
    return render(request, "verticals/farm/crop_season_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def crop_season_detail(request: HttpRequest, season_id: int) -> HttpResponse:
    """View crop season details with projections vs actuals and smart recommendations."""
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
    
    # === Smart Season Entry: Get recommended actions ===
    from inventory.services.farm_insights import (
        get_recommended_actions_for_season,
        get_entry_types_for_season,
        calculate_fertilizer_estimate,
        calculate_yield_estimate,
        CROP_ENTRY_TYPES,
    )
    
    today = timezone.now().date()
    recommended_actions = get_recommended_actions_for_season(season, today, limit=4)
    recommended_actions_data = [action.to_dict() for action in recommended_actions]
    
    # Get entry types for crop seasons
    entry_types = CROP_ENTRY_TYPES
    
    # Calculate weeks since planting
    weeks_since_planting = max(0, (today - season.start_date).days // 7)
    
    # Get fertilizer estimates
    fertilizer_estimate = calculate_fertilizer_estimate(
        season.crop_type,
        float(season.area_value),
        weeks_since_planting,
    )
    
    # Get yield estimates
    yield_estimate = calculate_yield_estimate(
        season.crop_type,
        float(season.area_value),
    )
    
    ctx.update({
        "active_tab": "crops",
        "season": season,
        "ledger_entries": ledger_entries,
        "actual_income": totals["total_income"],
        "actual_expenses": totals["total_expenses"],
        "actual_profit": totals["total_income"] - totals["total_expenses"],
        
        # Smart Entry context (NEW)
        "recommended_actions": recommended_actions_data,
        "entry_types": entry_types,
        "weeks_since_planting": weeks_since_planting,
        "fertilizer_estimate": fertilizer_estimate,
        "yield_estimate": yield_estimate,
        "season_type": "crop",
    })
    
    return render(request, "verticals/farm/crop_season_detail.html", ctx)


# ==============================================================================
# REPORTS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def reports(request: HttpRequest) -> HttpResponse:
    """Farm reports and exports with filter integration."""
    import json
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get filter state
    from inventory.services.farm_filters import parse_farm_filters, get_available_filter_options, apply_filters_to_ledger
    filter_state = parse_farm_filters(request, business)
    filter_options = get_available_filter_options(business)
    
    # Get filtered ledger data
    ledger_qs = FarmLedgerEntry.objects.filter(business=business)
    ledger_qs = apply_filters_to_ledger(ledger_qs, filter_state)
    
    # Calculate summary metrics
    totals = ledger_qs.aggregate(
        total_income=Coalesce(
            Sum("amount_mwk", filter=~models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        total_expenses=Coalesce(
            Sum("amount_mwk", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        sales_count=Count("id", filter=models.Q(entry_type=FarmEntryType.SALE)),
        expense_count=Count("id", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
    )
    
    net_profit = totals["total_income"] - totals["total_expenses"]
    
    # Top expense categories
    top_categories = (
        ledger_qs.filter(entry_type=FarmEntryType.EXPENSE)
        .values("category")
        .annotate(total=Sum("amount_mwk"))
        .order_by("-total")[:5]
    )
    
    # Sales by enterprise type (crop/livestock breakdown)
    sales_by_type = (
        ledger_qs.filter(entry_type=FarmEntryType.SALE)
        .values("enterprise_type")
        .annotate(total=Sum("amount_mwk"), count=Count("id"))
        .order_by("-total")
    )
    
    ctx.update({
        "active_tab": "reports",
        "hero_title": "Farm Metrics & Reports",
        "hero_blurb": "View insights and export your farm data",
        "filter_state": filter_state,
        "filter_options": filter_options,
        # Summary metrics
        "total_income": totals["total_income"],
        "total_expenses": totals["total_expenses"],
        "net_profit": net_profit,
        "sales_count": totals["sales_count"],
        "expense_count": totals["expense_count"],
        # Breakdowns
        "top_categories": top_categories,
        "sales_by_type": sales_by_type,
    })
    
    return render(request, "verticals/farm/reports.html", ctx)


# Required import for aggregation
from django.db import models

# Import new premium view functions from separate modules
# This allows verticals/urls.py to reference farm.sales_landing, etc.
from inventory.verticals.farm_sales import (
    sales_landing,
    sales_crops,
    sales_livestock,
    sales_record,
)
from inventory.verticals.farm_expenses import (
    expenses_landing,
    expenses_record,
    expenses_export,
)
from inventory.verticals.farm_assets import assets_landing
from inventory.verticals.farm_locations import (
    locations_list,
    locations_create,
    locations_edit,
)

