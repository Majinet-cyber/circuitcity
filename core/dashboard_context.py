"""
Dashboard Context Normalizer - Single Source of Truth for Dashboard Variables

This module provides a centralized way to normalize and provide default values
for dashboard context variables across all verticals (phones, clothing, pharmacy, 
liquor, gym, grocery, etc.).

PROBLEM SOLVED:
- Prevents 500 errors from missing template variables
- Standardizes naming convention (lower_snake_case)  
- Provides backward compatibility for legacy UPPERCASE keys
- Ensures consistent dashboard widget availability across all verticals

USAGE in views:
    from core.dashboard_context import normalize_dashboard_context
    
    ctx = {
        "business": business,
        "revenue": 12345,
        # ... your view-specific context
    }
    
    # Normalize before render
    ctx = normalize_dashboard_context(request, ctx)
    return render(request, "template.html", ctx)

NAMING CONVENTION:
All dashboard context keys use lower_snake_case:
- yesterday_summary (not YESTERDAY_SUMMARY)
- dashboard_quotes (not DASHBOARD_QUOTES)
- dashboard_brand_title (not DASHBOARD_BRAND_TITLE)
- dashboard_greeting (not DASHBOARD_GREETING)
- etc.

Legacy uppercase keys are automatically mapped to lowercase for backward compatibility.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


# Default values for optional dashboard widgets
DASHBOARD_DEFAULTS = {
    # Yesterday summary widget
    "yesterday_summary": None,
    # Daily quotes widget
    "dashboard_quotes": {},
    # Brand header widget
    "dashboard_brand_title": "",
    "dashboard_brand_logo_url": None,
    "dashboard_greeting": None,
    "dashboard_user_name": None,
    "dashboard_show_welcome": False,
    "dashboard_milestone_message": None,
    # Payment mix widget
    "payment_mix": None,
    "payment_mix_period": None,
    # Navigation context
    "active_tab": None,
    # JSON data for JS (optional)
    "quotes_json": "[]",
}


# Mapping of legacy UPPERCASE keys to new lowercase keys
LEGACY_KEY_MAP = {
    "YESTERDAY_SUMMARY": "yesterday_summary",
    "DASHBOARD_QUOTES": "dashboard_quotes",
    "DASHBOARD_BRAND_TITLE": "dashboard_brand_title",
    "DASHBOARD_BRAND_LOGO_URL": "dashboard_brand_logo_url",
    "DASHBOARD_GREETING": "dashboard_greeting",
    "DASHBOARD_USER_NAME": "dashboard_user_name",
    "DASHBOARD_SHOW_WELCOME": "dashboard_show_welcome",
    "DASHBOARD_MILESTONE_MESSAGE": "dashboard_milestone_message",
    "PAYMENT_MIX": "payment_mix",
    "PAYMENT_MIX_PERIOD": "payment_mix_period",
}


def normalize_dashboard_context(
    request: HttpRequest, context: Dict[str, Any], *, inject_defaults: bool = True, preserve_legacy: bool = True
) -> Dict[str, Any]:
    """
    Normalize dashboard context to use lowercase keys with safe defaults.

    This function:
    1. Provides safe defaults for all optional dashboard widgets
    2. Maps any legacy UPPERCASE keys to lowercase equivalents
    3. Never overwrites explicit lowercase values already in context
    4. Optionally preserves legacy UPPERCASE keys for gradual migration

    Args:
        request: Django HttpRequest object
        context: Existing template context dict (will be modified in-place)
        inject_defaults: If True, inject default values for missing keys (default: True)
        preserve_legacy: If True, keep both uppercase and lowercase keys during transition (default: True)

    Returns:
        The normalized context dict (same object as input, modified in-place)

    Example:
        >>> ctx = {"business": biz, "YESTERDAY_SUMMARY": summary_data}
        >>> ctx = normalize_dashboard_context(request, ctx)
        >>> # Now ctx has both "YESTERDAY_SUMMARY" and "yesterday_summary" pointing to same data
    """
    # Step 1: Inject defaults for any missing lowercase keys
    if inject_defaults:
        for key, default_value in DASHBOARD_DEFAULTS.items():
            if key not in context:
                context[key] = default_value

    # Step 2: Map legacy UPPERCASE keys to lowercase
    for legacy_key, modern_key in LEGACY_KEY_MAP.items():
        if legacy_key in context:
            # Copy the value from uppercase to lowercase
            # BUT: don't overwrite if lowercase was already explicitly set
            if (
                modern_key not in context
                or context[modern_key] is None
                or context[modern_key] == DASHBOARD_DEFAULTS.get(modern_key)
            ):
                context[modern_key] = context[legacy_key]

            # Remove the uppercase key UNLESS we're preserving for backward compat
            if not preserve_legacy:
                del context[legacy_key]

    # Step 3: Ensure critical fields are never None if we have alternatives
    # For example, if business exists, use its name as dashboard_brand_title fallback
    if "business" in context and context["business"]:
        business = context["business"]
        if not context.get("dashboard_brand_title"):
            context["dashboard_brand_title"] = getattr(business, "name", "Dashboard")

        # If business has a logo, use it
        if hasattr(business, "logo") and business.logo and not context.get("dashboard_brand_logo_url"):
            context["dashboard_brand_logo_url"] = business.logo.url

    # Step 4: Ensure user-related fields are populated if user exists
    if hasattr(request, "user") and request.user and request.user.is_authenticated:
        user = request.user
        if not context.get("dashboard_user_name"):
            # Prefer first_name, fallback to username
            context["dashboard_user_name"] = user.first_name or user.username

    return context


def inject_dashboard_enhancements(
    request: HttpRequest,
    context: Dict[str, Any],
    business: Any,
    *,
    show_yesterday_summary: bool = True,
    yesterday_condition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    High-level helper to inject all standard dashboard enhancements.

    This is a convenience function that:
    1. Fetches personalized greeting
    2. Fetches yesterday summary (if conditions met)
    3. Fetches daily quotes
    4. Fetches payment mix
    5. Normalizes all context keys

    Args:
        request: Django HttpRequest
        context: Existing context dict
        business: Business model instance
        show_yesterday_summary: Whether to attempt showing yesterday summary (default: True)
        yesterday_condition: Additional condition for yesterday summary, e.g., "range_param == 'today'"

    Returns:
        Normalized context dict with all enhancements

    Example:
        >>> ctx = {"revenue": 12345, "business": biz}
        >>> ctx = inject_dashboard_enhancements(request, ctx, biz)
        >>> return render(request, "dashboard.html", ctx)
    """
    # Import helpers (lazy import to avoid circular dependencies)
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import (
            get_yesterday_summary,
            should_show_yesterday_summary,
            mark_yesterday_summary_shown,
        )
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, business)

        # Yesterday summary (show once per day, with optional condition)
        yesterday_summary = None
        if show_yesterday_summary and should_show_yesterday_summary(request):
            # Check additional condition if provided
            should_fetch = True
            if yesterday_condition:
                # Evaluate the condition string in the context's namespace
                try:
                    should_fetch = eval(yesterday_condition, {}, context)
                except Exception:
                    should_fetch = True  # Default to showing if condition evaluation fails

            if should_fetch:
                yesterday_summary = get_yesterday_summary(request.user, business)
                if yesterday_summary:
                    mark_yesterday_summary_shown(request)

        # Payment mix (last 30 days)
        payment_mix = get_payment_mix_for_dashboard(business, period_days=30, user=None)

        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)

        # Extract quote texts for JavaScript rotation (if needed)
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json = __import__("json").dumps(quote_texts)

        # Add enhancements to context
        context.update(
            {
                "dashboard_greeting": greeting_ctx.get("greeting"),
                "dashboard_user_name": greeting_ctx.get("user_name"),
                "dashboard_show_welcome": greeting_ctx.get("show_welcome"),
                "dashboard_milestone_message": greeting_ctx.get("milestone"),
                "yesterday_summary": yesterday_summary,
                "payment_mix": payment_mix,
                "payment_mix_period": "Last 30 days",
                "dashboard_quotes": daily_quotes,
                "quotes_json": quotes_json,
            }
        )
    except Exception as e:
        # Gracefully degrade if helpers not available
        # Log the error but don't crash the dashboard
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to inject dashboard enhancements: {e}")
        pass

    # Normalize the context (this will handle defaults and legacy keys)
    return normalize_dashboard_context(request, context)
