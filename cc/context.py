# cc/context.py
from __future__ import annotations

from typing import Any, Dict
from django.conf import settings


# -------------------------------
# Project-wide globals for templates
# -------------------------------
def globals(request) -> Dict[str, Any]:  # noqa: A001 - keep name for Django settings
    """
    Injects app-wide constants and feature flags into every template.
    """
    return {
        "APP_NAME": getattr(settings, "APP_NAME", "Circuit City"),
        "APP_ENV": getattr(settings, "APP_ENV", "dev"),
        "STATIC_VERSION": getattr(settings, "STATIC_VERSION", "dev"),
        # Useful across many templates (e.g., base.html, dashboards)
        "FEATURES": getattr(settings, "FEATURES", {}),
        "NOTIFICATIONS_POLL_MS": getattr(settings, "NOTIFICATIONS_POLL_MS", 15000),
    }


# -------------------------------
# Role helpers used by templates
# -------------------------------
def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _user_in_any_group(user, names) -> bool:
    try:
        user_groups = set(g.name for g in user.groups.all())  # type: ignore[attr-defined]
        return any(n in user_groups for n in names)
    except Exception:
        return False


def _is_manager(user) -> bool:
    """
    Consider a user a 'manager' if any of the following is true:
      - is_superuser
      - is_staff
      - belongs to a group listed in settings.ROLE_GROUP_MANAGER_NAMES
      - has profile.is_manager = True
    """
    if not user or not user.is_authenticated:
        return False
    if _safe_getattr(user, "is_superuser", False):
        return True
    if _safe_getattr(user, "is_staff", False):
        return True
    group_names = getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"])
    if _user_in_any_group(user, group_names):
        return True
    profile = _safe_getattr(user, "profile", None)
    return bool(profile and _safe_getattr(profile, "is_manager", False))


def _is_agent(user) -> bool:
    """
    Agent = authenticated user who is NOT a manager and NOT staff.
    """
    return bool(
        user
        and user.is_authenticated
        and not _is_manager(user)
        and not _safe_getattr(user, "is_staff", False)
    )


def role_flags(request) -> Dict[str, Any]:
    """
    Inject booleans for simple, fast role checks in templates:
      - IS_MANAGER: True for managers/staff/superusers
      - IS_AGENT:   True for regular agents (non-staff, non-manager)
    """
    u = _safe_getattr(request, "user", None)
    return {
        "IS_MANAGER": _is_manager(u),
        "IS_AGENT": _is_agent(u),
    }


