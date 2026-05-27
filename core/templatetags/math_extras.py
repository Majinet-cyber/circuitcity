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


@register.filter(name="mul")
def mul(value, arg):
    """
    Multiplies the value by the argument.

    Args:
        value: A numeric value (int, float, Decimal) or None
        arg: A numeric value to multiply by, or None

    Returns:
        The product of value * arg, or 0 if either is None or invalid

    Examples:
        {{ 5|mul:3 }}         -> 15
        {{ 10|mul:2.5 }}      -> 25.0
        {{ None|mul:5 }}      -> 0
        {{ 5|mul:None }}      -> 0
    """
    try:
        return (value or 0) * (arg or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


@register.filter(name="div")
def div(value, arg):
    """
    Divides the value by the argument.

    Args:
        value: A numeric value (int, float, Decimal) or None
        arg: A numeric value to divide by, or None

    Returns:
        The quotient of value / arg, or 0 if arg is 0, None, or invalid

    Examples:
        {{ 10|div:2 }}        -> 5.0
        {{ 15|div:3 }}        -> 5.0
        {{ 10|div:0 }}        -> 0
        {{ None|div:5 }}      -> 0
    """
    try:
        divisor = arg or 0
        if divisor == 0:
            return 0
        return (value or 0) / divisor
    except (TypeError, ValueError, AttributeError, ZeroDivisionError):
        return 0
