# core/templatetags/safe_include.py
from django import template
from django.template.loader import get_template
from django.template import TemplateDoesNotExist

register = template.Library()

@register.simple_tag(takes_context=True)
def include_optional(context, template_name, **kwargs):
    """
    Render `template_name` if it exists; otherwise return empty string.
    Usage:
      {% load safe_include %}
      {% include_optional "path/to/partial.html" var1=foo var2=bar %}
    """
    try:
        tpl = get_template(template_name)
    except TemplateDoesNotExist:
        return ""
    ctx = context.flatten()
    ctx.update(kwargs)
    return tpl.render(ctx)
