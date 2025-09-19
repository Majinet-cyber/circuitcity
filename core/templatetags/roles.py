from django import template
from tenants.utils import is_manager, is_agent

register = template.Library()

@register.simple_tag(takes_context=True)
def is_manager_(context):
    return is_manager(context["request"].user)

@register.simple_tag(takes_context=True)
def is_agent_(context):
    return is_agent(context["request"].user)
