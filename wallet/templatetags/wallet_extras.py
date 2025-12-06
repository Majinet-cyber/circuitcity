# wallet/templatetags/wallet_extras.py
"""
Custom template filters for wallet app.
"""
from django import template

register = template.Library()


@register.filter(name="abs")
def abs_filter(value):
    """
    Return the absolute value of a number.
    
    Usage: {{ some_negative_number|abs }}
    """
    try:
        return abs(value)
    except (TypeError, ValueError):
        return value

