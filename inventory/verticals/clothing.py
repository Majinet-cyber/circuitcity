from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def dashboard(request):
    ctx = base.base_context(request)
    metrics = base.merch_metrics(ctx.get("business"), BusinessKind.CLOTHING)

    ctx.update(
        {
            "hero_title": "Clothing & Fashion",
            "hero_blurb": "Track outfits, sizes, and curated drops for each location.",
            "product_count": metrics["total"],
            "active_product_count": metrics["active"],
            "scan_required_count": metrics["scan_required"],
            "inventory_tracked_count": metrics["inventory_tracked"],
            "recent_products": metrics["recent"],
        }
    )
    
    # ===== NEW: Personalized dashboard enhancements =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes
        
        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, ctx.get("business"))
        
        # Brand header context
        brand_logo_url = None
        if ctx.get("business") and hasattr(ctx.get("business"), 'logo') and ctx.get("business").logo:
            brand_logo_url = ctx.get("business").logo.url
        
        # Yesterday summary (show once per day)
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, ctx.get("business"))
            if yesterday_summary:
                mark_yesterday_summary_shown(request)
        
        # Payment mix (last 30 days)
        payment_mix = get_payment_mix_for_dashboard(ctx.get("business"), period_days=30, user=None)
        
        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Add to context
        ctx.update({
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": ctx.get("business").name if ctx.get("business") else "Clothing Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "PAYMENT_MIX": payment_mix,
            "PAYMENT_MIX_PERIOD": "Last 30 days",
            "DASHBOARD_QUOTES": daily_quotes,
        })
    except Exception:
        pass  # Gracefully degrade if helpers not available
    
    return render(request, "verticals/clothing/dashboard.html", ctx)

