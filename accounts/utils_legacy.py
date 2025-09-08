# accounts/utils.py
import secrets
from datetime import timedelta
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.conf import settings
from .models import PasswordResetOTP

def generate_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"

def can_send_otp(user) -> tuple[bool, str | None]:
    window_start = timezone.now() - timedelta(minutes=45)
    sent_count = PasswordResetOTP.objects.filter(user=user, created_at__gte=window_start).count()
    if sent_count >= 3:
        next_try = PasswordResetOTP.objects.filter(user=user).latest("created_at").created_at + timedelta(minutes=45)
        return False, f"Too many codes sent. Try again after {next_try.strftime('%H:%M')}."
    return True, None

def create_and_email_otp(user):
    ok, msg = can_send_otp(user)
    if not ok:
        return False, msg

    raw = generate_otp()
    PasswordResetOTP.objects.create(user=user, code_hash=make_password(raw))
    subject = "Your password reset code"
    body = (
        f"Hello {getattr(user, 'first_name', '') or 'there'},\n\n"
        f"Your Circuit City reset code is: {raw}\n"
        f"This code expires in 5 minutes.\n\n"
        "If you didn’t request this, you can ignore this email."
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [user.email], fail_silently=False)
    return True, "If that email exists, a code has been sent."
