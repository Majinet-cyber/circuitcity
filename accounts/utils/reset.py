# accounts/utils/reset.py
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import PasswordResetCode


@dataclass
class ResetThrottle(Exception):
    """Raised when requests exceed the allowed window (3 per 45 minutes by default)."""
    message: str = "Too many reset codes requested. Please try again later."


def _generate_code() -> str:
    """Return a zero-padded 6-digit numeric code (string)."""
    return f"{secrets.randbelow(10**6):06d}"


def create_or_reuse_code(user, requester_ip: str | None = None) -> str:
    """
    Create a fresh OTP and store only its hash. Enforces:
      - Max N sends per window (default: 3 per 45 minutes)
      - Expiry TTL (default: 5 minutes)
    Note: since we store only a hash, we cannot "reuse" the raw code safely;
    we always create a new one (function name kept to match your existing imports).
    """
    ttl_seconds = int(getattr(settings, "ACCOUNTS_RESET_CODE_TTL_SECONDS", 5 * 60))
    window_minutes = int(getattr(settings, "ACCOUNTS_RESET_SEND_WINDOW_MINUTES", 45))
    max_sends = int(getattr(settings, "ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW", 3))

    now = timezone.now()
    window_start = now - timedelta(minutes=window_minutes)

    sends_in_window = PasswordResetCode.objects.filter(
        user=user,
        created_at__gte=window_start,
    ).count()
    if sends_in_window >= max_sends:
        # Raise a typed exception — your view swallows exceptions and still shows a neutral message
        raise ResetThrottle()

    # Create a brand-new code
    raw = _generate_code()
    expires_at = now + timedelta(seconds=ttl_seconds)

    rec = PasswordResetCode(
        user=user,
        expires_at=expires_at,
        requester_ip=requester_ip or None,
    )
    rec.set_raw_code(raw)  # stores hash
    rec.save()

    return raw


def send_reset_code_email(user, code: str) -> None:
    """
    Email the 6-digit code to the user's email.
    Uses HTML + plain-text alternative. If templates are missing, falls back to inline bodies.
    """
    if not user.email:
        # Nothing to send to; quietly no-op (view already uses neutral messaging)
        return

    app_name = getattr(settings, "APP_NAME", "Your App")
    ttl_seconds = int(getattr(settings, "ACCOUNTS_RESET_CODE_TTL_SECONDS", 5 * 60))
    ttl_minutes = max(1, ttl_seconds // 60)

    subject = f"{app_name}: {code} is your password reset code"
    context = {
        "app_name": app_name,
        "code": code,
        "ttl_minutes": ttl_minutes,
        "user": user,
    }

    # Try to render templates; fall back to inline content if missing
    try:
        html_body = render_to_string("email/password_reset_code.html", context)
        txt_body = render_to_string("email/password_reset_code.txt", context)
    except Exception:
        txt_body = (
            f"{app_name} password reset code: {code}\n\n"
            f"This code expires in {ttl_minutes} minutes.\n"
            "If you did not request this, you can ignore this email."
        )
        html_body = (
            f"<p style='font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif'>"
            f"<strong>{app_name}</strong> password reset code:</p>"
            f"<p style='font-size:24px;margin:.25rem 0 .75rem'><strong>{code}</strong></p>"
            f"<p style='color:#334155'>This code expires in {ttl_minutes} minutes.</p>"
            f"<p style='color:#64748b'>If you did not request this, you can ignore this email.</p>"
        )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    email = EmailMultiAlternatives(subject, txt_body, from_email, [user.email])
    email.attach_alternative(html_body, "text/html")
    # Let errors bubble up — your view already catches all exceptions and responds neutrally
    email.send(fail_silently=False)


def verify_code_and_consume(user, raw_code: str) -> bool:
    """
    Checks the most recent, unexpired, unused codes for a match.
    If matched, mark that code as used and return True; otherwise increment attempts and return False.
    """
    now = timezone.now()
    # Look at recent active codes only; newest first
    qs = PasswordResetCode.objects.filter(
        user=user,
        used=False,
        expires_at__gt=now,
    ).order_by("-created_at")

    for rec in qs:
        # Small guard to slow brute force on a single record
        max_attempts = 5
        if rec.attempts >= max_attempts:
            # Soft-disable this code by marking used once attempts exhausted
            rec.used = True
            rec.save(update_fields=["used"])
            continue

        if rec.matches(raw_code):
            rec.used = True
            rec.attempts = rec.attempts + 1
            rec.save(update_fields=["used", "attempts"])
            return True

        # Wrong code — bump attempts
        rec.attempts = rec.attempts + 1
        rec.save(update_fields=["attempts"])

    return False
