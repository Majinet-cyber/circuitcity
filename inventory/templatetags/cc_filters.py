# inventory/templatetags/cc_filters.py
"""
Custom template filters for Circuit City templates.
Provides safe, robust filters for common operations.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="get_item")
def get_item(value, key):
    """
    Get item from dict or object attribute by key.

    Usage:
        {{ my_dict|get_item:"key_name" }}
        {{ my_object|get_item:"attribute_name" }}

    Returns:
        The value if found, empty string ("") if not found or on error.
        Never raises an exception.

    Examples:
        >>> get_item({"a": 3}, "a")
        3
        >>> get_item({"a": 3}, "b")
        ""
        >>> get_item(None, "a")
        ""
    """
    if value is None:
        return ""

    try:
        # Try dict-like access first
        if hasattr(value, "__getitem__"):
            return value[key]
        # Try object attribute access
        elif hasattr(value, key):
            return getattr(value, key)
        else:
            return ""
    except (KeyError, TypeError, AttributeError, IndexError):
        return ""


@register.filter(name="mul")
def mul(a, b):
    """
    Multiply two numeric values safely.

    Usage:
        {{ value1|mul:value2 }}

    Handles:
        - None values (treated as 0)
        - String numbers (converted to Decimal)
        - int, float, Decimal types
        - Invalid inputs (returns 0)

    Returns:
        Decimal result of multiplication, or 0 on error.
        Never raises an exception.

    Examples:
        >>> mul("2", "3")
        Decimal('6')
        >>> mul(2.5, 4)
        Decimal('10.0')
        >>> mul(None, 5)
        Decimal('0')
        >>> mul("invalid", 5)
        Decimal('0')
    """
    # Handle None values
    if a is None:
        a = 0
    if b is None:
        b = 0

    try:
        # Convert to Decimal for precision
        a_decimal = Decimal(str(a)) if not isinstance(a, Decimal) else a
        b_decimal = Decimal(str(b)) if not isinstance(b, Decimal) else b

        return a_decimal * b_decimal
    except (ValueError, TypeError, InvalidOperation, ArithmeticError):
        # Return 0 for any error (invalid string, overflow, etc.)
        return Decimal("0")
