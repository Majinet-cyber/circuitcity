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
    FARM_SUBTYPES_BY_ANIMAL,
    LIVESTOCK_COUNT_ADDING_EVENTS,
    LIVESTOCK_COUNT_REMOVING_EVENTS,
    LIVESTOCK_NON_COUNT_EVENTS,
    FarmAnimalGender,
    FarmAnimalType,
    FarmBatchImage,
    FarmCropSeason,
    FarmEntryType,
    FarmExpenseCategory,
    FarmHealthStatus,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmLivestockEvent,
    FarmLivestockEventType,
    FarmLivestockSubType,
    FarmPaymentMethod,
    FarmSaleAvailability,
    FarmSeasonStatus,
    FarmUnit,
    FarmVaccinationStatus,
    subtype_choices_for_animal_type,
)
from inventory.models import Location
from inventory.services.farm_marketplace import (
    sync_livestock_batch_to_marketplace,
    unpublish_livestock_batch_listing,
)
from tenants.utils_roles import is_manager
from inventory.services.farm_manager import (
    AlertItem,
    CategorizedAlerts,
    compute_alerts,
    compute_categorized_alerts,
    compute_crop_intelligence,
    compute_farm_score,
    compute_livestock_intelligence,
    compute_livestock_snapshot,
    compute_monthly_profit,
    crop_season_to_data,
    generate_farm_recommendations,
    get_farm_dashboard_snapshot,
    ledger_entry_to_data,
    livestock_batch_to_data,
    livestock_event_to_data,
)
from inventory.verticals import base
from tenants.utils import require_business
from django.urls import reverse


def _safe_farm_marketplace_dashboard_extras(business, batches, ledger_qs, today):
    try:
        return _farm_marketplace_dashboard_extras(business, batches, ledger_qs, today)
    except Exception:
        return {
            "marketplace_farm_live_count": 0,
            "marketplace_live_total_count": 0,
            "marketplace_enquiry_unread_count": 0,
            "farm_dashboard_livestock_units": 0,
            "farm_dashboard_stock_value_estimate_mwk": Decimal("0"),
            "farm_dashboard_risky_margin_batches": 0,
            "farm_dashboard_low_photo_batches": 0,
            "farm_operational_prompts": [],
        }


