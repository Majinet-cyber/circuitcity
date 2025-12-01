# inventory/templatetags/roles.py
from django import template
from django.conf import settings

register = template.Library()

ROLE_GROUP_MANAGER_NAMES = set(getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"]))
ROLE_GROUP_AGENT_NAMES = set(getattr(settings, "ROLE_GROUP_AGENT_NAMES", ["Agent"]))


@register.simple_tag(takes_context=True)
def in_group(context, name: str):
    user = context.get("request").user
    return getattr(user, "is_superuser", False) or user.groups.filter(name=name).exists()


@register.simple_tag(takes_context=True)
def is_auditor(context):
    user = context.get("request").user
    return user.groups.filter(name="Auditor").exists()


@register.filter(name="is_manager")
def is_manager(user):
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
def is_agent(user):
    """
    Template filter: {{ request.user|is_agent }}
    Returns True if user is in Agent group but NOT a manager.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    if is_manager(user):
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


