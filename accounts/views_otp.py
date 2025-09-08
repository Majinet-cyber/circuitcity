# accounts/views_otp.py
import os, secrets, time
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone

User = get_user_model()

TTL = int(os.getenv("ACCOUNTS_RESET_CODE_TTL_SECONDS", "300"))
WINDOW_MIN = int(os.getenv("ACCOUNTS_RESET_SEND_WINDOW_MINUTES", "45"))
MAX_SENDS = int(os.getenv("ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW", "3"))

def _code_key(email):   return f"otp:reset:{email.lower()}"
def _count_key(email):  return f"otp:reset:{email.lower()}:win"
def _window_seconds():  return WINDOW_MIN * 60

def request_reset_code(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            messages.error(request, "Please enter your email.")
            return redirect("accounts:password_reset_code")

        # throttle: count sends in rolling window
        now = time.time()
        ck = _count_key(email)
        count, first_ts = cache.get(ck, (0, now))
        if now - first_ts > _window_seconds():
            count, first_ts = 0, now
        if count >= MAX_SENDS:
            messages.error(request, "Too many codes sent. Try again later.")
            return redirect("accounts:password_reset_code")
        cache.set(ck, (count + 1, first_ts), _window_seconds())

        code = f"{secrets.randbelow(10**6):06d}"
        cache.set(_code_key(email), code, TTL)

        send_mail(
            "Your Circuit City code",
            f"Your one-time code is {code}. It expires in {TTL//60} minutes.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        messages.success(request, f"We sent a code to {email}.")
        return redirect("accounts:password_reset_verify")
    return render(request, "accounts/password_reset_code.html")

def verify_reset_code(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        code  = request.POST.get("code", "").strip()
        newpw = request.POST.get("new_password", "").strip()

        cached = cache.get(_code_key(email))
        if not cached or cached != code:
            messages.error(request, "Invalid or expired code.")
            return redirect("accounts:password_reset_verify")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, "No account with that email.")
            return redirect("accounts:password_reset_verify")

        if len(newpw) < 12:
            messages.error(request, "Password must be at least 12 characters.")
            return redirect("accounts:password_reset_verify")

        user.password = make_password(newpw)
        user.last_login = timezone.now()
        user.save(update_fields=["password", "last_login"])
        cache.delete(_code_key(email))
        messages.success(request, "Password reset. You can now sign in.")
        return redirect("login")
    return render(request, "accounts/password_reset_verify.html")
