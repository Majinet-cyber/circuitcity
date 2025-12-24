from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.shortcuts import render
from django.utils import timezone

from tenants.models import Membership
from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import GymMember, GymPayment, GymWalletEntry
from inventory.models_attendance import TimeLog

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
    
    active_members = all_members.filter(
        payments__start_date__lte=today,
        payments__end_date__gte=today,
        payments__is_active=True,
    ).distinct().count()
    
    # In arrears = total members - active members
    in_arrears = total_members - active_members
    
    members_active_count = active_members  # Alias for template compatibility
    members_in_arrears = in_arrears
    
    # Monthly Recurring Revenue (current month)
    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    # Date ranges for metrics
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    current_month_payments = GymPayment.objects.filter(
        member__business=business,
        paid_at__gte=month_start,
        paid_at__lte=month_end
    )
    
    mrr = current_month_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    payment_count = current_month_payments.count()
    
    # Payment mix (handle cases where payment_method might be NULL)
    from inventory.models_verticals import PaymentMethod
    payment_mix = []
    try:
        for method_code, method_label in PaymentMethod.choices:
            method_payments = current_month_payments.filter(payment_method=method_code)
            count = method_payments.count()
            amount = method_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if count > 0:
                payment_mix.append({
                    "method": method_label,
                    "count": count,
                    "amount": amount,
                })
    except Exception as e:
        # If payment_method column doesn't exist or has issues, gracefully handle it
        # This ensures dashboard doesn't crash before migrations are applied
        payment_mix = []
    
    # ============================================================================
    # COSTS: Use admin wallet costs (same source as /wallet/admin/costs/)
    # This fixes the bug where costs added in admin wallet didn't show on dashboard
    # ============================================================================
    from inventory.utils_gym import get_business_costs_for_period
    
    costs_today = get_business_costs_for_period(business, today, today)
    costs_yesterday = get_business_costs_for_period(business, yesterday, yesterday)
    costs_this_month = get_business_costs_for_period(business, month_start.date(), today)
    
    # ============================================================================
    # REVENUE: Calculate from GymPayment for today, yesterday, this month
    # ============================================================================
    revenue_today = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=today_start,
        paid_at__lte=today_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    revenue_yesterday = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=yesterday_start,
        paid_at__lte=yesterday_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    revenue_this_month = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=month_start,
        paid_at__lte=month_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    # ============================================================================
    # PROFIT: Calculate profit = revenue - costs for each period
    # ============================================================================
    profit_today = revenue_today - costs_today
    profit_yesterday = revenue_yesterday - costs_yesterday
    profit_this_month = revenue_this_month - costs_this_month
    
    # Legacy context variables (for backward compatibility)
    costs = costs_this_month
    revenue = revenue_this_month
    profit = profit_this_month
    
    # Trainer earnings (this month)
    from inventory.models_verticals import TrainerFee
    try:
        trainer_earnings = TrainerFee.objects.filter(
            business=business,
            created_at__gte=month_start,
            created_at__lte=month_end
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    except Exception:
        # TrainerFee table may not exist yet
        trainer_earnings = Decimal("0.00")
    
    # Check-ins / sessions
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    
    # Safely query TimeLog (may not exist in all environments)
    try:
        sessions_today = TimeLog.objects.filter(
            business=business,
            kind="ARRIVAL",
            ts__gte=today
        ).count()
        
        sessions_this_week = TimeLog.objects.filter(
            business=business,
            kind="ARRIVAL",
            ts__gte=week_start
        ).count()
    except Exception:
        # TimeLog table doesn't exist or is not configured
        sessions_today = 0
        sessions_this_week = 0

    # ===== NEW: Personalized dashboard enhancements (quotes & greetings) =====
    ctx_enhancements = {}
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_quotes import get_todays_quotes
        import json as json_lib
        
        # Personalized greeting (changes 3x daily: morning, afternoon, evening)
        greeting_ctx = get_personalized_greeting(request.user, business)
        
        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, 'logo') and business.logo:
            brand_logo_url = business.logo.url
        
        # Hourly quotes (rotates every hour)
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Extract quote texts for JavaScript rotation
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json_data = json_lib.dumps(quote_texts)
        
        ctx_enhancements.update({
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": business.name if business else "Gym Dashboard",
            "DASHBOARD_QUOTES": daily_quotes,
            "quotes_json": quotes_json_data,
        })
    except Exception:
        # Gracefully degrade if helpers not available
        pass

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
            
            # Recent payments
            "recent_payments": GymPayment.objects.filter(member__business=business).select_related("member", "paid_by").order_by("-paid_at")[:10],
            
            # Session KPIs
            "sessions_today": sessions_today,
            "sessions_this_week": sessions_this_week,
            
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

