# core/templatetags/include_extras.py
from django import template
from django.template.loader import get_template
from django.template import TemplateDoesNotExist

register = template.Library()

@register.simple_tag(takes_context=True)
def include_if_exists(context, template_name, **kwargs):
    """
    Usage (in templates):
      {% load include_extras %}
      {% include_if_exists "partials/topbar.html" %}
      {% include_if_exists "partials/sidebar.html" user=user theme=theme %}
    Renders nothing if the template is missing.
    """
    try:
        t = get_template(template_name)
    except TemplateDoesNotExist:
        return ""
    ctx = context.flatten()
    ctx.update(kwargs)
    return t.render(ctx)


