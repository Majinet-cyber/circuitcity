# billing/templatetags/billing_tags.py
from __future__ import annotations

from datetime import datetime
from django import template
from django.utils import timezone

from billing.vertical_copy import get_billing_copy, get_billing_copy_for_business

register = template.Library()


@register.simple_tag(takes_context=True)
def vertical_copy(context):
    """
    Get vertical-aware billing copy for the current business.
    
    Usage in template:
        {% vertical_copy as copy %}
        {{ copy.location_singular }}  -> "farm" or "shop"
        {{ copy.staff_plural }}       -> "assistant managers" or "agents"
    """
    request = context.get("request")
    business = getattr(request, "business", None)
    return get_billing_copy_for_business(business)


@register.filter
def plan_description(plan, business):
    """
    Format plan description with vertical-appropriate terminology.
    
    Usage:
        {{ plan|plan_description:business }}
    """
    copy = get_billing_copy_for_business(business)
    max_stores = getattr(plan, "max_stores", 1)
    max_agents = getattr(plan, "max_agents", 0)
    return copy.format_plan_description(max_stores, max_agents)


@register.inclusion_tag("billing/components/subscription_badge.html", takes_context=True)
def subscription_badge(context):
    """
    Renders a small "Trial â€“ X days left" / "Active" / "Grace" badge.
    Expects request.business.subscription if tenants middleware is active.
    """
    request = context.get("request")
    sub = getattr(getattr(request, "business", None), "subscription", None)
    days_left = None
    label = "No subscription"
    tone = "secondary"

    if sub:
        status = sub.status or "trial"
        if status == "trial" and sub.trial_end:
            today = timezone.localdate()
            dl = (sub.trial_end.date() - today).days
            days_left = max(dl, 0)
            label = f"Trial â€” {days_left} day{'s' if days_left != 1 else ''} left"
            tone = "warning" if days_left <= 3 else "info"
        elif status == "active":
            label = "Active"
            tone = "success"
        elif status == "grace":
            label = "Grace"
            tone = "warning"
        elif status == "past_due":
            label = "Past due"
            tone = "danger"
        elif status == "expired":
            label = "Expired"
            tone = "danger"
        else:
            label = status.replace("_", " ").title()
            tone = "secondary"

    return {"label": label, "tone": tone}
