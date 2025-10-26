# billing/notify.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

# ---- Best-effort in-app notifications adapter --------------------------
def _notify_in_app(*, title: str, body: str, ntype: str = "billing", business=None, user=None, url: str = "") -> None:
    """
    Sends an in-app bell notification if the notifications app is available.
    Tries a couple of common entry points but all calls are best-effort.
    """
    try:
        # Preferred: a utils.notify(title, body, type, business=user/url)
        from notifications.utils import notify  # type: ignore
        notify(title=title, body=body, type=ntype, business=business, user=user, url=url)
        return
    except Exception:
        pass

    try:
        # Fallback: create a Notification model directly if it exists
        from notifications.models import Notification  # type: ignore
        Notification.objects.create(
            type=ntype, title=title, body=body, business=business, user=user, url=url
        )
    except Exception:
        # Silently ignore if notifications app is not wired yet
        pass


# ---- WhatsApp dispatchers (console / Twilio / Meta) --------------------
def _send_whatsapp_console(to: str, body: str) -> None:
    try:
        from django.utils import timezone
        print(f"[WA/console {timezone.now()}] -> {to}: {body}")
    except Exception:
        pass


def _send_whatsapp_twilio(to: str, body: str) -> None:
    # Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM in settings
    from twilio.rest import Client  # type: ignore
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    from_num = settings.TWILIO_WHATSAPP_FROM  # e.g., 'whatsapp:+14155238886'
    if not str(to).startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    client.messages.create(from_=from_num, to=to, body=body)


def _send_whatsapp_meta(to: str, body: str) -> None:
    """
    Meta (WhatsApp Cloud API) simple text message.
    Expects WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID; `to` must be MSISDN (e.g., +265...).
    """
    import json, urllib.request
    token = settings.WHATSAPP_TOKEN
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, data=json.dumps(payload).encode("utf-8"), timeout=10)
    except Exception as e:
        # Don't crash app flow due to WA fanout
        print(f"[WA/meta] send error: {e}")


def send_whatsapp(to: Optional[str], body: str) -> None:
    if not to:
        return
    backend = getattr(settings, "WHATSAPP_BACKEND", "console").lower()
    try:
        if backend == "twilio":
            _send_whatsapp_twilio(to, body)
        elif backend == "meta":
            _send_whatsapp_meta(to, body)
        else:
            _send_whatsapp_console(to, body)
    except Exception as e:
        print(f"[WA] error: {e}")


# ---- Email helpers ------------------------------------------------------
def send_email(subject: str, body: str, to_email: Optional[str], html_template: Optional[str] = None, ctx: Optional[dict] = None):
    if not to_email:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    if html_template:
        html = render_to_string(html_template, ctx or {})
        send_mail(subject, body, from_email, [to_email], html_message=html)
    else:
        send_mail(subject, body, from_email, [to_email])


# ---- Business contact discovery ----------------------------------------
@dataclass
class Contact:
    email: str = ""
    whatsapp: str = ""


def business_contact(business) -> Contact:
    """
    Try multiple common attribute names on Business to find email/WhatsApp.
    """
    if business is None:
        return Contact()
    email = (
        getattr(business, "manager_email", None)
        or getattr(business, "email", None)
        or getattr(business, "owner_email", None)
        or ""
    )
    phone = (
        getattr(business, "whatsapp_number", None)
        or getattr(business, "phone", None)
        or getattr(business, "manager_phone", None)
        or ""
    )
    return Contact(email=email or "", whatsapp=str(phone or "").strip())


# ---- Unified fanout -----------------------------------------------------
def fanout(*, business, title: str, body: str, ntype: str = "billing", url: str = "", to_email: Optional[str] = None, to_whatsapp: Optional[str] = None) -> None:
    """
    Send email + WhatsApp + in-app bell (best-effort).
    """
    c = business_contact(business)
    email = to_email or c.email
    wa = to_whatsapp or c.whatsapp

    # Email (plain-text body; you can switch to an HTML template if you like)
    try:
        send_email(subject=title, body=body, to_email=email)
    except Exception as e:
        print(f"[billing.email] error: {e}")

    # WhatsApp
    try:
        send_whatsapp(wa, body)
    except Exception as e:
        print(f"[billing.wa] error: {e}")

    # In-app bell
    try:
        _notify_in_app(title=title, body=body, ntype=ntype, business=business, url=url)
    except Exception as e:
        print(f"[billing.inapp] error: {e}")


