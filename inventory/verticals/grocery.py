from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

from . import base


@login_required
@require_business
def dashboard(request):
    """
    Main dashboard for Grocery vertical.
    TODO: Implement proper grocery dashboard later.
    For now, shows phones dashboard as temporary solution.
    """
    # TEMPORARY: Call phones dashboard until grocery dashboard is ready
    from inventory.views_phones import phones_dashboard
    return phones_dashboard(request)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def hub(request):
    """
    Grocery hub page - quick access to all grocery features.
    """
    ctx = base.base_context(request)
    ctx.update({
        "page_title": "Grocery Hub",
        "vertical_name": "Grocery",
    })
    return render(request, "verticals/grocery/hub.html", ctx)


# Sales history and other views are handled by inventory/views_grocery.py
# This module just provides the entry points for the verticals namespace

