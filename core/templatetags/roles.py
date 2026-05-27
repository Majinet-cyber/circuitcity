# circuitcity/core/templatetags/roles.py
"""
Role helpers for templates.

Usage in templates:
    {% load roles %}
    {% if is_manager_ %} ... {% endif %}
    {% if is_agent_ %} ... {% endif %}
    {{ request.user|is_manager }}
    {{ request.user|is_agent }}
    {% in_group "Manager" %}
    {% is_auditor %}

These tags return booleans and are resilient if the tenants utils
module (or request in context) is unavailable.
"""

from __future__ import annotations

from django import template
from django.conf import settings

register = template.Library()

# Settings for role group names
ROLE_GROUP_MANAGER_NAMES = set(getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"]))
ROLE_GROUP_AGENT_NAMES = set(getattr(settings, "ROLE_GROUP_AGENT_NAMES", ["Agent"]))

# -----------------------------------------------------------------------------
# Import role check functions with robust fallbacks
# -----------------------------------------------------------------------------
_is_manager = None
_is_agent = None
_get_active_business = None

# ✅ CRITICAL: Import from centralized role resolution (tenants.utils_roles)
# This ensures consistent role determination across the entire app
try:
    from tenants.utils_roles import is_manager as _ur_is_manager, is_agent as _ur_is_agent, get_active_business as _ur_get_active_business  # type: ignore

    _is_manager = _ur_is_manager
    _is_agent = _ur_is_agent
    _get_active_business = _ur_get_active_business
except Exception:
    # Fallback: try old import paths for backward compatibility
    try:
        from circuitcity.tenants.utils import is_manager as _cc_is_manager, is_agent as _cc_is_agent  # type: ignore

        _is_manager = _cc_is_manager
        _is_agent = _cc_is_agent
    except Exception:
        try:
            from tenants.utils import is_manager as _t_is_manager, is_agent as _t_is_agent  # type: ignore

            _is_manager = _t_is_manager
            _is_agent = _t_is_agent
        except Exception:
            # Final fallbacks: always return False to avoid template crashes.
            def _is_manager(_user, _business=None):  # type: ignore
                return False

            def _is_agent(_user, _business=None):  # type: ignore
                return False


def _get_user_from_context(ctx) -> object | None:
    """
    Extract a user object from the template context safely.
    Returns None if not available.
    """
    try:
        req = ctx.get("request")
        if req is None:
            return None
        return getattr(req, "user", None)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Public template tags
# -----------------------------------------------------------------------------
@register.simple_tag(takes_context=True)
def is_manager_(context) -> bool:
    """
    True if the current user is a manager.
    ✅ Uses centralized role resolution from tenants.utils_roles.
    """
    user = _get_user_from_context(context)
    if user is None:
        return False
    try:
        # Get business from context for business-scoped role check
        req = context.get("request")
        business = getattr(req, "business", None) if req else None
        if business is None and _get_active_business is not None:
            business = _get_active_business(req)

        return bool(_is_manager(user, business))
    except Exception:
        return False


@register.simple_tag(takes_context=True)
def is_agent_(context) -> bool:
    """
    True if the current user is an agent.
    ✅ Uses centralized role resolution from tenants.utils_roles.
    """
    user = _get_user_from_context(context)
    if user is None:
        return False
    try:
        # Get business from context for business-scoped role check
        req = context.get("request")
        business = getattr(req, "business", None) if req else None
        if business is None and _get_active_business is not None:
            business = _get_active_business(req)

        return bool(_is_agent(user, business))
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Optional backward/alternate aliases (non-breaking)
# -----------------------------------------------------------------------------
@register.simple_tag(takes_context=True)
def role_is_manager(context) -> bool:
    return is_manager_(context)


@register.simple_tag(takes_context=True)
def role_is_agent(context) -> bool:
    return is_agent_(context)


# -----------------------------------------------------------------------------
# Additional role filters and tags (merged from inventory)
# -----------------------------------------------------------------------------
@register.simple_tag(takes_context=True)
def in_group(context, name: str):
    """
    Check if the current user is in a specific group.
    Usage: {% in_group "Manager" %}
    """
    try:
        user = context.get("request").user
        return getattr(user, "is_superuser", False) or user.groups.filter(name=name).exists()
    except Exception:
        return False


@register.simple_tag(takes_context=True)
def is_auditor(context):
    """
    Check if the current user is in the Auditor group.
    Usage: {% is_auditor %}
    """
    try:
        user = context.get("request").user
        return user.groups.filter(name="Auditor").exists()
    except Exception:
        return False


@register.filter(name="is_manager")
def is_manager_filter(user):
    """
    Template filter: {{ request.user|is_manager }}
    ✅ Uses centralized role resolution from tenants.utils_roles.

    NOTE: This filter cannot access request.business context (filters don't get context),
    so it checks against None business. For business-scoped checks, use {% is_manager_ %} tag instead.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        # Call centralized role check with no business context (global check)
        # This will check staff/superuser/global groups
        return bool(_is_manager(user, None))
    except Exception:
        # Fallback: simple check if centralized function failed
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        try:
            group_names = set(user.groups.values_list("name", flat=True))
            return bool(group_names.intersection(ROLE_GROUP_MANAGER_NAMES))
        except Exception:
            return False


@register.filter(name="is_agent")
def is_agent_filter(user):
    """
    Template filter: {{ request.user|is_agent }}
    ✅ Uses centralized role resolution from tenants.utils_roles.
    Returns True if user is in Agent group but NOT a manager.

    NOTE: This filter cannot access request.business context (filters don't get context),
    so it checks against None business. For business-scoped checks, use {% is_agent_ %} tag instead.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        # Call centralized role check with no business context (global check)
        return bool(_is_agent(user, None))
    except Exception:
        # Fallback: simple check if centralized function failed
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return False
        if is_manager_filter(user):
            return False
        try:
            group_names = set(user.groups.values_list("name", flat=True))
            return bool(group_names.intersection(ROLE_GROUP_AGENT_NAMES))
        except Exception:
            return False


@register.filter(name="business_kind")
def business_kind(business, default="phones"):
    """
    Template filter: {{ request.business|business_kind }}
    Returns the business_kind or a default.
    """
    if not business:
        return default
    return getattr(business, "business_kind", None) or default
