# cc/context_processors.py
from __future__ import annotations

import os
from typing import Any, Dict


def build_meta(_request) -> Dict[str, Any]:
    """
    Expose build/version info to templates.

    - BUILD_ID prefers Render/Git envs, falls back to "dev".
    - STATIC_VERSION defaults to BUILD_ID (used as a cache-buster in base.html).
    - Also passes APP_NAME/APP_ENV for convenience in layouts.
    """
    build_id = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or os.getenv("APP_VERSION") or "dev"
    static_version = os.getenv("STATIC_VERSION") or build_id

    return {
        "BUILD_ID": build_id,
        "STATIC_VERSION": static_version,
        "APP_NAME": os.getenv("APP_NAME", "Emajinet"),
        "APP_ENV": os.getenv("APP_ENV", "dev"),
    }


def brand(request) -> Dict[str, Any]:
    """
    Provides `brand_name` and `active_business` to all templates.
    Defensive: if request has no business, we present a sane default.
    """
    biz = getattr(request, "business", None)
    name = getattr(biz, "name", None) or "Circuit City"
    return {
        "brand_name": name,
        "active_business": biz,
    }


def role_flags(request) -> Dict[str, Any]:
    """
    Adds lightweight role booleans commonly used in templates & JS.

    Exposed keys:
      - IS_MANAGER: True if user is a manager (uses middleware-set flags)
      - IS_STAFF: True if user.is_staff
      - IS_SUPERUSER: True if user.is_superuser
      - IS_AGENT: True for authenticated users who are NOT manager/staff
      - SHOW_BILLING: True for managers (same as IS_MANAGER)

    CRITICAL: Uses middleware-set role flags (request.is_manager_plus, request.is_agent_only)
    which are computed by RoleResolutionMiddleware using tenants.utils_roles.
    This ensures managers NEVER downgrade to agent scope.

    Important:
      * Lazy evaluation: only checks DB if absolutely necessary
      * Uses request._cached_user to avoid unnecessary session hits
    """

    def _safe_bool(val: Any) -> bool:
        try:
            return bool(val)
        except Exception:
            return False

    # Only use the cached user; do NOT touch request.user directly.
    user = getattr(request, "_cached_user", None)

    if not user:
        # Treat as anonymous: safe defaults prevent recursive failures on 500s.
        flags = {
            "IS_MANAGER": False,
            "IS_STAFF": False,
            "IS_SUPERUSER": False,
            "IS_AGENT": False,
            "SHOW_BILLING": False,
        }
        return {**flags, "ROLE_FLAGS": flags}

    # Base user flags (no DB hit once user is cached)
    is_staff = _safe_bool(getattr(user, "is_staff", False))
    is_superuser = _safe_bool(getattr(user, "is_superuser", False))
    is_auth = _safe_bool(getattr(user, "is_authenticated", False))

    # ✅ PRIMARY: Use middleware-set role flags (set by RoleResolutionMiddleware)
    # These flags are computed using the centralized tenants.utils_roles logic
    # which implements proper manager precedence
    if hasattr(request, "is_manager_plus") and hasattr(request, "is_agent_only"):
        is_manager = _safe_bool(request.is_manager_plus)
        is_agent = _safe_bool(request.is_agent_only)

        # Safety check: manager cannot be agent (middleware should prevent this)
        if is_manager and is_agent:
            is_agent = False
    else:
        # ✅ FALLBACK: If middleware didn't run, use legacy detection
        # Initialize manager flag
        is_manager = False

        # 1) Check request.membership (set by middleware if present)
        membership = getattr(request, "membership", None)
        if membership:
            membership_role = getattr(membership, "role", None)
            is_manager = _safe_bool((membership_role or "").upper() == "MANAGER")

        # 2) Check user groups (Manager group)
        if not is_manager and is_auth:
            try:
                is_manager = user.groups.filter(name__iexact="Manager").exists()
            except Exception:
                pass

        # 3) Check user.profile.is_manager
        if not is_manager and is_auth:
            try:
                profile = getattr(user, "profile", None)
                if profile:
                    is_manager = _safe_bool(getattr(profile, "is_manager", False))
            except Exception:
                pass

        # 4) Check Membership model for active business
        if not is_manager and is_auth:
            try:
                from tenants.models import Membership

                biz = getattr(request, "business", None)
                if biz:
                    membership_qs = Membership.objects.filter(user=user, business=biz, role__iexact="MANAGER")
                    # Filter by status if field exists
                    if hasattr(Membership, "status"):
                        membership_qs = membership_qs.filter(status__iexact="ACTIVE")
                    is_manager = membership_qs.exists()
            except Exception:
                pass

        # 5) Staff fallback
        if not is_manager:
            is_manager = is_staff

        # Agent = authenticated but not manager/staff
        # CRITICAL FIX: Ensure managers are NEVER treated as agents
        is_agent = _safe_bool(is_auth and not is_manager and not is_staff and not is_superuser)

    flags = {
        "IS_MANAGER": is_manager,
        "IS_STAFF": is_staff,
        "IS_SUPERUSER": is_superuser,
        "IS_AGENT": is_agent,
        "SHOW_BILLING": is_manager,  # Billing is manager-only
    }
    return {**flags, "ROLE_FLAGS": flags}


