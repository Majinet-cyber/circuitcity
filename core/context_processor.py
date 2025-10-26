# circuitcity/core/context_processors.py
from __future__ import annotations

from typing import Dict, Any
from django.conf import settings

# ---------------------------------------------------------------------
# Safe import of business rules (fallback keeps app running)
# ---------------------------------------------------------------------
try:
    from core.business_rules import get_rule, BUSINESS_TYPES  # type: ignore
except Exception:  # pragma: no cover
    # Minimal fallback so templates never crash if the module isn't present yet
    class _Rule:
        def __init__(self, code: str, name: str, serial_min: int, serial_max: int, require_imei: bool):
            self.code = code
            self.name = name
            self.serial_min = serial_min
            self.serial_max = serial_max
            self.require_imei = require_imei

    _DEFAULT_RULE = _Rule("phone_sales", "Phone sales", 15, 15, True)

    def get_rule(code: str | None):  # type: ignore
        return _DEFAULT_RULE

    BUSINESS_TYPES = {  # type: ignore
        "phone_sales": _DEFAULT_RULE,
    }

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------
def role_flags(request) -> Dict[str, Any]:
    """
    Injects booleans for templates:
      IS_MANAGER â€” True for managers/staff/superusers
      IS_AGENT   â€” True for agents (non-staff, non-manager)
    """
    u = _safe_getattr(request, "user", None)
    return {
        "IS_MANAGER": _is_manager(u),
        "IS_AGENT": _is_agent(u),
    }


def biz_context(request) -> Dict[str, Any]:
    """
    Single source of truth for business-type driven behavior.
    Exposes:
      cc_business         â€” active Business (or None)
      cc_business_code    â€” normalized code ('phone_sales', 'pharmacy', ...)
      cc_business_name    â€” human name
      cc_serial_min/max   â€” allowed serial length range (IMEI/SKU)
      cc_require_imei     â€” UI hint for phones
      cc_business_types   â€” map of available types (for sign-up selector)
    """
    biz = _safe_getattr(request, "active_business", None)
    biz_code = _safe_getattr(biz, "business_type", None)
    rule = get_rule(biz_code)

    return {
        "cc_business": biz,
        "cc_business_code": rule.code,
        "cc_business_name": rule.name,
        "cc_serial_min": rule.serial_min,
        "cc_serial_max": rule.serial_max,
        "cc_require_imei": bool(getattr(rule, "require_imei", False)),
        "cc_business_types": BUSINESS_TYPES,
    }


