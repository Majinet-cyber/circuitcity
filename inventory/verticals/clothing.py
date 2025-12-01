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
    return render(request, "verticals/clothing/dashboard.html", ctx)

