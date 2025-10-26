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
    Preserves your existing behavior while remaining defensive.
    """
    biz = getattr(request, "business", None)
    name = getattr(biz, "name", None) or "Circuit City"
    return {
        "brand_name": name,
        "active_business": biz,
    }


def role_flags(request) -> Dict[str, Any]:
    """
    Adds lightweight role booleans commonly used in templates.
    - IS_MANAGER mirrors the checks you reference in templates.
    """
    user = getattr(request, "user", None)

    def _is_manager() -> bool:
        try:
            # Explicit membership role takes precedence if present
            membership = getattr(request, "membership", None)
            if getattr(membership, "role", None) == "MANAGER":
                return True

            if user and getattr(user, "is_authenticated", False):
                # App-level manager flag on profile
                profile = getattr(user, "profile", None)
                if getattr(profile, "is_manager", False):
                    return True

                # Staff should be treated as manager in UI logic
                if getattr(user, "is_staff", False):
                    return True
        except Exception:
            pass
        return False

    return {
        "IS_MANAGER": _is_manager(),
    }


__all__ = ["build_meta", "brand", "role_flags"]


