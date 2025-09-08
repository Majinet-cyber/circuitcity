# accounts/utils.py
import hashlib
import secrets
import string
from datetime import timedelta
from django.utils import timezone

OTP_LEN = 6
OTP_TTL_MIN = 10        # minutes until expiration
OTP_MAX_ATTEMPTS = 5    # lock after this many wrong tries
RESEND_COOLDOWN_S = 60  # seconds between sends per email/purpose

def generate_otp(length: int = OTP_LEN) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))

def hash_code(code: str, email: str, purpose: str = "login") -> str:
    # Tie the hash to the email+purpose so a leaked code is useless elsewhere
    data = f"{code}:{email.lower()}:{purpose}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def expires_at(minutes: int = OTP_TTL_MIN):
    return timezone.now() + timedelta(minutes=minutes)
