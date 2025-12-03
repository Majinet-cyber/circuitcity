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
    
    # Active gym members
    active_members = GymMember.objects.filter(business=business, is_active=True, is_archived=False)
    total_members = active_members.count()
    
    # Calculate members in arrears
    members_in_arrears = 0
    for member in active_members:
        if member.days_left() == 0:
            members_in_arrears += 1
    
    # Monthly Recurring Revenue (current month)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    current_month_payments = GymPayment.objects.filter(
        member__business=business,
        paid_at__gte=month_start,
        paid_at__lte=month_end
    )
    
    mrr = current_month_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    payment_count = current_month_payments.count()
    
    # Payment mix
    from inventory.models_verticals import PaymentMethod
    payment_mix = []
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
    
    # Costs from wallet (current month expenses)
    costs = GymWalletEntry.objects.filter(
        business=business,
        entry_type="expense",
        created_at__gte=month_start,
        created_at__lte=month_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    # Total revenue (current month income from wallet)
    revenue = GymWalletEntry.objects.filter(
        business=business,
        entry_type="income",
        created_at__gte=month_start,
        created_at__lte=month_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    # Profit
    profit = revenue - costs
    
    # Check-ins / sessions
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    
    sessions_today = TimeLog.objects.filter(
        business=business,
        kind="ARRIVAL",
        timestamp__gte=today
    ).count()
    
    sessions_this_week = TimeLog.objects.filter(
        business=business,
        kind="ARRIVAL",
        timestamp__gte=week_start
    ).count()

    ctx.update(
        {
            "hero_title": "Gym & Fitness",
            "hero_blurb": "Monitor member pipelines, session scans, and wallet activity for your gym.",
            
            # Staff stats
            "manager_count": stats["managers"],
            "agent_count": stats["agents"],
            "recent_members": stats["recent"],
            
            # Member KPIs
            "total_members": total_members,
            "members_in_arrears": members_in_arrears,
            
            # Financial KPIs (current month)
            "mrr": mrr,
            "payment_count": payment_count,
            "revenue": revenue,
            "costs": costs,
            "profit": profit,
            "payment_mix": payment_mix,
            
            # Recent payments
            "recent_payments": GymPayment.objects.filter(member__business=business).select_related("member", "paid_by").order_by("-paid_at")[:10],
            
            # Session KPIs
            "sessions_today": sessions_today,
            "sessions_this_week": sessions_this_week,
        }
    )
    
    # ===== NEW: Personalized dashboard enhancements =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes
        
        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, business)
        
        # Brand header context
        brand_logo_url = None
        if hasattr(business, 'logo') and business.logo:
            brand_logo_url = business.logo.url
        
        # Yesterday summary (show once per day)
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, business)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)
        
        # Payment mix (use existing logic or create standardized version)
        payment_mix_standard = get_payment_mix_for_dashboard(business, period_days=30, user=None)
        
        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Add to context
        ctx.update({
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": business.name if business else "Gym Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "PAYMENT_MIX": payment_mix_standard if payment_mix_standard else None,
            "PAYMENT_MIX_PERIOD": "This Month",  # Gym already shows current month
            "DASHBOARD_QUOTES": daily_quotes,
        })
    except Exception:
        pass  # Gracefully degrade if helpers not available
    
    return render(request, "verticals/gym/dashboard.html", ctx)