def app_version(request) -> Dict[str, Any]:
    """
    Expose APP_VERSION to all templates for version display and update checking.
    """
    from django.conf import settings

    return {"APP_VERSION": getattr(settings, "APP_VERSION", "1.1.0")}


def currency_config(request) -> Dict[str, Any]:
    """
    Expose currency configuration to all templates.
    Provides user's display currency preference and exchange rate for JavaScript.
    """
    display_currency = "MWK"
    mwk_per_usd = None

    try:
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            if hasattr(user, "profile") and hasattr(user.profile, "display_currency"):
                display_currency = user.profile.display_currency or "MWK"

        # Always get exchange rate (needed for JS conversion even if user prefers MWK)
        from core.models import ExchangeRate

        rate_value = ExchangeRate.get_rate_value()
        if rate_value:
            mwk_per_usd = float(rate_value)
    except Exception:
        pass  # Fail gracefully - never crash on 404 pages or missing context

    return {
        "DISPLAY_CURRENCY": display_currency,
        "MWK_PER_USD": mwk_per_usd,
    }


def current_year(request) -> Dict[str, Any]:
    """
    Expose the current year to all templates for dynamic copyright notices.

    Returns:
        dict: Contains CURRENT_YEAR key with the current year as an integer.

    Example usage in templates:
        © {{ CURRENT_YEAR }} Emajinet
    """
    from django.utils import timezone

    return {
        "CURRENT_YEAR": timezone.now().year,
    }


def marketing_constants(request) -> Dict[str, Any]:
    """
    Expose marketing and support constants to all templates.
    
    Provides centralized access to:
    - SUPPORT_EMAIL: Official support email (support@emajinet.africa)
    - SUPPORT_WHATSAPP_NUMBER: Real working WhatsApp number
    - MARKETING_ACTIVE_BUSINESSES: Current count of active businesses for marketing
    
    This ensures consistency across all public-facing pages and prevents drift.
    """
    from django.conf import settings
    
    return {
        "SUPPORT_EMAIL": getattr(settings, "SUPPORT_EMAIL", "support@emajinet.africa"),
        "SUPPORT_WHATSAPP_NUMBER": getattr(settings, "SUPPORT_WHATSAPP_NUMBER", "+265 883 596 135"),
        "MARKETING_ACTIVE_BUSINESSES": getattr(settings, "MARKETING_ACTIVE_BUSINESSES", 34),
    }


__all__ = ["build_meta", "brand", "role_flags", "app_version", "currency_config", "current_year", "marketing_constants"]
