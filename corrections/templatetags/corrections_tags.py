"""
Template tags for corrections framework.
"""
from django import template

register = template.Library()


@register.filter
def lookup(obj, attr):
    """
    Template filter to dynamically look up an attribute on an object.
    
    Usage: {{ record|lookup:field_name }}
    """
    try:
        return getattr(obj, attr, None)
    except (AttributeError, TypeError):
        return None

