# tenants/templatetags/form_extras.py
from __future__ import annotations

from django import template
from django.utils.html import format_html

register = template.Library()


def _as_bound(field):
    """
    Allow passing either a BoundField or a string; strings are returned as-is.
    """
    try:
        from django.forms.boundfield import BoundField
        if isinstance(field, BoundField):
            return field
    except Exception:
        pass
    return None


@register.filter(name="add_class")
def add_class(field, css_classes: str = ""):
    """
    Usage in templates:
        {{ form.email|add_class:"input w-full" }}
    Works for both BoundField and plain strings (strings are returned unchanged).
    """
    bf = _as_bound(field)
    if not bf:
        return field  # leave strings unchanged
    return bf.as_widget(attrs={"class": f"{css_classes}".strip()})


@register.filter(name="add_attr")
def add_attr(field, arg: str):
    """
    Generic attribute adder:
        {{ form.email|add_attr:"placeholder:Enter email" }}
        {{ form.phone|add_attr:"data-role:phone" }}
    """
    bf = _as_bound(field)
    if not bf:
        return field
    if ":" not in arg:
        return bf.as_widget(attrs={})
    key, val = arg.split(":", 1)
    return bf.as_widget(attrs={key.strip(): val.strip()})


@register.filter(name="placeholder")
def placeholder(field, text: str):
    """Shortcut for setting placeholder text."""
    bf = _as_bound(field)
    if not bf:
        return field
    return bf.as_widget(attrs={"placeholder": text})


