# circuitcity/notifications/utils.py
from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

# Try to import the model, but don't hard-crash if app isn't ready/migrated yet.
try:
    from .models import Notification  # type: ignore
except Exception:  # app not ready / import error
    Notification = None  # type: ignore

log = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------
# Internal readiness checks
# ---------------------------
def _table_exists(model) -> bool:
    """
    True if the model's DB table exists (handles unmigrated dev DBs).
    """
    try:
        if not model:
            return False
        # Use introspection so we don't execute any writes/queries that would fail
        return model._meta.db_table in connection.introspection.table_names()
    except Exception:
        return False


def _notifications_enabled() -> bool:
    """
    Feature flag; default True. Set NOTIFICATIONS_ENABLED=False in settings to disable.
    """
    return getattr(settings, "NOTIFICATIONS_ENABLED", True)


# ---------------------------
# WhatsApp dispatch (pluggable)
# ---------------------------
def _send_whatsapp(number: str, text: str) -> bool:
    """
    Sends a WhatsApp message using one of:
      - 'console' (default): log only
      - 'twilio': requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
      - 'meta'  : WhatsApp Cloud API; requires WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID
    Returns True if (we believe) the message was sent; False otherwise.
    """
    backend = getattr(settings, "WHATSAPP_BACKEND", "console")
    try:
        if backend == "twilio":
            try:
                from twilio.rest import Client  # type: ignore
            except Exception as e:
                log.warning("Twilio not available: %s", e)
                return False
            sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
            tok = getattr(settings, "TWILIO_AUTH_TOKEN", None)
            from_num = getattr(settings, "TWILIO_WHATSAPP_FROM", None)
            if not (sid and tok and from_num):
                log.warning("Twilio missing settings; falling back to console")
                log.info("[WA-console][%s] %s", number, text)
                return False
            client = Client(sid, tok)
            client.messages.create(
                body=text,
                from_=f"whatsapp:{from_num}",
                to=f"whatsapp:{number}",
            )
            return True

        elif backend == "meta":
            import json
            import urllib.request

            token = getattr(settings, "WHATSAPP_TOKEN", None)
            phone_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
            if not (token and phone_id):
                log.warning("Meta WA missing settings; falling back to console")
                log.info("[WA-console][%s] %s", number, text)
                return False

            url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
            data = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": text},
            }
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec - server-to-server
                _ = resp.read()
            return True

        # console/default
        log.info("[WA-console][%s] %s", number, text)
        return True

    except Exception as e:
        log.error("WhatsApp send failed: %s", e, exc_info=True)
        return False


# ---------------------------
# Email helpers
# ---------------------------
def _send_email(subject: str, body: str, recipients: Iterable[str]) -> None:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost")
    emails = [e for e in recipients if e]
    if not emails:
        return
    try:
        send_mail(subject, body, from_email, emails, fail_silently=True)
    except Exception as e:
        log.warning("Email send failed: %s", e)


# ---------------------------
# Recipients discovery
# ---------------------------
def _admin_emails() -> list[str]:
    explicit = getattr(settings, "NOTIFY_ADMIN_EMAILS", None)
    if explicit:
        return [e for e in explicit if e]
    return list(
        User.objects.filter(is_staff=True, email__isnull=False)
        .values_list("email", flat=True)
    )

def _admin_whatsapp_number() -> Optional[str]:
    return getattr(settings, "ADMIN_WHATSAPP_NUMBER", None)

def _agent_whatsapp_number(user) -> Optional[str]:
    # Try common places for phone
    phone = None
    profile = getattr(user, "profile", None)
    if profile:
        phone = getattr(profile, "phone", None) or getattr(profile, "whatsapp", None)
    if not phone:
        phone = getattr(user, "phone", None)
    return phone


# ---------------------------
# Core API
# ---------------------------
def create_notification(
    *,
    audience: str,                 # 'ADMIN' or 'AGENT'
    message: str,
    level: str = "info",
    user=None,                     # required for AGENT
    meta: Optional[dict] = None,
    email: bool = True,
    whatsapp: bool = True,
) -> Optional["Notification"]:
    """
    Create a Notification row if the model/table exists and notifications are enabled.
    If the table isn't ready (e.g., dev without migrations), we **gracefully no-op**
    on the DB write but can still send email/WhatsApp fanout.

    Returns the Notification instance if created, else None.
    """
    # Early feature flag
    if not _notifications_enabled():
        log.info("Notifications disabled via NOTIFICATIONS_ENABLED=False")
        return None

    # Fanout text used by both DB + transports
    subject = "Notification"
    body = message

    # Attempt to write to DB only if model/table is present
    n = None
    if Notification and _table_exists(Notification):
        try:
            n = Notification.objects.create(
                audience=audience,
                user=user if audience == "AGENT" else None,
                message=message,
                level=level,
                meta=meta or {},
            )
        except (OperationalError, ProgrammingError) as e:
            # Table might still be missing or mid-migration; fall through to transport only
            log.warning("Notification DB write failed (will continue without DB row): %s", e)
            n = None
    else:
        log.debug("Notification table not available; skipping DB write.")

    # Admin fanout
    if audience == "ADMIN":
        if email:
            _send_email(subject, body, _admin_emails())
        if whatsapp:
            admin_wa = _admin_whatsapp_number()
            if admin_wa:
                _send_whatsapp(admin_wa, message)

    # Agent direct
    if audience == "AGENT" and user is not None:
        if email and getattr(user, "email", None):
            _send_email(subject, body, [user.email])
        if whatsapp:
            wa = _agent_whatsapp_number(user)
            if wa:
                _send_whatsapp(wa, message)

    return n


# Convenience hooks other apps can call
def notify_payslip_issued(user, period_label: str, amount: float):
    msg = f"Payslip issued for {period_label}: {amount:,.2f}"
    create_notification(
        audience="ADMIN",
        message=f"{user.get_username()} payslip issued ({period_label}).",
        level="success",
    )
    create_notification(
        audience="AGENT",
        user=user,
        message=msg,
        level="success",
    )


def notify_invoice_sent(invoice_no: str, amount: float, to_email: Optional[str] = None):
    msg = f"Invoice {invoice_no} sent for {amount:,.2f}"
    create_notification(audience="ADMIN", message=msg, level="info")
    if to_email:
        _send_email(f"Invoice {invoice_no}", msg, [to_email])


