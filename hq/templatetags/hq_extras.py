from django import template
from hq.permissions import is_hq_admin
register = template.Library()

@register.filter
def is_hq(user):  # usage: {% if request.user|is_hq %}
    return is_hq_admin(user)


