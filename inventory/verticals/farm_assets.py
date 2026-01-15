# inventory/verticals/farm_assets.py
"""
Farm Assets view for tracking farm equipment, tools, and infrastructure.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from tenants.utils import require_business
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def assets_landing(request: HttpRequest) -> HttpResponse:
    """
    Farm Assets landing page.
    """
    ctx = base.base_context(request)
    
    ctx.update({
        "active_tab": "assets",
        "hero_title": "Farm Assets",
        "hero_blurb": "Track your farm equipment, tools, and infrastructure",
    })
    
    return render(request, "verticals/farm/assets_landing.html", ctx)
