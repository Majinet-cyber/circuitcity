# inventory/templatetags/roles.py
from django import template
register = template.Library()

@register.simple_tag(takes_context=True)
def in_group(context, name: str):
    user = context.get("request").user
    return getattr(user, "is_superuser", False) or user.groups.filter(name=name).exists()

@register.simple_tag(takes_context=True)
def is_auditor(context):
    user = context.get("request").user
    return user.groups.filter(name="Auditor").exists()


