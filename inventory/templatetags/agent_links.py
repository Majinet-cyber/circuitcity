"""
Template filters and tags for making agent names clickable.
"""
from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()


@register.filter
def agent_link(agent, user):
    """
    Convert an agent object to a clickable link (if viewer is a manager).
    
    Usage in template:
        {{ item.assigned_agent|agent_link:request.user }}
    
    Args:
        agent: User object (the agent)
        user: Current user (viewer)
    
    Returns:
        HTML string: clickable link for managers, plain text for others
    """
    if not agent:
        return mark_safe('<span class="text-muted">—</span>')
    
    # Get agent name
    agent_name = agent.get_full_name() or agent.username or agent.email or "Unknown"
    agent_name_escaped = escape(agent_name)
    
    # Check if viewer is a manager (simplified check)
    is_manager = False
    try:
        from core.roles import is_manager as check_manager
        is_manager = check_manager(user)
    except Exception:
        # Fallback: check if user is staff or has is_manager attribute
        is_manager = getattr(user, 'is_staff', False) or getattr(user, 'is_manager', False)
    
    # If manager, make it clickable
    if is_manager:
        try:
            url = reverse('inventory:agent_performance', kwargs={'agent_id': agent.pk})
            return mark_safe(f'<a href="{url}" class="agent-link" style="color:#2563eb;text-decoration:none;font-weight:600">{agent_name_escaped}</a>')
        except Exception:
            # URL reverse failed, return plain text
            return agent_name_escaped
    else:
        # Not a manager, return plain text
        return agent_name_escaped


@register.simple_tag
def agent_performance_url(agent_id):
    """
    Generate URL for agent performance page.
    
    Usage in template:
        {% agent_performance_url agent.id %}
    """
    try:
        return reverse('inventory:agent_performance', kwargs={'agent_id': agent_id})
    except Exception:
        return '#'

