# circuitcity/core/context_processor.py
from __future__ import annotations

from typing import Dict, Any
from django.conf import settings


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
    Manager if:
      - superuser OR is_staff, OR
      - in any group from settings.ROLE_GROUP_MANAGER_NAMES, OR
      - user.profile.is_manager == True
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
    """Agent = authenticated, not staff, not manager."""
    return bool(user and user.is_authenticated and not _is_manager(user) and not _safe_getattr(user, "is_staff", False))


def role_flags(request) -> Dict[str, Any]:
    """
    Injects booleans for templates:
      IS_MANAGER — True for managers/staff/superusers
      IS_AGENT   — True for agents (non-staff, non-manager)
    """
    u = _safe_getattr(request, "user", None)
    return {
        "IS_MANAGER": _is_manager(u),
        "IS_AGENT": _is_agent(u),
    }
