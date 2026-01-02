from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tenants.utils import require_business

from . import base


@login_required
@require_business
def no_business(request):
    ctx = base.base_context(request)
    ctx.update(
        {
            "hero_title": "Select your business type",
            "hero_blurb": "Set a business vertical so we can launch the correct dashboard.",
        }
    )
    return render(request, "verticals/no_business.html", ctx)
