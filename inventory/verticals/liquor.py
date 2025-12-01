from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def dashboard(request):
    ctx = base.base_context(request)
    metrics = base.merch_metrics(ctx.get("business"), BusinessKind.LIQUOR)
    shots_enabled = base.merch_queryset(ctx.get("business"), BusinessKind.LIQUOR).filter(has_shots=True).count()

    ctx.update(
        {
            "hero_title": "Liquor & Bar",
            "hero_blurb": "Monitor bottle counts, shot packs, and wallet balances in one place.",
            "product_count": metrics["total"],
            "active_product_count": metrics["active"],
            "scan_required_count": metrics["scan_required"],
            "inventory_tracked_count": metrics["inventory_tracked"],
            "shots_enabled_count": shots_enabled,
            "recent_products": metrics["recent"],
        }
    )
    return render(request, "verticals/liquor/dashboard.html", ctx)

