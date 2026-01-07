"""
Custom template tags and filters for CircuitCity.

These helpers are registered as builtins in settings.py, so they work
everywhere without {% load cc_extras %}.
"""
from django import template
from django.utils.safestring import mark_safe
import hashlib

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css):
    """
    Add CSS classes to a form field widget.

    Usage: {{ form.email|add_class:"form-control" }}
    """
    if not hasattr(field, "as_widget"):
        return field
    return field.as_widget(attrs={"class": css})


@register.filter(name="to_int")
def to_int(value):
    """
    Convert value to int safely, returning 0 if conversion fails.

    Usage: {{ some_value|to_int }}
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


@register.filter(name="split")
def split_filter(value, separator=","):
    """
    Split a string by separator.

    Usage: {{ "a,b,c"|split:"," }}
    """
    if not value:
        return []
    return str(value).split(separator)


@register.filter(name="color_for")
def color_for(value):
    """
    Generate a deterministic color from a small palette based on the value.
    Returns a CSS color class or hex color.

    Usage: {{ customer_name|color_for }}
    """
    if not value:
        return "#6c757d"  # gray default

    # Use a pleasant color palette (avoiding raw md5 hex)
    colors = [
        "#3b82f6",  # blue
        "#10b981",  # green
        "#f59e0b",  # amber
        "#ef4444",  # red
        "#8b5cf6",  # violet
        "#ec4899",  # pink
        "#14b8a6",  # teal
        "#f97316",  # orange
    ]

    # Hash the value to get a consistent index
    hash_val = int(hashlib.md5(str(value).encode()).hexdigest(), 16)
    return colors[hash_val % len(colors)]


@register.simple_tag(takes_context=True)
def url_for(context, **kwargs):
    """
    Build a URL with querystring, preserving existing GET params.

    Usage: {% url_for page=2 sort="name" %}

    - Removes params when value is None or empty string
    - Preserves existing GET params not specified
    - Falls back to building ?key=value if request is missing
    """
    request = context.get("request")

    # Start with existing GET params if available
    if request and hasattr(request, "GET"):
        params = dict(request.GET.items())
    else:
        params = {}

    # Update/remove params based on kwargs
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value

    # Build querystring
    if not params:
        return "?"

    pairs = [f"{k}={v}" for k, v in params.items()]
    return "?" + "&".join(pairs)
