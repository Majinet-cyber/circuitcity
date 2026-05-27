"""
Template filters for the Clothing vertical.
"""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="clothing_category_display")
def clothing_category_display(category_value: str) -> str:
    """
    Convert a clothing category slug to a human-readable display name.

    Handles both predefined categories (e.g. "shirt" → "Shirt") and
    custom slugified categories (e.g. "soccer-jerseys" → "Soccer Jerseys").

    Usage in templates:
        {{ product.category|clothing_category_display }}
    """
    if not category_value:
        return ""
    try:
        from inventory.clothing_config import get_category_display
        return get_category_display(category_value)
    except Exception:
        return category_value.replace("-", " ").replace("_", " ").title()
