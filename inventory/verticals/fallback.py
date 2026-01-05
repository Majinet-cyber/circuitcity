from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from tenants.utils import require_business

from . import base


@login_required
@require_business
def no_business(request):
    """
    Fallback for businesses without a vertical set.
    Instead of showing "Select your business type", redirect to settings
    where they can configure their business.

    CRITICAL: This prevents /verticals/none/ from being a valid landing page.
    """
    # Add a helpful message
    messages.warning(request, "Please set your business type in settings to access your dashboard.")

    # Try to redirect to settings
    try:
        return redirect(reverse("accounts:settings_unified"))
    except NoReverseMatch:
        try:
            return redirect(reverse("accounts:settings_profile"))
        except NoReverseMatch:
            # Last resort: show the page with instructions
            ctx = base.base_context(request)
            ctx.update(
                {
                    "hero_title": "Set up your business",
                    "hero_blurb": "Configure your business type in settings to get started.",
                }
            )
            return render(request, "verticals/no_business.html", ctx)
