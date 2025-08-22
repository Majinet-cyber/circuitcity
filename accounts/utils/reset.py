# accounts/utils/reset.py
from __future__ import annotations

import datetime
import logging
import secrets
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone

from ..models import PasswordResetCode

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Configurable knobs (fall back to sane defaults) ---
OTP_LENGTH = int(getattr(settings, "PASSWORD_RESET_OTP_LENGTH", 6))
OTP_TTL_MINUTES = int(getattr(settings, "PASSWORD_RESET_OTP_TTL_MINUTES", 15))
MAX_ATTEMPTS = int(getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", 5))


def _random_code(n: int = OTP_LENGTH) -> str:
    """Generate a numeric OTP using a cryptographically secure RNG."""
    return "".join(secrets.choice("0123456789") for _ in range(n))


def create_or_reuse_code(user: User, requester_ip: Optional[str] = None) -> str:
    """
    Issue a fresh one-time reset code for the user.
    - Invalidates any still-active codes.
    - Stores only a HASH of the code.
    - Returns the raw code (for emailing).
    """
    now = timezone.now()

    # Invalidate any other active codes to avoid multiple valid codes
    PasswordResetCode.objects.filter(
        user=user, used=False, expires_at__gt=now
    ).update(used=True)

    code = _random_code()
    code_hash = make_password(code)
    expires_at = now + datetime.timedelta(minutes=OTP_TTL_MINUTES)

    PasswordResetCode.objects.create(
        user=user,
        code_hash=code_hash,
        expires_at=expires_at,
        requester_ip=requester_ip,
    )

    try:
        logger.info("Issued password reset code", extra={"user_id": user.pk})
    except Exception:
        pass

    return code


def send_reset_code_email(user: User, code: str) -> None:
    """
    Email the OTP to the user's registered email.
    Uses DEFAULT_FROM_EMAIL or EMAIL_HOST_USER from settings; falls back to a neutral address.
    """
    app_name = getattr(settings, "APP_NAME", getattr(settings, "SITE_NAME", "Your App"))
    subject = f"{app_name}: Password reset code"

    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or "noreply@example.com"
    )

    body_txt = (
        f"Hi {user.get_username()},\n\n"
        f"Your password reset code is: {code}\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes.\n\n"
        "If you didn’t request this, you can ignore this email.\n"
    )

    body_html = (
        f"<p>Hi {user.get_username()},</p>"
        f"<p>Your password reset code is: "
        f"<strong style='font-size:18px; letter-spacing:2px;'>{code}</strong></p>"
        f"<p>This code expires in {OTP_TTL_MINUTES} minutes.</p>"
        "<p>If you didn’t request this, you can ignore this email.</p>"
    )

    send_mail(subject, body_txt, from_email, [user.email], html_message=body_html)


def verify_code_and_consume(user: User, code: str) -> bool:
    """
    Check the most recent active code for the user.
    - Returns True if the provided code matches and is within TTL.
    - Always increments attempts; on success marks 'used'.
    - On too many attempts, burns the code.
    """
    now = timezone.now()
    prc = (
        PasswordResetCode.objects.filter(
            user=user, used=False, expires_at__gt=now
        )
        .order_by("-created_at")
        .first()
    )
    if not prc:
        return False

    if prc.attempts >= MAX_ATTEMPTS:
        prc.used = True
        prc.save(update_fields=["used"])
        return False

    ok = check_password(code, prc.code_hash)

    prc.attempts += 1
    if ok:
        prc.used = True
    prc.save(update_fields=["attempts", "used"])

    # Best-effort: ensure no other codes remain active after success
    if ok:
        PasswordResetCode.objects.filter(user=user, used=False).update(used=True)

    return ok


def purge_expired_codes(older_than_minutes: int = 24 * 60) -> int:
    """
    Optional maintenance helper for a periodic job:
    Mark long-expired codes as used (idempotent).
    Returns number of codes updated.
    """
    cutoff = timezone.now() - datetime.timedelta(minutes=older_than_minutes)
    qs = PasswordResetCode.objects.filter(expires_at__lt=cutoff, used=False)
    return qs.update(used=True)
