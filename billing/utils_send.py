# billing/utils_send.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# Try to use your notifications app’s WhatsApp dispatcher if available
try:
    from notifications.backends.whatsapp import send_whatsapp  # type: ignore
except Exception:
    send_whatsapp = None  # type: ignore


@dataclass
class SendResult:
    ok: bool
    channel: str
    detail: str = ""


def send_invoice_email(*, to_email: str, subject: str, html_body: str, text_body: str = "") -> SendResult:
    if not to_email:
        return SendResult(False, "email", "Missing recipient email")
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    msg = EmailMultiAlternatives(subject=subject, body=text_body or "See HTML version.", from_email=from_email, to=[to_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    return SendResult(True, "email", f"Sent to {to_email}")


def send_invoice_whatsapp(*, to_number: str, text: str) -> SendResult:
    if not to_number:
        return SendResult(False, "whatsapp", "Missing WhatsApp number")

    if send_whatsapp:
        # Your notifications backend can decide provider via settings.WHATSAPP_BACKEND
        send_whatsapp(to_number, text)
        return SendResult(True, "whatsapp", f"Sent to {to_number}")

    # Minimal console fallback
    print(f"[WhatsApp:FALLBACK] -> {to_number}\n{text}")
    return SendResult(True, "whatsapp", "Console fallback")
