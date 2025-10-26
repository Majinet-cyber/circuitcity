# core/templatetags/nsurl.py
from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()

@register.simple_tag(takes_context=True)
def ns_url(context, viewname, *args, **kwargs):
    """
    Try normal reverse first. If it fails due to a missing namespace,
    try stripping the namespace (e.g., 'inventory:scan_in' -> 'scan_in').
    """
    try:
        return reverse(viewname, args=args, kwargs=kwargs)
    except NoReverseMatch:
        if ":" in viewname:
            _, bare = viewname.split(":", 1)
            try:
                return reverse(bare, args=args, kwargs=kwargs)
            except NoReverseMatch:
                pass
        raise


