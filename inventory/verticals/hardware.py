from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.HARDWARE)
def dashboard(request):
    """
    Main dashboard for Hardware Store vertical.
    Shows: sales overview, stock levels, recent transactions.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Basic metrics (placeholder - will be enhanced with real data)
    ctx.update({
        "page_title": "Hardware Store Dashboard",
        "vertical_name": "Hardware Store",
        "total_products": 0,
        "low_stock_count": 0,
        "today_sales": 0,
        "month_sales": 0,
        "welcome_message": f"Welcome to {business.name if business else 'your'} Hardware Store dashboard",
    })
    
    return render(request, "verticals/hardware/dashboard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.HARDWARE)
def hub(request):
    """
    Hardware Store hub page - quick access to all features.
    """
    ctx = base.base_context(request)
    ctx.update({
        "page_title": "Hardware Store Hub",
        "vertical_name": "Hardware Store",
    })
    return render(request, "verticals/hardware/hub.html", ctx)

