from __future__ import annotations
from typing import Iterable
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.urls import reverse


# Hook point for your existing role/tenant wiring.


def attach_user_to_business(user, business, role: str, locations: Iterable=None):
"""
Attempts to attach a user to a business and assign role.
Adapt this to your actual membership model if present.
"""
# Common pattern A: Business has M2M to users
if hasattr(business, "users"):
business.users.add(user)


# Pattern B: User has FK to business
elif hasattr(user, "business"):
setattr(user, "business", business)
user.save(update_fields=["business"]) # noqa


# Roles via Django groups (tenant‑scoped group name)
group_name = f"biz:{business.pk}:{role}"
group, _ = Group.objects.get_or_create(name=group_name)
user.groups.add(group)


# Optional: store default location on profile, if such field exists
if locations:
default_loc = next(iter(locations), None)
if default_loc and hasattr(user, "profile") and hasattr(user.profile, "default_location"):
user.profile.default_location = default_loc
user.profile.save(update_fields=["default_location"]) # noqa




def invite_link(request, invite) -> str:
# Build absolute join URL
path = reverse("tenants:accept_invite", args=[invite.token])
return request.build_absolute_uri(path)




def send_invitation(invite, url: str):
"""Send via email or WhatsApp/SMS. Keep it simple; replace with real gateway later."""
subject = "You're invited to join Circuit City"
body = (
f"Hi {invite.full_name},\n\n"
f"You've been invited to join {invite.business.name} on Circuit City as {invite.role}.\n"
f"Click to accept and set your password: {url}\n\n"
f"This link expires on {invite.expires_at:%Y-%m-%d %H:%M}."
)
# Email if available
if invite.email:
from django.core.mail import send_mail
send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"), [invite.email], fail_silently=True)


# WhatsApp/SMS stub (prints/logs for now)
backend = getattr(settings, "WHATSAPP_BACKEND", "console")
if invite.phone and backend == "console":
print(f"[WHATSAPP:console] -> {invite.phone}\n{body}")