def _farm_marketplace_dashboard_extras(business, batches, ledger_qs, today):
    """Marketplace KPIs + short operational prompts for the farm dashboard."""
    from django.db.models import Sum

    from inventory.models_marketplace import ListingStatus, MarketplaceEnquiry, MarketplaceListing

    try:
        marketplace_farm_live_count = MarketplaceListing.objects.filter(
            business=business, vertical="farm", status=ListingStatus.LIVE
        ).count()
        marketplace_live_total_count = MarketplaceListing.objects.filter(
            business=business, status=ListingStatus.LIVE
        ).count()
        marketplace_enquiry_unread_count = MarketplaceEnquiry.objects.filter(
            business=business, is_read=False
        ).count()
    except Exception:
        marketplace_farm_live_count = 0
        marketplace_live_total_count = 0
        marketplace_enquiry_unread_count = 0

    livestock_units = sum(b.count_current or 0 for b in batches)
    est_stock_value = Decimal("0")
    risky_margin_batches = 0
    low_photo_batches = 0
    for b in batches:
        ev = getattr(b, "estimated_value_mwk", None)
        if ev:
            est_stock_value += ev
        if getattr(b, "margin_band", None) == "risky":
            risky_margin_batches += 1
        if (
            (b.count_current or 0) > 0
            and not b.primary_image
            and not b.gallery_images.exists()
        ):
            low_photo_batches += 1

    prompts = []
    for b in batches:
        if (
            getattr(b, "margin_band", None) == "risky"
            and (b.cost_basis_per_head_mwk or b.expected_sale_price_mwk)
        ):
            prompts.append(
                {
                    "severity": "warning",
                    "title": "Pricing under pressure",
                    "message": f'{b.name}: margin looks negative or very thin — review ask vs cost.',
                }
            )
        if (
            "layer" in (b.animal_subtype or "")
            and not (b.egg_production_status or "").strip()
        ):
            prompts.append(
                {
                    "severity": "info",
                    "title": "Track egg output",
                    "message": f"You marked layers for {b.name} — add egg production notes when ready.",
                }
            )
        if (
            (b.count_current or 0) > 0
            and not b.marketplace_listing_id
            and (
                getattr(b, "effective_asking_price_per_head_mwk", None)
                or b.expected_sale_price_mwk
            )
        ):
            prompts.append(
                {
                    "severity": "info",
                    "title": "Ready to publish",
                    "message": f"{b.name} has stock and an asking price — publish to marketplace from batch detail.",
                }
            )

    feed_spend_mwk = None
    try:
        feed_spend_mwk = ledger_qs.filter(
            entry_type=FarmEntryType.EXPENSE,
            category=FarmExpenseCategory.FEED,
            date__month=today.month,
            date__year=today.year,
        ).aggregate(total=Sum("amount_mwk"))["total"]
    except Exception:
        feed_spend_mwk = None

    if feed_spend_mwk and feed_spend_mwk > Decimal("0") and low_photo_batches > 0:
        prompts.append(
            {
                "severity": "info",
                "title": "Photos lift enquiries",
                "message": "Listings with photos convert better — add a primary photo on key batches.",
            }
        )

    seen = set()
    deduped = []
    for p in prompts:
        key = (p["title"], p["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)
        if len(deduped) >= 8:
            break

    return {
        "marketplace_farm_live_count": marketplace_farm_live_count,
        "marketplace_live_total_count": marketplace_live_total_count,
        "marketplace_enquiry_unread_count": marketplace_enquiry_unread_count,
        "farm_dashboard_livestock_units": livestock_units,
        "farm_dashboard_stock_value_estimate_mwk": est_stock_value,
        "farm_dashboard_risky_margin_batches": risky_margin_batches,
        "farm_dashboard_low_photo_batches": low_photo_batches,
        "farm_operational_prompts": deduped,
    }


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
    
    # === DEMO DATA: show clearly-labeled sample values when workspace is empty ===
    is_demo = (
        not ledger_entries
        and snapshot.total_livestock_count == 0
        and active_seasons_count == 0
    )
    
    if is_demo:
        import json as _json
        demo_profit_trend = [
            {"month": m, "year": 2026, "net_profit": v, "income": v + 80000, "expenses": 80000}
            for m, v in [("Nov", 180000), ("Dec", 220000), ("Jan", 310000), ("Feb", 270000), ("Mar", 350000), ("Apr", 420000)]
        ]
        demo_expense_breakdown = [
            {"category": "Fertilizer", "amount": 140000, "percentage": 39},
            {"category": "Labour", "amount": 90000, "percentage": 25},
            {"category": "Seed", "amount": 70000, "percentage": 19},
            {"category": "Transport", "amount": 35000, "percentage": 10},
            {"category": "Veterinary", "amount": 25000, "percentage": 7},
        ]
        profit_trend_json = _json.dumps(demo_profit_trend)
        expense_breakdown_json = _json.dumps(demo_expense_breakdown)
        demo_marketplace_extras = {
            "marketplace_farm_live_count": 3,
            "marketplace_live_total_count": 3,
            "marketplace_enquiry_unread_count": 2,
            "farm_dashboard_livestock_units": 45,
            "farm_dashboard_stock_value_estimate_mwk": Decimal("135000"),
            "farm_dashboard_risky_margin_batches": 0,
            "farm_dashboard_low_photo_batches": 0,
            "farm_operational_prompts": [],
        }
        demo_crops_breakdown = [
            {"name": "Maize Season A", "crop_type": "Maize", "area": 2.0, "area_unit": "ha", "weeks_since_planting": 8, "stage": "Week 8", "status": "Active", "emoji": "🌽"},
            {"name": "Groundnuts Plot B", "crop_type": "Groundnuts", "area": 1.5, "area_unit": "ha", "weeks_since_planting": 4, "stage": "Week 4", "status": "Active", "emoji": "🥜"},
            {"name": "Soya Beans C", "crop_type": "Soya", "area": 1.0, "area_unit": "ha", "weeks_since_planting": 2, "stage": "Week 2", "status": "Active", "emoji": "🫘"},
        ]
        demo_livestock_by_type = {
            "Pigs": {"count": 25, "icon": "🐖"},
            "Chickens": {"count": 20, "icon": "🐔"},
        }
    else:
        demo_marketplace_extras = _safe_farm_marketplace_dashboard_extras(business, batches, ledger_qs, today)
        demo_crops_breakdown = crops_breakdown
        demo_livestock_by_type = livestock_by_type

    # =====================================================================
    # INTELLIGENCE LAYER — farm score, categorized alerts, recommendations
    # =====================================================================
    try:
        # Compute livestock intelligence for each batch
        livestock_intelligences = []
        for batch in batches:
            batch_data = livestock_batch_to_data(batch)
            # Filter ledger entries linked to this batch
            batch_ledger = [
                e for e in ledger_entries
                if e.get("livestock_batch_id") == batch.id
            ]
            # Fallback: if no linked ledger, use enterprise_type match
            if not batch_ledger:
                animal_ent = batch.animal_type  # e.g. "pigs", "chickens"
                batch_ledger = [e for e in ledger_entries if e["enterprise_type"] == animal_ent]
            intel = compute_livestock_intelligence(
                batch=batch_data,
                events=events_data if "events_data" in dir() else [],
                ledger_entries=batch_ledger,
                batch_created_date=batch.created_at.date() if hasattr(batch.created_at, "date") else today,
                today=today,
            )
            livestock_intelligences.append(intel)

        # Compute crop intelligence for each active season
        crop_intelligences = []
        for season in active_seasons:
            season_data = crop_season_to_data(season)
            # Ledger entries linked to this season
            season_ledger = [
                e for e in ledger_entries
                if e.get("crop_season_id") == season.id
            ]
            # Fallback: match by crop_type
            if not season_ledger:
                season_ledger = [e for e in ledger_entries if e["enterprise_type"] == season.crop_type]
            ci = compute_crop_intelligence(season_data, season_ledger, today)
            crop_intelligences.append(ci)

        # Days since last expense
        last_expense = ledger_qs.filter(entry_type=FarmEntryType.EXPENSE).order_by("-date").first()
        days_since_last_expense = (today - last_expense.date).days if last_expense else None

        # Days since last livestock event
        try:
            last_event = FarmLivestockEvent.objects.filter(
                batch__business=business
            ).order_by("-date").first()
            has_recent_livestock_event = bool(last_event and (today - last_event.date).days <= 7)
        except Exception:
            has_recent_livestock_event = False

        # Risk levels list for farm score
        livestock_risk_levels = [i.mortality_risk_level for i in livestock_intelligences]
        missing_sale_price_count = sum(1 for i in livestock_intelligences if not i.has_asking_price and i.has_stock)
        missing_yield_count = sum(1 for c in crop_intelligences if not c.projected_income_mwk and c.status in ("active", "planning"))

        # Farm score
        farm_score = compute_farm_score(
            net_profit=snapshot.net_profit_mwk,
            total_income=snapshot.total_income_mwk,
            total_expenses=snapshot.total_expenses_mwk,
            livestock_risk_levels=livestock_risk_levels,
            active_crop_seasons_count=active_seasons_count,
            missing_yield_count=missing_yield_count,
            missing_sale_price_count=missing_sale_price_count,
            marketplace_listings_count=demo_marketplace_extras.get("marketplace_farm_live_count", 0),
            days_since_last_sale=days_since_last_sale,
            days_since_last_expense=days_since_last_expense,
            has_recent_livestock_event=has_recent_livestock_event,
        )

        # Categorized alerts
        categorized_alerts = compute_categorized_alerts(
            net_profit=snapshot.net_profit_mwk,
            total_income=snapshot.total_income_mwk,
            total_expenses=snapshot.total_expenses_mwk,
            livestock_intelligences=livestock_intelligences,
            crop_intelligences=crop_intelligences,
            days_since_last_sale=days_since_last_sale,
            marketplace_listings_count=demo_marketplace_extras.get("marketplace_farm_live_count", 0),
        )

        # Recommendations
        recommendations = generate_farm_recommendations(
            net_profit=snapshot.net_profit_mwk,
            livestock_intelligences=livestock_intelligences,
            crop_intelligences=crop_intelligences,
            has_marketplace_listings=demo_marketplace_extras.get("marketplace_farm_live_count", 0) > 0,
            has_poultry=any(b.animal_type == "chickens" for b in batches),
            days_since_egg_record=None,
            days_since_last_sale=days_since_last_sale,
            limit=5,
        )

    except Exception as e:
        logger.warning(f"Farm intelligence layer failed gracefully: {e}")
        livestock_intelligences = []
        crop_intelligences = []
        farm_score = None
        categorized_alerts = CategorizedAlerts(critical=[], warnings=[], opportunities=[], total_count=0)
        recommendations = []

    ctx.update({
        "active_tab": "dashboard",
        "hero_title": "Farm Manager",
        "hero_blurb": "Know what is growing, costing, earning, and needs your attention.",

        # SSOT snapshot (all computed values)
        "snapshot": snapshot,

        # Demo mode flag
        "is_demo": is_demo,

        # Filter state
        "filter_state": filter_state,
        "filter_options": filter_options,

        # Chart data (JSON for Chart.js — demo or real)
        "profit_trend_json": profit_trend_json,
        "expense_breakdown_json": expense_breakdown_json,

        # For backwards compatibility with existing template parts
        "profit_this_month": Decimal("420000") if is_demo else snapshot.net_profit_mwk,
        "income_this_month": Decimal("780000") if is_demo else snapshot.total_income_mwk,
        "expenses_this_month": Decimal("360000") if is_demo else snapshot.total_expenses_mwk,
        "sales_count_this_month": 12 if is_demo else snapshot.sales_count,
        "top_expense_categories": demo_expense_breakdown if is_demo else snapshot.expense_breakdown,

        # Livestock display data
        "livestock_batches": batches,
        "livestock_snapshots": livestock_snapshots,
        "livestock_intelligences": livestock_intelligences,
        "total_livestock_count": 45 if is_demo else snapshot.total_livestock_count,
        "total_livestock_value": Decimal("135000") if is_demo else snapshot.total_livestock_value,
        "livestock_by_type": demo_livestock_by_type,

        # Crops
        "active_seasons": active_seasons,
        "crops_breakdown": demo_crops_breakdown,
        "crop_intelligences": crop_intelligences,

        # Assets preview
        "assets_preview": assets_preview,
        "total_assets_value": total_assets_value,
        "assets_count": assets_count,

        # AI Insights
        "ai_insights": ai_insights_data,

        # Marketplace & operational prompts
        **demo_marketplace_extras,

        # Recent activity
        "recent_entries": recent_entries,

        # Alerts (legacy flat list + new categorized)
        "alerts": snapshot.alerts,
        "alerts_count": len(snapshot.alerts),
        "critical_alerts_count": snapshot.critical_alerts_count,
        "categorized_alerts": categorized_alerts,

        # Intelligence layer (new)
        "farm_score": farm_score,
        "recommendations": recommendations,
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
    
    today = timezone.now().date()
    batch_snapshots = []
    for batch in batches:
        batch_data = livestock_batch_to_data(batch)
        snapshot = compute_livestock_snapshot(batch_data, events_data)
        # Build intelligence for each batch
        batch_ledger = [
            ledger_entry_to_data(e)
            for e in FarmLedgerEntry.objects.filter(
                business=business, livestock_batch=batch
            )
        ]
        try:
            intel = compute_livestock_intelligence(
                batch=batch_data,
                events=events_data,
                ledger_entries=batch_ledger,
                batch_created_date=batch.created_at.date() if hasattr(batch.created_at, "date") else today,
                today=today,
            )
        except Exception:
            intel = None
        batch_snapshots.append({
            "batch": batch,
            "snapshot": snapshot,
            "intel": intel,
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
            animal_type = request.POST.get("animal_type", FarmAnimalType.PIGS)
            st_raw = request.POST.get("animal_subtype", FarmLivestockSubType.UNSPECIFIED)
            allowed = {a[0] for a in subtype_choices_for_animal_type(animal_type)}
            if st_raw not in allowed:
                st_raw = FarmLivestockSubType.UNSPECIFIED
            batch = FarmLivestockBatch.objects.create(
                business=business,
                animal_type=animal_type,
                animal_subtype=st_raw,
                name=request.POST.get("name", ""),
                count_current=int(request.POST.get("initial_count", 0)),
                valuation_enabled=request.POST.get("valuation_enabled") == "on",
                avg_weight_kg=_farm_parse_decimal(request.POST.get("avg_weight_kg")),
                price_per_kg_mwk=_farm_parse_decimal(request.POST.get("price_per_kg")),
                price_per_animal_mwk=_farm_parse_decimal(request.POST.get("price_per_animal")),
                cost_basis_per_head_mwk=_farm_parse_decimal(request.POST.get("cost_basis_per_head_mwk")),
                expected_sale_price_mwk=_farm_parse_decimal(request.POST.get("expected_sale_price_mwk")),
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
    
    import json
    from django.core.serializers.json import DjangoJSONEncoder

    ctx.update(
        {
            "active_tab": "livestock",
            "animal_types": FarmAnimalType.choices,
            "subtype_default": FarmAnimalType.PIGS,
            "subtype_labels_json": json.dumps(
                {c.value: c.label for c in FarmLivestockSubType},
                cls=DjangoJSONEncoder,
            ),
            "subtype_map_json": json.dumps(
                {k: list(v) for k, v in FARM_SUBTYPES_BY_ANIMAL.items()},
                cls=DjangoJSONEncoder,
            ),
        }
    )

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
                unit_price_mwk=_farm_parse_decimal(request.POST.get("unit_price")),
                weight_kg=_farm_parse_decimal(request.POST.get("weight_kg")),
                quantity=_farm_parse_decimal(request.POST.get("quantity")),
                quantity_unit=request.POST.get("quantity_unit", ""),
                cost_impact_mwk=_farm_parse_decimal(request.POST.get("cost_impact_mwk")),
                revenue_impact_mwk=_farm_parse_decimal(request.POST.get("revenue_impact_mwk")),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )

            # Update batch count only for count-changing events
            if event_type in LIVESTOCK_COUNT_ADDING_EVENTS:
                batch.count_current += count
                batch.save(update_fields=["count_current"])
            elif event_type in LIVESTOCK_COUNT_REMOVING_EVENTS:
                batch.count_current = max(0, batch.count_current - count)
                batch.save(update_fields=["count_current"])
            # Non-count events (vaccination, feeding, etc.) don't change count
            
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
    
    # Group event types for the UI
    count_events = [(v, l) for v, l in FarmLivestockEventType.choices
                    if v in LIVESTOCK_COUNT_ADDING_EVENTS | LIVESTOCK_COUNT_REMOVING_EVENTS]
    health_events = [(v, l) for v, l in FarmLivestockEventType.choices
                     if v in LIVESTOCK_NON_COUNT_EVENTS]

    ctx.update({
        "active_tab": "livestock",
        "batches": batches,
        "event_types": FarmLivestockEventType.choices,
        "count_event_types": count_events,
        "health_event_types": health_events,
        "entry_types": LIVESTOCK_ENTRY_TYPES,
        "recommended_actions": recommended_actions,
        "preselect_batch_id": preselect_batch_id,
        "preselect_type": preselect_type,
        "season_type": "livestock",
    })
    
    return render(request, "verticals/farm/livestock_add_event.html", ctx)


def _farm_parse_decimal(raw: str | None):
    if not raw or not str(raw).strip():
        return None
    try:
        return Decimal(str(raw).strip().replace(",", ""))
    except Exception:
        return None


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def livestock_batch_detail(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Batch detail: metadata, margin, photos, publish to marketplace."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    batch = get_object_or_404(FarmLivestockBatch, pk=batch_id, business=business)
    from django.core.serializers.json import DjangoJSONEncoder
    import json

    if request.method == "POST":
        action = request.POST.get("_action", "").strip()
        if action == "publish_listing":
            if not is_manager(request.user, business):
                messages.error(request, "Only managers can publish marketplace listings.")
                return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
            try:
                sync_livestock_batch_to_marketplace(batch, request.user, business)
                messages.success(request, "Livestock listing published to the marketplace.")
            except Exception as e:
                messages.error(request, f"Could not publish: {e}")
            return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
        if action == "unpublish_listing":
            if not is_manager(request.user, business):
                messages.error(request, "Only managers can change marketplace listings.")
                return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
            try:
                unpublish_livestock_batch_listing(batch)
                messages.info(request, "Marketplace listing taken offline (still linked for re-publish).")
            except Exception as e:
                messages.error(request, f"Could not update listing: {e}")
            return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
        if action == "add_gallery":
            if not is_manager(request.user, business):
                messages.error(request, "Only managers can upload photos.")
                return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
            f = request.FILES.get("gallery_image")
            if f:
                nxt = batch.gallery_images.count()
                FarmBatchImage.objects.create(
                    batch=batch,
                    image=f,
                    sort_order=nxt,
                    caption=request.POST.get("caption", "")[:200],
                )
                messages.success(request, "Photo added to gallery.")
            return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)
        # Save batch details (default POST)
        st_raw = request.POST.get("animal_subtype", FarmLivestockSubType.UNSPECIFIED)
        allowed = {a[0] for a in subtype_choices_for_animal_type(request.POST.get("animal_type", batch.animal_type))}
        if st_raw not in allowed:
            st_raw = FarmLivestockSubType.UNSPECIFIED
        batch.animal_type = request.POST.get("animal_type", batch.animal_type)
        batch.animal_subtype = st_raw
        batch.name = request.POST.get("name", batch.name).strip() or batch.name
        batch.breed_text = request.POST.get("breed_text", "")[:120]
        batch.gender = request.POST.get("gender", batch.gender)
        batch.notes = request.POST.get("notes", "")
        am = request.POST.get("age_months", "").strip()
        batch.age_months = int(am) if am.isdigit() else None
        batch.health_status = request.POST.get("health_status", batch.health_status)
        batch.vaccination_status = request.POST.get("vaccination_status", batch.vaccination_status)
        batch.feed_growth_stage = request.POST.get("feed_growth_stage", "")[:80]
        batch.egg_production_status = request.POST.get("egg_production_status", "")[:80]
        batch.dairy_output_note = request.POST.get("dairy_output_note", "")[:200]
        batch.sale_availability = request.POST.get("sale_availability", batch.sale_availability)
        batch.is_featured_listing = request.POST.get("is_featured_listing") == "on"
        batch.cost_basis_per_head_mwk = _farm_parse_decimal(request.POST.get("cost_basis_per_head_mwk"))
        batch.expected_sale_price_mwk = _farm_parse_decimal(request.POST.get("expected_sale_price_mwk"))
        loc_id = request.POST.get("location_id", "").strip()
        if loc_id.isdigit():
            loc = Location.objects.filter(pk=int(loc_id), business=business).first()
            batch.location = loc
        elif loc_id == "":
            batch.location = None
        v_on = request.POST.get("valuation_enabled") == "on"
        batch.valuation_enabled = v_on
        batch.avg_weight_kg = _farm_parse_decimal(request.POST.get("avg_weight_kg"))
        batch.price_per_kg_mwk = _farm_parse_decimal(request.POST.get("price_per_kg"))
        batch.price_per_animal_mwk = _farm_parse_decimal(request.POST.get("price_per_animal"))
        if "primary_image" in request.FILES and request.FILES.get("primary_image"):
            batch.primary_image = request.FILES["primary_image"]
        try:
            batch.save()
            messages.success(request, "Batch details saved.")
        except Exception as e:
            messages.error(request, f"Save failed: {e}")
        return redirect("verticals:farm_livestock_detail", batch_id=batch.pk)

    from inventory.models_marketplace import ListingStatus

    listing = getattr(batch, "marketplace_listing", None)
    today = timezone.now().date()
    all_events = FarmLivestockEvent.objects.filter(batch__business=business)
    events_data = [livestock_event_to_data(e) for e in all_events]
    batch_data = livestock_batch_to_data(batch)
    snapshot = compute_livestock_snapshot(batch_data, events_data, today)

    # ── Intelligence layer ──────────────────────────────────────────
    batch_ledger_entries = list(
        FarmLedgerEntry.objects.filter(
            business=business, livestock_batch=batch
        ).values(
            "id", "entry_type", "category", "amount_mwk", "date",
            "enterprise_type", "description", "livestock_batch_id",
        )
    )
    # Convert queryset to list of dicts that match LedgerEntryData
    def _to_ledger_data(row):
        return {
            "id": row["id"],
            "entry_type": row["entry_type"],
            "category": row["category"],
            "amount_mwk": row["amount_mwk"] or Decimal("0"),
            "date": row["date"],
            "enterprise_type": row["enterprise_type"] or "",
            "description": row["description"] or "",
            "livestock_batch_id": row["livestock_batch_id"],
            "crop_season_id": None,
        }
    batch_ledger_data = [_to_ledger_data(r) for r in batch_ledger_entries]

    intelligence = None
    try:
        intelligence = compute_livestock_intelligence(
            batch=batch_data,
            events=events_data,
            ledger_entries=batch_ledger_data,
            batch_created_date=batch.created_at.date() if hasattr(batch.created_at, "date") else today,
            today=today,
        )
    except Exception as _intel_err:
        import logging
        logging.getLogger(__name__).warning("livestock intelligence failed: %s", _intel_err)

    # ── Simulation (GET params for default values) ──────────────────
    sim_sale_price = request.GET.get("sim_sale_price") or (
        str(batch.expected_sale_price_mwk) if batch.expected_sale_price_mwk else ""
    )
    sim_animals_to_sell = request.GET.get("sim_animals_to_sell") or str(
        batch.count_current or 0
    )
    sim_final_weight = request.GET.get("sim_final_weight") or (
        str(batch.avg_weight_kg) if batch.avg_weight_kg else ""
    )
    sim_extra_feed_cost = request.GET.get("sim_extra_feed_cost") or "0"
    sim_expected_mortality = request.GET.get("sim_expected_mortality") or "0"

    # Run simple simulation if params provided
    simulation_result = None
    try:
        sp = Decimal(sim_sale_price) if sim_sale_price else None
        animals = int(sim_animals_to_sell) if sim_animals_to_sell else 0
        extra_feed = Decimal(sim_extra_feed_cost) if sim_extra_feed_cost else Decimal("0")
        mortality_sim = Decimal(sim_expected_mortality) if sim_expected_mortality else Decimal("0")

        if sp and animals > 0 and intelligence:
            sold_after_mortality = max(0, int(animals * (1 - mortality_sim / 100)))
            extra_cost = intelligence.total_cost_mwk + extra_feed
            proj_revenue = sp * sold_after_mortality
            proj_profit = proj_revenue - extra_cost
            proj_roi = (proj_profit / extra_cost * 100) if extra_cost > 0 else None
            break_even_sim = (extra_cost / sold_after_mortality) if sold_after_mortality > 0 else None

            # Best/expected/worst cases
            simulation_result = {
                "sale_price": sp,
                "animals_sold": sold_after_mortality,
                "total_cost": extra_cost,
                "projected_revenue": proj_revenue,
                "projected_profit": proj_profit,
                "roi_pct": proj_roi,
                "break_even_price": break_even_sim,
                "best_case_profit": proj_profit + (sp * sold_after_mortality * Decimal("0.1")),
                "worst_case_profit": proj_profit - (sp * sold_after_mortality * Decimal("0.15")),
            }
    except (ValueError, TypeError, Exception):
        pass

    # ── Housing planner context ─────────────────────────────────────
    housing_space_estimate = None
    if batch.count_current and batch.animal_type:
        space_map = {
            "pigs": Decimal("1.5"),      # m² per pig
            "cattle": Decimal("6"),       # m² per cattle
            "goats": Decimal("2"),        # m² per goat
            "chickens": Decimal("0.1"),   # m² per chicken
            "ducks": Decimal("0.15"),
            "rabbits": Decimal("0.3"),
            "sheep": Decimal("2"),
        }
        m2_per = space_map.get(batch.animal_type)
        if m2_per:
            housing_space_estimate = m2_per * batch.count_current

    ctx.update(
        {
            "active_tab": "livestock",
            "batch": batch,
            "snapshot": snapshot,
            "intelligence": intelligence,
            "simulation_result": simulation_result,
            "sim_sale_price": sim_sale_price,
            "sim_animals_to_sell": sim_animals_to_sell,
            "sim_final_weight": sim_final_weight,
            "sim_extra_feed_cost": sim_extra_feed_cost,
            "sim_expected_mortality": sim_expected_mortality,
            "housing_space_estimate": housing_space_estimate,
            "subtype_choices": subtype_choices_for_animal_type(batch.animal_type),
            "animal_types": FarmAnimalType.choices,
            "health_statuses": FarmHealthStatus.choices,
            "vaccination_statuses": FarmVaccinationStatus.choices,
            "genders": FarmAnimalGender.choices,
            "sale_availability_choices": FarmSaleAvailability.choices,
            "locations": Location.objects.filter(business=business),
            "listing": listing,
            "listing_is_live": bool(listing and listing.status == ListingStatus.LIVE),
            "is_manager": is_manager(request.user, business),
            "margin_band": batch.margin_band,
            "margin_pct": batch.margin_pct_vs_cost,
            "subtype_labels_json": json.dumps(
                {c.value: c.label for c in FarmLivestockSubType},
                cls=DjangoJSONEncoder,
            ),
            "subtype_map_json": json.dumps(
                {k: list(v) for k, v in FARM_SUBTYPES_BY_ANIMAL.items()}, cls=DjangoJSONEncoder
            ),
        }
    )
    return render(request, "verticals/farm/livestock_batch_detail.html", ctx)


# ==============================================================================
# LIVESTOCK SIMULATION
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_simulate(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Profit simulation for a single livestock batch."""
    from inventory.services.farm_manager import compute_livestock_simulation

    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    batch = get_object_or_404(FarmLivestockBatch, pk=batch_id, business=business)
    batch_data = livestock_batch_to_data(batch)

    # Total costs from ledger entries linked to this batch
    batch_cost = FarmLedgerEntry.objects.filter(
        business=business,
        livestock_batch=batch,
        entry_type=FarmEntryType.EXPENSE,
    ).aggregate(total=Sum("amount_mwk"))["total"] or Decimal("0")

    # Simulation inputs from GET/POST
    try:
        sim_price = Decimal(request.GET.get("sale_price", "") or "") if request.GET.get("sale_price") else batch.expected_sale_price_mwk or batch.price_per_animal_mwk
    except Exception:
        sim_price = batch.expected_sale_price_mwk or batch.price_per_animal_mwk

    try:
        sim_count = int(request.GET.get("count", "") or "") if request.GET.get("count") else batch.count_current
    except Exception:
        sim_count = batch.count_current

    simulation = compute_livestock_simulation(
        batch=batch_data,
        current_costs=batch_cost,
        expected_sale_price=sim_price,
        expected_count_to_sell=sim_count,
    )

    ctx.update({
        "active_tab": "livestock",
        "batch": batch,
        "simulation": simulation,
        "batch_cost": batch_cost,
        "sim_price": sim_price or Decimal("0"),
        "sim_count": sim_count or 0,
    })
    return render(request, "verticals/farm/livestock_simulate.html", ctx)


# ==============================================================================
# HOUSING PLANNER
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_housing_planner(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Simple housing planner for a livestock batch (placeholder for 3D integration)."""
    ctx = base.base_context(request)
    business = ctx.get("business")

    batch = get_object_or_404(FarmLivestockBatch, pk=batch_id, business=business)

    # Estimate floor space: 0.5 sqm per pig/goat, 0.1 sqm per chicken, 2 sqm per cow
    SPACE_PER_ANIMAL = {
        "pigs": Decimal("0.5"),
        "cattle": Decimal("2.0"),
        "goats": Decimal("0.5"),
        "chickens": Decimal("0.1"),
        "ducks": Decimal("0.1"),
        "rabbits": Decimal("0.2"),
        "sheep": Decimal("0.6"),
        "fish": Decimal("0.3"),
    }
    space_per = SPACE_PER_ANIMAL.get(batch.animal_type, Decimal("0.5"))
    estimated_sqm = space_per * batch.count_current if batch.count_current else Decimal("0")

    ctx.update({
        "active_tab": "livestock",
        "batch": batch,
        "estimated_sqm": estimated_sqm,
        "space_per_animal": space_per,
        "checklist": [
            ("Adequate floor space", f"{estimated_sqm:.1f} m² recommended for {batch.count_current} animals"),
            ("Ventilation", "Ensure cross-ventilation to reduce disease risk"),
            ("Clean water access", "Water points within easy reach of all animals"),
            ("Feed storage", "Secure, dry feed storage adjacent to pen"),
            ("Drainage", "Floor slope of 2–5% away from feeding area"),
            ("Biosecurity barrier", "Footbath at pen entrance; restrict visitor access"),
            ("Separation pens", "At least one isolation pen for sick animals"),
        ],
    })
    return render(request, "verticals/farm/livestock_housing_plan.html", ctx)


# ==============================================================================
# EGG / POULTRY TRACKING
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def egg_tracking_list(request: HttpRequest) -> HttpResponse:
    """List poultry batches and egg production summaries."""
    from inventory.models_farm import PoultryBatch
    from inventory.services.farm_manager import compute_egg_summary

    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    try:
        poultry_batches = PoultryBatch.objects.filter(business=business, is_active=True).order_by("-start_date")
    except Exception:
        poultry_batches = []

    batch_summaries = []
    for pb in poultry_batches:
        try:
            daily_records = list(
                pb.daily_records.order_by("-date").values(
                    "date", "eggs_collected", "deaths", "feed_kg"
                )[:90]
            )
            summary = compute_egg_summary(
                batch_id=pb.id,
                batch_name=pb.name,
                initial_birds=pb.initial_birds,
                current_birds=pb.current_birds,
                total_eggs=pb.total_eggs,
                total_feed_kg=pb.total_feed_kg,
                total_cost=pb.total_cost,
                total_sales=pb.total_sales,
                daily_records=daily_records,
                today=today,
            )
        except Exception:
            summary = None
        batch_summaries.append({"batch": pb, "summary": summary})

    ctx.update({
        "active_tab": "livestock",
        "batch_summaries": batch_summaries,
        "has_poultry": len(batch_summaries) > 0,
    })
    return render(request, "verticals/farm/poultry_list.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def egg_tracking_record(request: HttpRequest) -> HttpResponse:
    """Record a daily egg/poultry entry."""
    from inventory.models_farm import PoultryBatch, PoultryDailyRecord

    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    batches = PoultryBatch.objects.filter(business=business, is_active=True)
    preselect_id = request.GET.get("batch_id") or request.POST.get("batch_id")

    if request.method == "POST":
        try:
            batch_id = int(request.POST.get("batch_id", 0))
            pb = get_object_or_404(PoultryBatch, pk=batch_id, business=business)
            record_date = request.POST.get("date") or today

            PoultryDailyRecord.objects.update_or_create(
                batch=pb,
                date=record_date,
                defaults={
                    "birds_alive": int(request.POST.get("birds_alive", pb.current_birds or 0)),
                    "deaths": int(request.POST.get("deaths", 0)),
                    "feed_kg": Decimal(request.POST.get("feed_kg", "0") or "0"),
                    "eggs_collected": int(request.POST.get("eggs_collected", 0)),
                    "medication": request.POST.get("medication", ""),
                    "remarks": request.POST.get("remarks", ""),
                    "created_by": request.user,
                },
            )
            messages.success(request, f"Egg record saved for {pb.name}.")
            return redirect("verticals:farm_egg_tracking")
        except Exception as e:
            messages.error(request, f"Error saving egg record: {e}")

    ctx.update({
        "active_tab": "livestock",
        "batches": batches,
        "preselect_id": int(preselect_id) if preselect_id else None,
        "today": today,
    })
    return render(request, "verticals/farm/poultry_daily_record.html", ctx)


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
    
    # ── Crop intelligence layer ──────────────────────────────────────
    actual_profit = totals["total_income"] - totals["total_expenses"]
    crop_intelligence = None
    try:
        season_data = crop_season_to_data(season)
        ledger_data_list = [ledger_entry_to_data(e) for e in ledger_entries]
        crop_intelligence = compute_crop_intelligence(season_data, ledger_data_list, today)
    except Exception as _ci_err:
        import logging
        logging.getLogger(__name__).warning("crop intelligence failed: %s", _ci_err)

    # ── Poultry/Egg tracking context (if applicable) ─────────────────
    egg_summary = None
    if hasattr(season, "crop_type") and season.crop_type in ("chickens", "poultry"):
        pass  # Would come from PoultryDailyRecord; skipped if not poultry season

    ctx.update({
        "active_tab": "crops",
        "season": season,
        "ledger_entries": ledger_entries,
        "actual_income": totals["total_income"],
        "actual_expenses": totals["total_expenses"],
        "actual_profit": actual_profit,

        # Crop intelligence
        "crop_intelligence": crop_intelligence,

        # Smart Entry context
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


# ==============================================================================
# LIVESTOCK SIMULATION
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def livestock_simulate(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Simulate profit scenarios for a livestock batch."""
    from inventory.services.farm_intelligence import simulate_livestock_batch
    ctx = base.base_context(request)
    business = ctx.get("business")
    batch = get_object_or_404(FarmLivestockBatch, pk=batch_id, business=business)

    simulation = None
    form_data = {}

    if request.method == "POST" or request.GET.get("run"):
        try:
            sale_price = _farm_parse_decimal(request.POST.get("sale_price") or request.GET.get("sale_price"))
            if sale_price is None:
                sale_price = batch.expected_sale_price_mwk or Decimal("0")

            # Get total cost from ledger
            all_events = FarmLivestockEvent.objects.filter(batch=batch)
            events_data = [livestock_event_to_data(e) for e in all_events]
            batch_data = livestock_batch_to_data(batch)
            snapshot = compute_livestock_snapshot(batch_data, events_data)

            ledger_entries = FarmLedgerEntry.objects.filter(
                business=business, livestock_batch=batch
            )
            total_cost = ledger_entries.filter(
                entry_type=FarmEntryType.EXPENSE
            ).aggregate(
                total=Coalesce(Sum("amount_mwk"), Decimal("0"))
            )["total"]

            form_data = {
                "sale_price": sale_price,
                "total_cost": total_cost,
                "count": batch.count_current,
            }

            if sale_price > 0:
                simulation = simulate_livestock_batch(
                    count_current=batch.count_current,
                    expected_sale_price_mwk=sale_price,
                    total_cost_mwk=total_cost,
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Simulation failed: {e}")

    ctx.update({
        "active_tab": "livestock",
        "batch": batch,
        "simulation": simulation,
        "form_data": form_data,
        "default_price": batch.expected_sale_price_mwk,
    })
    return render(request, "verticals/farm/livestock_simulate.html", ctx)


# ==============================================================================
# LIVESTOCK HOUSING PLANNER
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_housing_planner(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Housing planner for a livestock batch. Placeholder for future 3D integration."""
    from inventory.services.farm_intelligence import compute_housing_plan
    ctx = base.base_context(request)
    business = ctx.get("business")
    batch = get_object_or_404(FarmLivestockBatch, pk=batch_id, business=business)

    plan = None
    try:
        plan = compute_housing_plan(
            animal_type=batch.animal_type,
            animal_count=max(1, batch.count_current),
            housing_type=request.GET.get("housing_type", "standard"),
        )
    except Exception:
        pass

    ctx.update({
        "active_tab": "livestock",
        "batch": batch,
        "plan": plan,
    })
    return render(request, "verticals/farm/livestock_housing_planner.html", ctx)


# ==============================================================================
# EGG / POULTRY TRACKING
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def egg_tracking_list(request: HttpRequest) -> HttpResponse:
    """Egg production tracking dashboard — lists layer batches and recent records."""
    from inventory.models_farm import PoultryBatch, PoultryDailyRecord
    from inventory.services.farm_intelligence import compute_egg_summary
    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    try:
        layer_batches = PoultryBatch.objects.filter(
            business=business, is_active=True
        ).order_by("-start_date")

        # Get recent daily records (last 30 days)
        from datetime import timedelta
        month_start = today - timedelta(days=30)
        recent_records = PoultryDailyRecord.objects.filter(
            batch__business=business,
            date__gte=month_start,
        ).order_by("-date").select_related("batch")[:60]

        # Convert to list of dicts for compute_egg_summary
        records_data = [
            {
                "date": r.date,
                "eggs_collected": r.eggs_collected,
                "spoiled_eggs": 0,  # field may not exist on legacy records
                "feed_kg": r.feed_kg,
                "batch_id": r.batch_id,
            }
            for r in recent_records
        ]

        total_birds = sum(b.current_birds for b in layer_batches)
        egg_summary = compute_egg_summary(
            daily_records=records_data,
            today=today,
            layer_batches_count=layer_batches.count(),
            total_layer_birds=total_birds,
        )

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Egg tracking load failed: {e}")
        layer_batches = []
        recent_records = []
        egg_summary = None

    ctx.update({
        "active_tab": "livestock",
        "page_title": "Egg Production Tracking",
        "layer_batches": layer_batches,
        "recent_records": recent_records,
        "egg_summary": egg_summary,
        "today": today,
    })
    return render(request, "verticals/farm/egg_tracking.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def egg_tracking_record(request: HttpRequest) -> HttpResponse:
    """Record daily egg collection for a poultry batch."""
    from inventory.models_farm import PoultryBatch, PoultryDailyRecord
    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    try:
        layer_batches = PoultryBatch.objects.filter(business=business, is_active=True)
    except Exception:
        layer_batches = []

    if request.method == "POST":
        try:
            batch_id = request.POST.get("batch_id")
            batch = get_object_or_404(PoultryBatch, pk=batch_id, business=business)
            record_date = request.POST.get("date") or today
            eggs = int(request.POST.get("eggs_collected", 0))
            deaths = int(request.POST.get("deaths", 0))
            feed_kg = _farm_parse_decimal(request.POST.get("feed_kg")) or Decimal("0")
            medication = request.POST.get("medication", "")
            remarks = request.POST.get("remarks", "")

            # Update or create daily record
            record, created = PoultryDailyRecord.objects.update_or_create(
                batch=batch,
                date=record_date,
                defaults={
                    "birds_alive": max(0, batch.current_birds - deaths),
                    "deaths": deaths,
                    "feed_kg": feed_kg,
                    "eggs_collected": eggs,
                    "medication": medication,
                    "remarks": remarks,
                    "created_by": request.user,
                }
            )
            messages.success(
                request,
                f"{'Recorded' if created else 'Updated'} egg collection: {eggs} eggs for {batch.name}."
            )
            return redirect("verticals:farm_egg_tracking")
        except Exception as e:
            messages.error(request, f"Error recording: {e}")

    ctx.update({
        "active_tab": "livestock",
        "page_title": "Record Egg Collection",
        "layer_batches": layer_batches,
        "today": today,
        "preselect_batch": request.GET.get("batch_id"),
    })
    return render(request, "verticals/farm/egg_tracking_record.html", ctx)


# ==============================================================================
# FARM BUSINESS HEALTH (farm-specific)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def farm_business_health_view(request: HttpRequest) -> HttpResponse:
    """Farm-specific business health check with score, badges, and recommendations."""
    from inventory.services.farm_intelligence import compute_farm_business_health
    ctx = base.base_context(request)
    business = ctx.get("business")
    today = timezone.now().date()

    try:
        ledger_qs = FarmLedgerEntry.objects.filter(business=business)
        ledger_entries = [ledger_entry_to_data(e) for e in ledger_qs]
        batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
        active_seasons = FarmCropSeason.objects.filter(
            business=business,
            status__in=[FarmSeasonStatus.PLANNING, FarmSeasonStatus.ACTIVE],
        )

        # Compute financials
        from django.db.models import Sum as DbSum
        totals = ledger_qs.aggregate(
            income=Coalesce(
                DbSum("amount_mwk", filter=~models.Q(entry_type=FarmEntryType.EXPENSE)),
                Decimal("0"),
            ),
            expenses=Coalesce(
                DbSum("amount_mwk", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
                Decimal("0"),
            ),
        )
        total_income = totals["income"]
        total_expenses = totals["expenses"]
        net_profit = total_income - total_expenses

        # Livestock mortality
        all_events = FarmLivestockEvent.objects.filter(batch__business=business)
        events_data = [livestock_event_to_data(e) for e in all_events]
        livestock_snapshots = []
        for batch in batches:
            batch_data = livestock_batch_to_data(batch)
            snapshot = compute_livestock_snapshot(batch_data, events_data, today)
            livestock_snapshots.append(snapshot)

        # Overall mortality
        total_in = sum(s.births_total + s.purchases_total for s in livestock_snapshots)
        total_deaths = sum(s.deaths_total for s in livestock_snapshots)
        mortality_rate = (
            Decimal(total_deaths) / Decimal(total_in) * 100
            if total_in > 0 else None
        )

        crops_with_yield = sum(
            1 for s in active_seasons if s.projected_yield is not None
        )

        from inventory.models_marketplace import ListingStatus, MarketplaceListing
        mp_count = MarketplaceListing.objects.filter(
            business=business, vertical="farm", status=ListingStatus.LIVE
        ).count()

        last_entry = ledger_qs.order_by("-date").first()
        days_since = (today - last_entry.date).days if last_entry else None

        from inventory.models_farm import FarmAsset
        assets_val = FarmAsset.objects.filter(
            business=business, is_active=True
        ).aggregate(total=Coalesce(DbSum("value_mwk"), Decimal("0")))["total"]

        health = compute_farm_business_health(
            net_profit_mwk=net_profit,
            total_income_mwk=total_income,
            total_expenses_mwk=total_expenses,
            expected_income_mwk=None,
            livestock_value_mwk=None,
            assets_value_mwk=assets_val,
            mortality_rate_pct=mortality_rate,
            marketplace_live_count=mp_count,
            active_batches_count=batches.count(),
            active_seasons_count=active_seasons.count(),
            ledger_entries_count=ledger_qs.count(),
            days_since_last_activity=days_since,
            crops_with_projected_yield=crops_with_yield,
        )

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Farm business health failed: {e}")
        health = None
        net_profit = Decimal("0")
        total_income = Decimal("0")
        total_expenses = Decimal("0")

    ctx.update({
        "active_tab": "dashboard",
        "page_title": "Farm Business Health",
        "health": health,
        "net_profit": net_profit,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "all_farm_badges": [
            "Books Balanced", "Profit Strong", "Livestock Stable", "Crops Healthy",
            "Feed Controlled", "Harvest Ready", "Marketplace Ready", "Records Clean",
        ],
    })
    return render(request, "verticals/farm/business_health.html", ctx)


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

