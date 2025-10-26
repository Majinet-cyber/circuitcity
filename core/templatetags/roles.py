# circuitcity/core/templatetags/roles.py
"""
Role helpers for templates.

Usage in templates:
    {% load roles %}
    {% if is_manager_ %} ... {% endif %}
    {% if is_agent_ %} ... {% endif %}

These tags return booleans and are resilient if the tenants utils
module (or request in context) is unavailable.
"""

from __future__ import annotations

from django import template

register = template.Library()

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


