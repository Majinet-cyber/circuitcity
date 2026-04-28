from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_attendance import TimeLog
from inventory.models_verticals import GymMember, GymPayment, GymWalletEntry
from tenants.models import Membership
from tenants.utils import require_business

from . import base

# Note: fast_sell() removed - gym is membership-based (members + payments),
# not product-based (inventory + sales). Gym does NOT support Fast Sell.


def _membership_stats(business):
    if not business:
        return {"managers": 0, "agents": 0, "recent": []}

    qs = Membership.objects.filter(business=business).order_by("-created_at")
    return {
        "managers": qs.filter(role="MANAGER", status="ACTIVE").count(),
        "agents": qs.filter(role="AGENT", status="ACTIVE").count(),
        "recent": list(qs[:5]),
    }


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def dashboard(request):
    ctx = base.base_context(request)
    business = ctx.get("business")

    # Staff membership stats
    stats = _membership_stats(business)

    # Get all gym members
    all_members = GymMember.objects.filter(business=business, is_active=True, is_archived=False)
    total_members = all_members.count()

    # Calculate membership status based on GymPayment coverage
    # A member is ACTIVE if they have at least one payment whose period covers today
    today = timezone.localdate()

    active_members = (
        all_members.filter(
            payments__start_date__lte=today,
            payments__end_date__gte=today,
            payments__is_active=True,
        )
        .distinct()
        .count()
    )

    # In arrears = total members - active members
    in_arrears = total_members - active_members

    members_active_count = active_members  # Alias for template compatibility
    members_in_arrears = in_arrears

    # ============================================================================
    # DATE RANGE FILTER: Parse querystring (today/last7/mtd/month/all_time)
    # ============================================================================
    range_param = request.GET.get("range", "this_month").lower()
    now = timezone.now()
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    # Determine date range based on filter
    if range_param == "today":
        start_date = today
        end_date = today
        range_label = "Today"
    elif range_param == "last7":
        start_date = today - timedelta(days=6)  # Last 7 days including today
        end_date = today
        range_label = "Last 7 Days"
    elif range_param == "last_month":
        # Last calendar month
        first_day_this_month = today.replace(day=1)
        end_date = first_day_this_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
        range_label = start_date.strftime("%B %Y")
    elif range_param == "month":
        # Specific month picker: ?range=month&month=2026-01
        month_str = request.GET.get("month", "")
        if month_str:
            try:
                # Parse YYYY-MM format
                year, month = map(int, month_str.split("-"))
                start_date = today.replace(year=year, month=month, day=1)
                # Get last day of month
                if month == 12:
                    end_date = start_date.replace(year=year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    end_date = start_date.replace(month=month + 1, day=1) - timedelta(days=1)
                range_label = start_date.strftime("%B %Y")
            except (ValueError, TypeError):
                # Invalid month format, fall back to this month
                start_date = today.replace(day=1)
                end_date = today
                range_label = "This Month"
                range_param = "this_month"
        else:
            # No month specified, fall back to this month
            start_date = today.replace(day=1)
            end_date = today
            range_label = "This Month"
            range_param = "this_month"
    elif range_param == "all_time":
        # All time: no date constraints
        start_date = None
        end_date = None
        range_label = "All Time"
    else:  # this_month / mtd (default)
        range_param = "this_month"
        start_date = today.replace(day=1)
        end_date = today
        range_label = "This Month"

    # Date ranges for metrics (datetime-aware for paid_at filtering)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

    # Calculate datetime boundaries for selected range
    if start_date is not None and end_date is not None:
        range_start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        range_end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
    else:
        # All time: use None to indicate no date filtering
        range_start_dt = None
        range_end_dt = None

    # ============================================================================
    # FINANCIAL KPIs: Revenue, Costs, Profit, MRR
    # Use consistent date filtering and Coalesce for safe aggregation
    # ============================================================================

    # Use unified metrics service for selected date range
    from inventory.services.gym_metrics import get_gym_dashboard_metrics

    range_metrics = get_gym_dashboard_metrics(business, start_date, end_date)
    revenue = range_metrics["revenue"]
    payment_count = range_metrics["payments_count"]
    payment_mix = range_metrics.get("payment_mix", [])
    
    # Store selected month for template (if month picker was used)
    selected_month = request.GET.get("month", "") if range_param == "month" else ""

    # Also get month metrics for MRR
    # MRR (Monthly Recurring Revenue) = total revenue THIS MONTH (month-to-date)
    # This is the standard SaaS metric: revenue in the current calendar month
    from inventory.services.gym_metrics import get_this_month_metrics

    month_metrics = get_this_month_metrics(business)
    mrr = month_metrics["revenue"]  # Total revenue this month (MTD)

    # ============================================================================
    # COSTS: Use admin wallet costs (same source as /wallet/admin/costs/)
    # This fixes the bug where costs added in admin wallet didn't show on dashboard
    # ============================================================================
    from inventory.utils_gym import get_business_costs_for_period

    costs_today = get_business_costs_for_period(business, today, today)
    costs_yesterday = get_business_costs_for_period(business, yesterday, yesterday)
    costs_this_month = get_business_costs_for_period(business, month_start.date(), today)
    
    # CRITICAL FIX: Calculate costs for the selected filter range (not just MTD)
    # For all_time, sum all costs (no date filter)
    if start_date is not None and end_date is not None:
        costs_selected_range = get_business_costs_for_period(business, start_date, end_date)
    else:
        # All time: sum all costs without date filtering
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        admin_costs_qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        )
        costs_agg = admin_costs_qs.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        costs_selected_range = abs(costs_agg.get("total") or Decimal("0.00"))

    # ============================================================================
    # REVENUE: Calculate from GymPayment for today, yesterday, this month
    # CRITICAL FIX: Calculate directly from membership_amount + trainer_fee
    # This ensures revenue is ALWAYS correct even if amount field has legacy 0/NULL values
    # ============================================================================
    from django.db.models import ExpressionWrapper, F
    
    revenue_today = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=today_start,
        paid_at__lte=today_end,
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    Coalesce(F("membership_amount"), Value(Decimal("0.00"))) +
                    Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"]

    revenue_yesterday = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=yesterday_start,
        paid_at__lte=yesterday_end,
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    Coalesce(F("membership_amount"), Value(Decimal("0.00"))) +
                    Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"]

    # Use revenue from unified metrics service
    revenue_this_month = month_metrics["revenue"]

    # ============================================================================
    # PROFIT: Calculate profit = revenue - costs for each period
    # ============================================================================
    profit_today = revenue_today - costs_today
    profit_yesterday = revenue_yesterday - costs_yesterday
    profit_this_month = revenue_this_month - costs_this_month
    
    # CRITICAL FIX: Calculate profit for the selected filter range
    profit_selected_range = revenue - costs_selected_range

    # Context variables: Use selected filter range values (not hardcoded MTD)
    # This ensures the "Financial Performance" section reflects the actual filter
    costs = costs_selected_range  # FIX: Was costs_this_month (ignored filter!)
    # revenue already set from range_metrics above (line 114)
    profit = profit_selected_range  # FIX: Was profit_this_month (ignored filter!)

    # SANITY CHECK (development only): If payments exist but revenue is 0, log ERROR
    if payment_count > 0 and revenue == Decimal("0.00"):
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"GYM DASHBOARD BUG: {payment_count} payments exist but revenue=0! "
            f"Business={business.id}, Range={start_date} to {end_date}"
        )

    # CRITICAL DEBUG INSTRUMENTATION (STEP 1)
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        "GYM_DASH_DEBUG biz=%s loc=%s range=%s start=%s end=%s revenue=%s costs=%s profit=%s mrr=%s payment_count=%s payment_mix=%s",
        business.id if business else None,
        getattr(business, 'location_id', None),
        range_param,
        start_date,
        end_date,
        revenue,
        costs,
        profit,
        mrr,
        payment_count,
        [(pm.get('method'), pm.get('amount')) for pm in payment_mix] if payment_mix else [],
    )

    # Trainer earnings (this month)
    from inventory.models_verticals import TrainerFee

    try:
        trainer_earnings = TrainerFee.objects.filter(
            business=business, created_at__gte=month_start, created_at__lte=month_end
        ).aggregate(
            total=Coalesce(Sum("amount"), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2))
        )[
            "total"
        ]
    except Exception:
        # TrainerFee table may not exist yet
        trainer_earnings = Decimal("0.00")

    # Check-ins / sessions
    today_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_dt - timedelta(days=today_dt.weekday())

    # Safely query TimeLog (may not exist in all environments)
    try:
        sessions_today = TimeLog.objects.filter(business=business, kind="ARRIVAL", ts__gte=today_dt).count()

        sessions_this_week = TimeLog.objects.filter(business=business, kind="ARRIVAL", ts__gte=week_start).count()
    except Exception:
        # TimeLog table doesn't exist or is not configured
        sessions_today = 0
        sessions_this_week = 0

    # Gamification KPIs: Today's check-ins and Top streak
    from inventory.models_verticals import GymCheckIn

    try:
        checkins_today_count = GymCheckIn.objects.filter(business=business, timestamp__gte=today_dt).count()

        # Top streak member
        top_streak_member = (
            GymMember.objects.filter(business=business, is_active=True, is_archived=False, streak_days__gt=0)
            .order_by("-streak_days")
            .first()
        )
        top_streak_name = top_streak_member.name if top_streak_member else None
        top_streak_days = top_streak_member.streak_days if top_streak_member else 0
    except Exception:
        checkins_today_count = 0
        top_streak_name = None
        top_streak_days = 0

    # ===== NEW: Personalized dashboard enhancements (quotes & greetings) =====
    ctx_enhancements = {}
    try:
        import json as json_lib

        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting (changes 3x daily: morning, afternoon, evening)
        greeting_ctx = get_personalized_greeting(request.user, business)

        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, "logo") and business.logo:
            brand_logo_url = business.logo.url

        # Hourly quotes (rotates every hour)
        daily_quotes = get_todays_quotes(request.user, count=10)

        # Extract quote texts for JavaScript rotation
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json_data = json_lib.dumps(quote_texts)

        ctx_enhancements.update(
            {
                "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
                "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
                "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
                "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
                "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
                "DASHBOARD_BRAND_TITLE": business.name if business else "Gym Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    # Recent payments: respect the selected filter
    recent_payments_qs = GymPayment.objects.filter(member__business=business).select_related("member", "paid_by")
    
    # Apply date filtering to recent payments based on selected range
    if range_start_dt is not None and range_end_dt is not None:
        recent_payments_qs = recent_payments_qs.filter(paid_at__gte=range_start_dt, paid_at__lte=range_end_dt)
    # For all_time, no date filter is applied (shows all payments)
    
    recent_payments = recent_payments_qs.order_by("-paid_at")[:10]

    ctx.update(
        {
            "active_tab": "dashboard",  # For navigation highlighting
            "hero_title": "Gym & Fitness",
            "hero_blurb": "Monitor member pipelines, session scans, and wallet activity for your gym.",
            # Staff stats
            "manager_count": stats["managers"],
            "agent_count": stats["agents"],
            "recent_members": stats["recent"],
            # Member KPIs
            "total_members": total_members,
            "members_active_count": members_active_count,  # Template expects this
            "members_in_arrears": members_in_arrears,
            # Financial KPIs - Daily metrics (today, yesterday, this month)
            "costs_today": costs_today,
            "costs_yesterday": costs_yesterday,
            "costs_this_month": costs_this_month,
            "revenue_today": revenue_today,
            "revenue_yesterday": revenue_yesterday,
            "revenue_this_month": revenue_this_month,
            "profit_today": profit_today,
            "profit_yesterday": profit_yesterday,
            "profit_this_month": profit_this_month,
            # Financial KPIs (legacy/default values for backward compatibility)
            "mrr": mrr,
            "payment_count": payment_count,
            "revenue": revenue,  # Defaults to this month
            "costs": costs,  # Defaults to this month
            "profit": profit,  # Defaults to this month
            "payment_mix": payment_mix,
            "trainer_earnings": trainer_earnings,
            # Date range filter
            "range_key": range_param,
            "range_label": range_label,
            "selected_month": selected_month,  # For month picker
            # Recent payments (filtered by selected range)
            "recent_payments": recent_payments,
            # Session KPIs
            "sessions_today": sessions_today,
            "sessions_this_week": sessions_this_week,
            # Gamification KPIs
            "checkins_today": checkins_today_count,
            "top_streak_name": top_streak_name,
            "top_streak_days": top_streak_days,
            # Billing/subscription safe defaults (gym doesn't use subscriptions)
            "membership": None,
            "subscription": None,
            "quotes_json": "[]",
            **ctx_enhancements,  # Merge dashboard enhancements
        }
    )

    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context

    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "verticals/gym/dashboard.html", ctx)
