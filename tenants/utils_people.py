# tenants/utils_people.py
from __future__ import annotations

from typing import Iterable, Optional, Any

from django.conf import settings
from django.contrib.auth.models import Group
from django.urls import reverse
from django.core.mail import send_mail


def attach_user_to_business(
    user: Any,
    business: Any,
    role: str,
    locations: Optional[Iterable[Any]] = None,
) -> None:
    """
    Attach a user to a business and assign a role.

    This is intentionally tolerant and uses common patterns:
      - Pattern A: Business has M2M `users` and supports `.add(user)`.
      - Pattern B: User has FK `business`, so we set and save it.
      - Role is applied via a Django Group named `biz:{business.pk}:{role}`.
      - If a profile with `default_location` exists, we set the first location.
    """
    # Pattern A: Business has M2M to users
    try:
        if hasattr(business, "users") and hasattr(business.users, "add"):
            business.users.add(user)
        # Pattern B: User has FK to business
        elif hasattr(user, "business"):
            setattr(user, "business", business)
            try:
                user.save(update_fields=["business"])
            except Exception:
                # If update_fields doesn't match, fallback to a plain save.
                user.save()
    except Exception:
        # Non-fatal: keep going to apply groups/locations even if this failed.
        pass

    # Apply role via Django groups (tenant-scoped group name)
    try:
        group_name = f"biz:{getattr(business, 'pk', getattr(business, 'id', 'unknown'))}:{role}"
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
    except Exception:
        # Group assignment shouldn't block rest of the flow
        pass

    # Optional: set a default location on user.profile.default_location
    try:
        if locations:
            default_loc = next(iter(locations), None)
            if (
                default_loc is not None
                and hasattr(user, "profile")
                and hasattr(user.profile, "default_location")
            ):
                user.profile.default_location = default_loc
                try:
                    user.profile.save(update_fields=["default_location"])
                except Exception:
                    user.profile.save()
    except Exception:
        pass


def invite_link(request, invite) -> str:
    """
    Build an absolute URL for accepting an invite.
    Assumes a URL pattern named 'tenants:accept_invite' that takes invite.token.
    """
    path = reverse("tenants:accept_invite", args=[invite.token])
    return request.build_absolute_uri(path)


def send_invitation(invite, url: str) -> None:
    """
    Send the invitation message.

    - If invite.email is present, send a simple email via Django's send_mail.
    - If invite.phone is present, print a WhatsApp/SMS-style message to console
      when WHATSAPP_BACKEND='console' (safe default stub).
    """
    subject = "You're invited to join Circuit City"
    business_name = getattr(getattr(invite, "business", None), "name", "your business")
    role = getattr(invite, "role", "member")
    full_name = getattr(invite, "full_name", "")
    expires_at = getattr(invite, "expires_at", None)

    expiry_txt = ""
    try:
        if expires_at is not None:
            expiry_txt = f"\nThis link expires on {expires_at:%Y-%m-%d %H:%M}."
    except Exception:
        pass

    body = (
        f"Hi {full_name},\n\n"
        f"You've been invited to join {business_name} on Circuit City as {role}.\n"
        f"Click to accept and set your password:\n{url}\n"
        f"{expiry_txt}\n"
    ).strip()

    # Email (best-effort, silent on failure)
    try:
        if getattr(invite, "email", None):
            from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
            send_mail(subject, body, from_addr, [invite.email], fail_silently=True)
    except Exception:
        pass

    # WhatsApp/SMS stub (console backend)
    try:
        backend = getattr(settings, "WHATSAPP_BACKEND", "console")
        if getattr(invite, "phone", None) and backend == "console":
            print(f"[WHATSAPP:console] to {invite.phone}\n{body}")
    except Exception:
        pass


__all__ = ["attach_user_to_business", "invite_link", "send_invitation"]
