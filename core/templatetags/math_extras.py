# core/templatetags/math_extras.py
"""
Core mathematical template filters available globally.
"""
from django import template

register = template.Library()


@register.filter(name="abs")
def abs_filter(value):
    """
    Returns the absolute value of a number.
    
    Args:
        value: A numeric value (int, float, Decimal) or None
        
    Returns:
        The absolute value of the input, or 0 if value is None or invalid
        
    Examples:
        {{ -42|abs }}         -> 42
        {{ 42|abs }}          -> 42
        {{ -3.14|abs }}       -> 3.14
        {{ None|abs }}        -> 0
    """
    if value is None:
        return 0
    try:
        return abs(value)
    except (TypeError, ValueError):
        return 0

