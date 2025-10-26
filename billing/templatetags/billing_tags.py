# billing/templatetags/billing_tags.py
from __future__ import annotations

from datetime import datetime
from django import template
from django.utils import timezone

register = template.Library()

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


