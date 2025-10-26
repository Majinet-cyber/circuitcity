from __future__ import annotations

import hashlib
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


# ----------------------------------------
# Avatar: initials fallback
# ----------------------------------------
@register.filter
def initials(user):
    """
    Returns the initials of the user's name.
    If the user has no first/last name, fall back to username or '?'.
    """
    if not user:
        return "?"
    name = ""
    if hasattr(user, "first_name") and user.first_name:
        name += user.first_name[0]
    if hasattr(user, "last_name") and user.last_name:
        name += user.last_name[0]
    if not name and getattr(user, "username", None):
        name = user.username[0]
    return name.upper() or "?"


# ----------------------------------------
# Gravatar fallback for avatars
# ----------------------------------------
@register.filter
def gravatar_url(email, size=100):
    """
    Returns the Gravatar URL for the given email address.
    Uses a default fallback image if email is missing.
    """
    if not email:
        # Fallback icon (generated avatar)
        return f"https://ui-avatars.com/api/?name=User&size={size}&background=0D6EFD&color=fff"
    email = email.strip().lower()
    email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{email_hash}?s={size}&d=identicon"


# ----------------------------------------
# Active tab detection for settings nav
# ----------------------------------------
@register.simple_tag(takes_context=True)
def active_tab(context, tab_name):
    """
    Returns 'active' if the current URL name matches the given tab name.
    Useful for highlighting the active tab in settings navigation.
    """
    try:
        current_url = context["request"].resolver_match.url_name
        return "active" if current_url == tab_name else ""
    except Exception:
        return ""


# ----------------------------------------
# Check if user has 2FA enabled
# ----------------------------------------
@register.filter
def has_2fa(user):
    """
    Returns True if the user has a confirmed OTP device registered.
    Used for showing 2FA badges.
    """
    try:
        return hasattr(user, "otp_device") and user.otp_device is not None
    except Exception:
        return False


# ----------------------------------------
# Render field errors (Bootstrap-friendly)
# ----------------------------------------
@register.filter(name="render_errors")
def render_errors(field):
    """
    Renders Bootstrap-friendly error messages for a form field.
    Usage: {{ form.field|render_errors }}
    """
    if not field.errors:
        return ""
    html = "".join([f"<div class='invalid-feedback d-block'>{err}</div>" for err in field.errors])
    return mark_safe(html)


