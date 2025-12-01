from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tenants.models import Membership
from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

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
    stats = _membership_stats(ctx.get("business"))

    ctx.update(
        {
            "hero_title": "Gym & Fitness",
            "hero_blurb": "Monitor member pipelines, session scans, and wallet activity for your gym.",
            "manager_count": stats["managers"],
            "agent_count": stats["agents"],
            "recent_members": stats["recent"],
        }
    )
    return render(request, "verticals/gym/dashboard.html", ctx)

