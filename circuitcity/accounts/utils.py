# accounts/utils.py
import hashlib
import secrets
import string
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import PermissionDenied

# -----------------------------
# OTP / Email Verification
# -----------------------------
OTP_LEN = 6
OTP_TTL_MIN = 10        # minutes until expiration
OTP_MAX_ATTEMPTS = 5    # lock after this many wrong tries
RESEND_COOLDOWN_S = 60  # seconds between sends per email/purpose

def generate_otp(length: int = OTP_LEN) -> str:
    """
    Generate a numeric OTP of given length.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))

def hash_code(code: str, email: str, purpose: str = "login") -> str:
    """
    Tie the OTP hash to the email + purpose so a leaked code
    is useless elsewhere.
    """
    data = f"{code}:{email.lower()}:{purpose}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def expires_at(minutes: int = OTP_TTL_MIN):
    """
    Return a timezone-aware datetime for OTP expiration.
    """
    return timezone.now() + timedelta(minutes=minutes)


# -----------------------------
# Role-based Access Helpers
# -----------------------------
def require_admin_or_manager(user):
    """
    Allow only admins (Django staff) and managers.
    Agents get a 403.
    """
    if not (user.is_authenticated and (user.is_staff or getattr(user.profile, "is_manager", False))):
        raise PermissionDenied("Admins and managers only.")


def require_agent(user):
    """
    Allow only agents (not staff, not managers).
    Admins or managers get a 403.
    """
    if not user.is_authenticated:
        raise PermissionDenied("Login required.")

    profile = getattr(user, "profile", None)
    if not profile:
        raise PermissionDenied("Profile missing.")

    if user.is_staff or profile.is_manager:
        raise PermissionDenied("Agents only.")


