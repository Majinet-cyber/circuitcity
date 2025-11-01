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
    build_id = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
        or os.getenv("APP_VERSION")
        or "dev"
    )
    static_version = os.getenv("STATIC_VERSION") or build_id

    return {
        "BUILD_ID": build_id,
        "STATIC_VERSION": static_version,
        "APP_NAME": os.getenv("APP_NAME", "Circuit City"),
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
      - IS_MANAGER: True if membership role == MANAGER, or (fallback) is_staff
      - IS_STAFF: True if user.is_staff
      - IS_SUPERUSER: True if user.is_superuser
      - IS_AGENT: True for authenticated users who are NOT manager/staff

    Important:
      * Never evaluates request.user (SimpleLazyObject) to avoid DB/session hits,
        especially while rendering error pages.
      * Uses request._cached_user only if AuthenticationMiddleware already resolved it.
      * Avoids touching user.profile or groups/permissions here (they can trigger queries).
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
        }
        return {**flags, "ROLE_FLAGS": flags}

    # Base user flags (no DB hit once user is cached)
    is_staff = _safe_bool(getattr(user, "is_staff", False))
    is_superuser = _safe_bool(getattr(user, "is_superuser", False))
    is_auth = _safe_bool(getattr(user, "is_authenticated", False))

    # Membership-derived manager flag (safe: only use if middleware already set it)
    membership = getattr(request, "membership", None)
    membership_role = getattr(membership, "role", None)
    is_membership_manager = _safe_bool((membership_role or "").upper() == "MANAGER")

    # Unified manager flag: membership takes precedence; staff implies manager as fallback.
    is_manager = is_membership_manager or is_staff

    # Agent = authenticated but not manager/staff
    is_agent = _safe_bool(is_auth and not is_manager and not is_staff)

    flags = {
        "IS_MANAGER": is_manager,
        "IS_STAFF": is_staff,
        "IS_SUPERUSER": is_superuser,
        "IS_AGENT": is_agent,
    }
    return {**flags, "ROLE_FLAGS": flags}


__all__ = ["build_meta", "brand", "role_flags"]
