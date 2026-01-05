from django import template

from hq.permissions import is_hq_admin

register = template.Library()


@register.filter
def is_hq(user):  # usage: {% if request.user|is_hq %}
    return is_hq_admin(user)


@register.simple_tag
def querystring(request, **kwargs):
    """
    Build querystring while preserving existing query parameters.
    Usage: ?{% querystring request page=page_obj.previous_page_number %}

    Args:
        request: The request object
        **kwargs: Key-value pairs to add/update in the querystring

    Returns:
        URL-encoded querystring string (e.g., "page=2&q=test")
    """
    q = request.GET.copy()
    for k, v in kwargs.items():
        if v is None:
            q.pop(k, None)
        else:
            q[k] = str(v)
    return q.urlencode()
