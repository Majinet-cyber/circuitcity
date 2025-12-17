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

# Prefer fully qualified path first, then app-shortcut, else fallback no-ops.
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
        def _is_manager(_user):  # type: ignore
            return False
        def _is_agent(_user):  # type: ignore
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
    """True if the current user is a manager."""
    user = _get_user_from_context(context)
    try:
        return bool(_is_manager(user)) if user is not None else False
    except Exception:
        return False


@register.simple_tag(takes_context=True)
def is_agent_(context) -> bool:
    """True if the current user is an agent."""
    user = _get_user_from_context(context)
    try:
        return bool(_is_agent(user)) if user is not None else False
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
    Returns True if user is superuser/staff or in Manager/Admin group.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
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
    Returns True if user is in Agent group but NOT a manager.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
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


