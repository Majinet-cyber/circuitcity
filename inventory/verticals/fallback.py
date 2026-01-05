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
    Fallback for businesses without a vertical set OR with unrecognized vertical.

    CRITICAL ROUTING LOGIC (to prevent infinite redirect loops):
    - If business_kind is NULL/blank: redirect to settings to configure
    - If business_kind is set but unrecognized: RENDER 200 page with instructions
      (DO NOT redirect to avoid loops)

    This page returns HTTP 200 and provides links to:
    - Generic dashboard (inventory:generic_dashboard)
    - Business settings (to change business type)
    """
    import logging

    log = logging.getLogger(__name__)
    business = getattr(request, "business", None)
    business_kind = getattr(business, "business_kind", None) if business else None

    # CRITICAL: Skip adding warnings for non-HTML requests (sw.js, static files, etc.)
    path = request.path_info or request.path or "/"
    accept = request.META.get("HTTP_ACCEPT", "")
    is_html_request = "text/html" in accept or not accept
    is_settings_page = path.startswith("/accounts/")

    # Case 1: business_kind is NULL/blank - redirect to settings
    if not business_kind:
        # Only add message once per session for HTML requests not on settings pages
        if is_html_request and not is_settings_page:
            session_key = f"warned_no_business_kind_{business.pk if business else 'none'}"
            if not request.session.get(session_key):
                messages.warning(request, "Please set your business type in settings to access your dashboard.")
                request.session[session_key] = True

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
                        "business_kind": business_kind,
                    }
                )
                return render(request, "verticals/no_business.html", ctx)

    # Case 2: business_kind is set but vertical not found (misconfiguration)
    # CRITICAL: DO NOT redirect - render a 200 page to prevent infinite loops
    log.error(
        f"Unrecognized business_kind '{business_kind}' for business {business.name if business else 'Unknown'}. "
        f"Showing /verticals/none/ page. Please update vertical registry or business_kind."
    )

    # Only add warning once per session for HTML requests not on settings pages
    if is_html_request and not is_settings_page:
        session_key = f"warned_vertical_{business.pk if business else 'none'}_{business_kind}"
        if not request.session.get(session_key):
            messages.warning(
                request,
                f"Your business type ('{business_kind}') is not fully configured yet. "
                "Showing generic dashboard. Contact support for assistance.",
            )
            request.session[session_key] = True

    # RENDER a 200 page (DO NOT redirect to prevent loops)
    ctx = base.base_context(request)
    ctx.update(
        {
            "hero_title": "Business Type Not Configured",
            "hero_blurb": f"Your business type ('{business_kind}') is not fully configured yet.",
            "business_kind": business_kind,
            "show_generic_dashboard_link": True,
            "show_settings_link": True,
        }
    )
    return render(request, "verticals/no_business.html", ctx)
