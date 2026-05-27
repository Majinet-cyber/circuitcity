"""
Email OTP service layer for secure OTP generation, storage, and verification.
Handles rate limiting, expiration, and attempt tracking.
"""
from __future__ import annotations

import secrets
import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import EmailOTP

User = get_user_model()
log = logging.getLogger(__name__)

# Configuration (read from env with safe defaults)
OTP_TTL_MINUTES = int(getattr(settings, "EMAIL_OTP_TTL_MINUTES", 10))
OTP_MAX_ATTEMPTS = int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))
OTP_RATE_LIMIT_PER_MINUTE = int(getattr(settings, "OTP_RATE_LIMIT_PER_MINUTE", 3))


def _normalize_email(email: str) -> str:
    """Normalize email to lowercase and strip whitespace."""
    return (email or "").strip().lower()


def _get_rate_limit_key(email: str, purpose: str) -> str:
    """Generate cache key for rate limiting."""
    normalized = _normalize_email(email)
    return f"otp_rl:{purpose}:{normalized}"


def _check_rate_limit(email: str, purpose: str) -> bool:
    """
    Check if email is rate-limited for the given purpose.
    Returns True if allowed, False if rate-limited.
    """
    key = _get_rate_limit_key(email, purpose)
    count = cache.get(key, 0)

    if count >= OTP_RATE_LIMIT_PER_MINUTE:
        log.warning(f"Rate limit exceeded for {email} purpose={purpose}")
        return False

    # Increment counter with 60 second expiry
    cache.set(key, count + 1, timeout=60)
    return True


def _generate_otp_code() -> str:
    """Generate a secure 6-digit OTP code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_otp_email(email: str, code: str, purpose: str, otp_id: int) -> None:
    """Send OTP code via email using notification system."""
    from notifications.services import emit_event
    from django.contrib.auth import get_user_model
    from django.db import transaction

    User = get_user_model()

    try:
        # Get user if exists
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass

        # Map purpose to event type
        event_type_map = {
            "reset": "OTP_RESET",
            "verify": "OTP_VERIFY",
            "signup": "OTP_CODE",
            "login": "OTP_CODE",
            "2fa": "OTP_CODE",
        }
        event_type = event_type_map.get(purpose, "OTP_CODE")

        # Send email via notification system with transaction.on_commit
        # This ensures email is sent after DB commit (OTP record is already saved)
        transaction.on_commit(
            lambda: emit_event(
                event_type=event_type,
                recipients=[email],
                dedupe_key=f"OTP:{purpose}:{email}:{otp_id}",
                payload={
                    "code": code,
                    "purpose": purpose,
                    "expires_minutes": OTP_TTL_MINUTES,
                },
                business=None,  # OTP not business-specific
                user=user,  # Pass user for preference checking (though transactional emails bypass preferences)
            )
        )
        log.info(f"OTP email queued for {email} for purpose={purpose} (event_type={event_type})")
    except Exception as e:
        log.error(f"Failed to queue OTP email to {email}: {e}", exc_info=True)
        raise


def request_email_otp(
    email: str,
    purpose: str,
    user: Optional[User] = None,
    request=None,
) -> None:
    """
    Request an email OTP for the given email and purpose.

    Args:
        email: Email address to send OTP to
        purpose: One of 'signup', 'login', 'reset', '2fa'
        user: Optional user instance (for signup, user may not exist yet)
        request: Optional request object (for IP/user_agent extraction)

    Raises:
        ValueError: If rate-limited or invalid purpose
    """
    if purpose not in ["signup", "login", "reset", "2fa"]:
        raise ValueError(f"Invalid purpose: {purpose}")

    normalized_email = _normalize_email(email)
    if not normalized_email:
        raise ValueError("Email is required")

    # Check rate limit
    if not _check_rate_limit(normalized_email, purpose):
        raise ValueError("Too many requests. Please try again later.")

    # Generate OTP
    code = _generate_otp_code()
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    # Extract IP and user agent from request if available
    requester_ip = None
    user_agent = None
    if request:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            requester_ip = x_forwarded_for.split(",")[0].strip()
        else:
            requester_ip = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]  # Limit length

    # Create OTP record
    otp = EmailOTP(
        email=normalized_email,
        user=user,
        purpose=purpose,
        expires_at=expires_at,
        requester_ip=requester_ip,
        user_agent=user_agent,
    )
    otp.set_raw_code(code)
    otp.save()

    # Send email via notification system
    _send_otp_email(normalized_email, code, purpose, otp.id)


def verify_email_otp(email: str, purpose: str, code: str) -> bool:
    """
    Verify an OTP code for the given email and purpose.

    In E2E_TESTING mode, accepts a fixed test code (default "000000") for bypass.

    Args:
        email: Email address
        purpose: Purpose of the OTP
        code: The 6-digit code to verify

    Returns:
        True if valid and consumed, False otherwise
    """
    normalized_email = _normalize_email(email)
    if not normalized_email or not code:
        return False

    # E2E Testing bypass: accept fixed test code if E2E_TESTING is enabled
    if getattr(settings, "E2E_TESTING", False) or getattr(settings, "DEBUG", False):
        test_code = getattr(settings, "E2E_OTP_CODE", "000000")
        if code == test_code:
            # Find any unconsumed OTP for this email/purpose and mark it as consumed
            now = timezone.now()
            otp = (
                EmailOTP.objects.filter(
                    email=normalized_email,
                    purpose=purpose,
                    consumed_at__isnull=True,
                    expires_at__gt=now,
                )
                .order_by("-created_at")
                .first()
            )
            if otp:
                otp.consumed_at = now
                otp.save(update_fields=["consumed_at"])
                log.info(f"E2E OTP bypass verified for {normalized_email} purpose={purpose}")
                return True

    # Find latest unconsumed, non-expired OTP for this email/purpose
    now = timezone.now()
    otp = (
        EmailOTP.objects.filter(
            email=normalized_email,
            purpose=purpose,
            consumed_at__isnull=True,
            expires_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )

    if not otp:
        log.warning(f"No valid OTP found for {normalized_email} purpose={purpose}")
        return False

    # Check attempt limit
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        log.warning(
            f"OTP attempt limit exceeded for {normalized_email} purpose={purpose} " f"(attempts={otp.attempts})"
        )
        return False

    # Increment attempts
    otp.attempts += 1
    otp.save(update_fields=["attempts"])

    # Verify code
    if otp.matches(code):
        # Mark as consumed
        otp.consumed_at = now
        otp.save(update_fields=["consumed_at"])
        log.info(f"OTP verified successfully for {normalized_email} purpose={purpose}")
        return True

    log.warning(f"Invalid OTP code for {normalized_email} purpose={purpose}")
    return False


def purge_expired_otps() -> int:
    """
    Delete expired OTPs older than 24 hours.
    Returns the number of deleted records.
    """
    cutoff = timezone.now() - timedelta(hours=24)
    deleted, _ = EmailOTP.objects.filter(expires_at__lt=cutoff).delete()
    log.info(f"Purged {deleted} expired OTP records")
    return deleted
