# circuitcity/accounts/views.py
from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import quote_plus

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    get_user_model,
    update_session_auth_hash,
    authenticate,
    login,
    logout,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST
from django.middleware.csrf import get_token

from .forms import (
    AvatarForm,
    ForgotPasswordRequestForm,
    VerifyCodeResetForm,
    IdentifierLoginForm,
    ProfileForm,
    PasswordChangeSimpleForm,
    ManagerSignUpForm,
)
from .models import EmailOTP, LoginSecurity, Profile

# Optional tenants (graceful fallbacks if app not installed)
try:
    from tenants.models import Business, Membership  # type: ignore
except Exception:
    Business = None          # type: ignore
    Membership = None        # type: ignore

log = logging.getLogger(__name__)
User = get_user_model()

# ============================
# Templates (centralize names)
# ============================
LOGIN_TEMPLATE = "accounts/login.html"
FORGOT_REQUEST_TEMPLATE = "accounts/forgot_password_request.html"
FORGOT_RESET_TEMPLATE = "accounts/forgot_password_reset.html"
FORGOT_SENT_TEMPLATE = "accounts/forgot_password_sent.html"  # optional

# ----------------------------
# OTP config
# ----------------------------
OTP_SESSION_KEY = "otp_verified_at"
OTP_SESSION_UID = "otp_user_id"
OTP_WINDOW_MINUTES = int(getattr(settings, "OTP_WINDOW_MINUTES", 20))


# ----------------------------
# Helpers
# ----------------------------
def _client_ip(request) -> str | None:
    xfwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_by_identifier(identifier: str):
    ident = (identifier or "").strip()
    if not ident:
        return None

    # Prefer username exact (case-insensitive)
    try:
        return User.objects.get(username__iexact=ident)
    except User.DoesNotExist:
        pass
    except User.MultipleObjectsReturned:
        user = (
            User.objects.filter(username__iexact=ident)
            .order_by("-last_login", "-date_joined", "-id")
            .first()
        )
        if user:
            return user

    # Then email
    user = (
        User.objects.filter(email__iexact=ident)
        .order_by("-last_login", "-date_joined", "-id")
        .first()
    )
    return user


def _generate_otp(n: int = 6) -> str:
    return f"{random.randint(0, 10**n - 1):0{n}d}"


def _create_email_otp(email: str, *, purpose: str, requester_ip: str | None) -> str | None:
    if not email:
        return None
    now = timezone.now()
    window_start = now - timedelta(minutes=45)
    recent_count = EmailOTP.objects.filter(
        email__iexact=email, purpose=purpose, created_at__gte=window_start
    ).count()
    if recent_count >= 3:
        return None

    raw = _generate_otp(6)
    otp = EmailOTP(
        email=email.strip(),
        purpose=purpose,
        expires_at=now + timedelta(minutes=5),
        requester_ip=requester_ip,
        meta={"ua": "web"},
    )
    otp.set_raw_code(raw)
    otp.save()
    return raw


def _send_email_otp(email: str, code: str, *, purpose: str) -> None:
    subject = {
        "reset": "Your password reset code",
        "login": "Your login verification code",
        "verify": "Your verification code",
    }.get(purpose, "Your verification code")

    msg_lines = [
        "Use the one-time code below:",
        "",
        f"    {code}",
        "",
        "This code will expire in 5 minutes.",
        "If you didn’t request this, you can ignore this email.",
    ]
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost")
    send_mail(subject, "\n".join(msg_lines), from_email, [email], fail_silently=True)


def _verify_email_otp(email: str, code: str, *, purpose: str) -> bool:
    if not email or not code:
        return False

    candidates = EmailOTP.objects.filter(
        email__iexact=email,
        purpose=purpose,
        created_at__gte=timezone.now() - timedelta(hours=6),
    ).order_by("-created_at")[:10]

    for row in candidates:
        if row.consumed_at is not None or row.is_expired:
            continue
        if row.attempts >= 5:
            continue
        row.attempts += 1
        row.save(update_fields=["attempts"])

        if row.matches(code):
            row.consumed_at = timezone.now()
            row.save(update_fields=["consumed_at"])
            return True

    return False


def _mark_otp_verified(request) -> None:
    request.session[OTP_SESSION_KEY] = time.time()
    request.session[OTP_SESSION_UID] = request.user.id


def _otp_is_valid(request) -> bool:
    try:
        ts = float(request.session.get(OTP_SESSION_KEY, 0.0))
    except Exception:
        ts = 0.0
    uid = request.session.get(OTP_SESSION_UID)
    if not uid or uid != request.user.id or not ts:
        return False
    return (time.time() - ts) <= (OTP_WINDOW_MINUTES * 60)


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    name, domain = email.split("@", 1)
    if not name:
        return f"*@{domain}"
    return f"{name[0]}{'*' * max(0, len(name) - 1)}@{domain}"


def _get_or_create_manager_group() -> Group:
    return Group.objects.get_or_create(name="Manager")[0]


def _safe_redirect(*candidates: str, default: str = "/"):
    for c in candidates:
        if not c:
            continue
        if c.startswith("/"):
            return c
        try:
            return reverse(c)
        except NoReverseMatch:
            continue
    return default


# ----------------------------
# Two-factor links (safe if two_factor not installed)
# ----------------------------
def _twofa_links():
    enabled = getattr(settings, "ENABLE_2FA", False)
    manage_url = None
    status = "Disabled"

    if not enabled:
        return False, None, status

    try:
        try:
            manage_url = reverse("two_factor:profile")
        except Exception:
            manage_url = reverse("two_factor:setup")
        status = "Enabled"
    except Exception:
        manage_url = None
        status = "Enabled (app not installed)"

    return enabled, manage_url, status


# ============================
# Login (custom)
# ============================
@require_http_methods(["GET", "POST"])
def login_view(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.user.is_authenticated:
        return redirect(next_url or getattr(settings, "LOGIN_REDIRECT_URL", "/"))

    origin_path = _debug_template_origin(LOGIN_TEMPLATE)
    form = IdentifierLoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        password = form.cleaned_data["password"]

        user = _get_user_by_identifier(identifier)
        generic_err = "Invalid credentials or temporarily locked. Please try again."

        if user:
            sec, _ = LoginSecurity.objects.get_or_create(user=user)
            if sec.hard_blocked:
                messages.error(request, "This account is blocked. Contact an admin.")
                return _render_login(request, form, next_url, origin_path)
            if sec.is_locked():
                messages.error(request, generic_err)
                return _render_login(request, form, next_url, origin_path)

        auth_user = authenticate(
            request,
            username=(user.username if user else identifier),
            password=password,
        )

        if auth_user is not None and auth_user.is_active:
            sec, _ = LoginSecurity.objects.get_or_create(user=auth_user)
            sec.note_success()
            login(request, auth_user)
            return redirect(next_url or getattr(settings, "LOGIN_REDIRECT_URL", "/"))

        if user:
            sec, _ = LoginSecurity.objects.get_or_create(user=user)
            sec.note_failure()
        messages.error(request, generic_err)

    return _render_login(request, form, next_url, origin_path)


def _render_login(request, form, next_url, origin_path):
    try:
        resp = render(request, LOGIN_TEMPLATE, {"form": form, "next": next_url})
    except TemplateDoesNotExist:
        return _login_inline_fallback(request, form, next_url, origin_path)
    if origin_path:
        resp["X-Template-Origin"] = origin_path
    return resp


def _login_inline_fallback(request, form, next_url, origin_path):
    csrf_val = get_token(request)
    # Minimal inline login so production never 500s if template missing.
    html = f"""<!doctype html>
<meta charset="utf-8"><title>Login (Inline Fallback)</title>
<style>
  body{{font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;background:#f7fafc;margin:0;padding:24px}}
  .card{{max-width:520px;margin:24px auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}}
  label{{display:block;margin:.75rem 0 .35rem}}
  input{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:10px}}
  button{{margin-top:12px;padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#2563eb;color:#fff;cursor:pointer}}
  .note{{margin-top:10px;color:#0c4a6e;background:#ecfeff;border:1px solid #bae6fd;border-radius:10px;padding:10px}}
</style>
<div class="card">
  <h2>Circuit City — Inline Login</h2>
  <div class="note"><strong>Template used:</strong> {origin_path or "(missing)"}<br/>This is the emergency inline form.</div>
  <form method="post" action="{reverse('accounts:login')}">
    <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_val}">
    <input type="hidden" name="next" value="{next_url or ''}">
    <label for="id_identifier">Email or Username</label>
    <input id="id_identifier" name="identifier" type="text" autocomplete="username email" required>
    <label for="id_password">Password</label>
    <input id="id_password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
  </form>
</div>"""
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    if origin_path:
        resp["X-Template-Origin"] = origin_path
    return resp


# ----------------------------
# Logout (GET or POST)
# ----------------------------
@require_http_methods(["GET", "POST"])
def logout_get_or_post(request):
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or getattr(settings, "LOGOUT_REDIRECT_URL", None)
        or getattr(settings, "LOGIN_URL", "/accounts/login/")
    )
    try:
        logout(request)
    except Exception:
        pass
    return redirect(next_url)


# ----------------------------
# OTP challenge (email code)
# ----------------------------
@login_required
@require_http_methods(["GET", "POST"])
def otp_challenge(request):
    next_url = request.GET.get("next") or request.POST.get("next") or "/"

    if _otp_is_valid(request):
        return redirect(next_url)

    ctx = {
        "next": next_url,
        "email_masked": _mask_email(getattr(request.user, "email", "") or ""),
        "window_minutes": OTP_WINDOW_MINUTES,
        "sent": False,
    }

    if request.method == "POST":
        action = (request.POST.get("action") or "").lower()
        if action == "send":
            if not request.user.email:
                messages.error(request, "Your account has no email address; contact an admin.")
            else:
                code = _create_email_otp(
                    request.user.email,
                    purpose="verify",
                    requester_ip=_client_ip(request),
                )
                if code:
                    _send_email_otp(request.user.email, code, purpose="verify")
                    ctx["sent"] = True
                    messages.success(request, "We sent a verification code to your email.")
                else:
                    messages.error(request, "Too many code requests. Please try again later.")
        else:  # verify
            code = (request.POST.get("code") or "").strip()
            if not code:
                messages.error(request, "Enter the 6-digit code.")
            elif not request.user.email:
                messages.error(request, "Your account has no email address; contact an admin.")
            else:
                ok = _verify_email_otp(request.user.email, code, purpose="verify")
                if ok:
                    _mark_otp_verified(request)
                    messages.success(request, "Verified.")
                    return redirect(next_url)
                messages.error(request, "Invalid or expired code. Please try again.")

    try:
        return render(request, "accounts/otp_challenge.html", ctx)
    except TemplateDoesNotExist:
        html = f"""<!doctype html>
<meta charset="utf-8"><title>Verify</title>
<style>
  body{{font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;background:#f7fafc;margin:0;padding:24px}}
  .card{{max-width:520px;margin:24px auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}}
  .row{{display:flex;gap:8px;align-items:center}}
  input[type=text]{{padding:10px;border:1px solid #cbd5e1;border-radius:10px;flex:1}}
  button{{padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#0ea5e9;color:#fff;cursor:pointer}}
  .ghost{{background:#fff;color:#0f172a}}
</style>
<div class="card">
  <h2>Extra verification</h2>
  <p>We sent a 6-digit code to <strong>{ctx["email_masked"]}</strong> (valid {OTP_WINDOW_MINUTES} minutes after you verify).</p>
  <form method="post">
    <input type="hidden" name="next" value="{next_url}"/>
    <div class="row" style="margin:10px 0">
      <input name="code" placeholder="Enter code" inputmode="numeric" maxlength="6" />
      <button type="submit">Verify</button>
    </div>
    <button class="ghost" name="action" value="send" type="submit">Resend code</button>
  </form>
</div>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")


def otp_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
            return redirect(f"{login_url}?next={quote_plus(request.get_full_path())}")
        if _otp_is_valid(request):
            return view_func(request, *args, **kwargs)
        try:
            otp_url = reverse("accounts:otp_challenge")
        except Exception:
            otp_url = "/accounts/otp/"
        return redirect(f"{otp_url}?next={quote_plus(request.get_full_path())}")
    return _wrapped


# ----------------------------
# Debug probe to confirm template origin (only in DEBUG)
# ----------------------------
def login_template_probe(request):
    if not settings.DEBUG:
        return HttpResponse("Not available when DEBUG=False.", status=404)

    origin = _debug_template_origin(LOGIN_TEMPLATE) or "(unknown origin)"
    ctx = {"form": IdentifierLoginForm(), "next": request.GET.get("next", "")}

    try:
        html = render(request, LOGIN_TEMPLATE, ctx).content.decode("utf-8")
    except TemplateDoesNotExist:
        return _login_inline_fallback(request, IdentifierLoginForm(), request.GET.get("next", ""), origin)

    banner = f'''
    <div style="margin:10px 0;padding:10px 12px;border-radius:10px;
                background:#ecfeff;border:1px solid #bae6fd;color:#0c4a6e;
                font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;">
      <strong>Template Origin:</strong> {origin}
      <div>URL: /accounts/login/_which/ (debug probe)</div>
    </div>
    '''

    if "<main" in html:
        html = html.replace("<main", banner + "<main", 1)
    elif "<body" in html:
        html = html.replace(">", ">" + banner, 1)
    else:
        html = banner + html

    resp = HttpResponse(html)
    resp["Content-Type"] = "text/html; charset=utf-8"
    resp["X-Template-Origin"] = origin
    return resp


# ----------------------------
# Avatar upload (self)
# ----------------------------
@login_required
@require_POST
def upload_my_avatar(request):
    form = AvatarForm(request.POST, request.FILES)
    next_url = request.POST.get("next") or "/"
    if not form.is_valid():
        messages.error(request, "; ".join([e for errs in form.errors.values() for e in errs]))
        return redirect(next_url)

    f = form.cleaned_data["avatar"]
    profile = getattr(request.user, "profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=request.user)

    profile.avatar.save(f.name, f, save=True)
    messages.success(request, "Avatar updated.")
    return redirect(next_url)


# ----------------------------
# Avatar upload (by agent_id)
# ----------------------------
@login_required
@require_POST
def upload_agent_avatar(request, agent_id: int):
    next_url = request.POST.get("next") or "/"

    if not (request.user.is_superuser or request.user.is_staff or request.user.id == agent_id):
        return HttpResponseForbidden("Admins only.")
    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "; ".join([e for errs in form.errors.values() for e in errs]))
        return redirect(next_url)

    try:
        target = User.objects.get(pk=agent_id)
    except User.DoesNotExist:
        messages.error(request, "Agent not found.")
        return redirect(next_url)

    f = form.cleaned_data["avatar"]
    profile = getattr(target, "profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=target)

    profile.avatar.save(f.name, f, save=True)
    messages.success(request, "Agent avatar updated.")
    return redirect(next_url)


# ----------------------------
# Forgot password (2-step) with safe fallbacks
# ----------------------------
@require_http_methods(["GET", "POST"])
def forgot_password_request_view(request):
    """
    Step 1: Ask for identifier (email/username). Email a code *if* user exists.
    """
    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = _get_user_by_identifier(form.cleaned_data["identifier"])
        if user and user.email:
            ip = _client_ip(request)
            code = _create_email_otp(user.email, purpose="reset", requester_ip=ip)
            if code:
                _send_email_otp(user.email, code, purpose="reset")

        # Do not leak whether the account exists
        messages.success(request, "If an account exists, we’ve emailed a reset code.")
        try:
            return redirect("accounts:forgot_password_reset")
        except NoReverseMatch:
            return redirect("/accounts/password/reset/")

    # Render with fallback if template missing
    try:
        return render(request, FORGOT_REQUEST_TEMPLATE, {"form": form})
    except TemplateDoesNotExist:
        csrf_val = get_token(request)
        html = f"""<!doctype html>
<meta charset="utf-8"><title>Forgot password</title>
<style>
  body{{font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;background:#f7fafc;margin:0;padding:24px}}
  .card{{max-width:520px;margin:24px auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}}
  label{{display:block;margin:.75rem 0 .35rem}}
  input{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:10px}}
  button{{margin-top:12px;padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#0ea5e9;color:#fff;cursor:pointer}}
  a{{color:#2563eb;text-decoration:none}}
</style>
<div class="card">
  <h2>Forgot your password?</h2>
  <p>Enter your email/username. If we find a match, we will email a reset code.</p>
  <form method="post">
    <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_val}">
    <label for="id_identifier">Email or Username</label>
    <input id="id_identifier" name="identifier" required>
    <button type="submit">Send reset code</button>
  </form>
  <p style="margin-top:10px"><a href="{reverse('accounts:login')}">Back to sign in</a></p>
</div>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_http_methods(["GET", "POST"])
def forgot_password_verify_view(request):
    """
    Step 2: Verify code + set new password.
    """
    form = VerifyCodeResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        user = _get_user_by_identifier(identifier)
        if not user or not user.email:
            messages.error(request, "Invalid code or identifier.")
            try:
                return redirect("accounts:forgot_password_reset")
            except NoReverseMatch:
                return redirect("/accounts/password/reset/")

        code = form.cleaned_data["code"]
        if not _verify_email_otp(user.email, code, purpose="reset"):
            messages.error(request, "Invalid or expired code.")
            try:
                return redirect("accounts:forgot_password_reset")
            except NoReverseMatch:
                return redirect("/accounts/password/reset/")

        new_password = form.cleaned_data["new_password1"]
        user.set_password(new_password)
        user.save()

        sec, _ = LoginSecurity.objects.get_or_create(user=user)
        sec.note_success()

        try:
            update_session_auth_hash(request, user)
        except Exception:
            pass

        messages.success(request, "Password updated. You can now sign in.")
        try:
            return redirect("accounts:login")
        except NoReverseMatch:
            return redirect(getattr(settings, "LOGIN_URL", "/accounts/login/"))

    # Render with fallback if template missing
    try:
        return render(request, FORGOT_RESET_TEMPLATE, {"form": form})
    except TemplateDoesNotExist:
        csrf_val = get_token(request)
        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
        html = f"""<!doctype html>
<meta charset="utf-8"><title>Reset password</title>
<style>
  body{{font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;background:#f7fafc;margin:0;padding:24px}}
  .card{{max-width:520px;margin:24px auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}}
  label{{display:block;margin:.75rem 0 .35rem}}
  input{{width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:10px}}
  button{{margin-top:12px;padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#22c55e;color:#fff;cursor:pointer}}
  a{{color:#2563eb;text-decoration:none}}
</style>
<div class="card">
  <h2>Enter code & new password</h2>
  <form method="post">
    <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_val}">
    <label for="id_identifier">Email or Username</label>
    <input id="id_identifier" name="identifier" required>
    <label for="id_code">6-digit code</label>
    <input id="id_code" name="code" inputmode="numeric" maxlength="6" required>
    <label for="id_new_password1">New password</label>
    <input id="id_new_password1" name="new_password1" type="password" required>
    <label for="id_new_password2">Confirm new password</label>
    <input id="id_new_password2" name="new_password2" type="password" required>
    <button type="submit">Update password</button>
  </form>
  <p style="margin-top:10px"><a href="{login_url}">Back to sign in</a></p>
</div>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")


# ----------------------------
# Admin: Unblock
# ----------------------------
@login_required
@require_POST
def admin_unblock_user_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Admins only.")
    uid = request.POST.get("user_id")
    try:
        target = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        messages.error(request, "User not found.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    sec, _ = LoginSecurity.objects.get_or_create(user=target)
    sec.stage = 0
    sec.fail_count = 0
    sec.locked_until = None
    sec.hard_blocked = False
    sec.save(update_fields=["stage", "fail_count", "locked_until", "hard_blocked"])
    messages.success(request, f"{target} unblocked.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


# =========================================
# SETTINGS PAGES
# =========================================
@login_required
def settings_home(request):
    try:
        return redirect("accounts:settings_unified")
    except NoReverseMatch:
        return redirect("accounts:settings_profile")


@login_required
@require_http_methods(["GET", "POST"])
def settings_profile(request):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:settings_profile")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/settings_profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def settings_security(request):
    if request.method == "POST":
        form = PasswordChangeSimpleForm(request.POST, user=request.user)
        if form.is_valid():
            old = form.cleaned_data["old_password"]
            new1 = form.cleaned_data["new_password1"]
            if not request.user.check_password(old):
                messages.error(request, "Current password is incorrect.")
            else:
                request.user.set_password(new1)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password changed.")
                return redirect("accounts:settings_security")
    else:
        form = PasswordChangeSimpleForm(user=request.user)

    return render(request, "accounts/settings_security.html", {"form": form})


@login_required
def settings_sessions(request):
    user_sessions = []
    now = timezone.now()
    for s in Session.objects.filter(expire_date__gte=now):
        data = s.get_decoded()
        if str(request.user.pk) == str(data.get("_auth_user_id")):
            user_sessions.append(s)

    return render(request, "accounts/settings_sessions.html", {"sessions": user_sessions})


@login_required
@require_POST
def terminate_other_sessions(request):
    current_key = request.session.session_key
    now = timezone.now()
    killed = 0
    for s in Session.objects.filter(expire_date__gte=now):
        try:
            if s.session_key != current_key and str(request.user.pk) == str(s.get_decoded().get("_auth_user_id")):
                s.delete()
                killed += 1
        except Exception:
            continue

    if killed:
        messages.success(request, f"Terminated {killed} other session(s).")
    else:
        messages.info(request, "No other active sessions found.")
    return redirect("accounts:settings_sessions")


# ----------------------------
# Unified Settings
# ----------------------------
@login_required
def settings_unified(request):
    user = request.user
    full_name = user.get_full_name() or user.username
    twofa_enabled, twofa_manage_url, twofa_status = _twofa_links()

    try:
        change_pw_url = reverse("accounts:settings_security")
    except NoReverseMatch:
        try:
            change_pw_url = reverse("password_change")
        except NoReverseMatch:
            change_pw_url = None

    try:
        upload_avatar_url = reverse("accounts:upload_my_avatar")
    except NoReverseMatch:
        upload_avatar_url = None

    avatar_img_url = ""
    try:
        profile = getattr(user, "profile", None)
        if profile and getattr(profile, "avatar", None) and getattr(profile.avatar, "url", ""):
            avatar_img_url = profile.avatar.url
    except Exception:
        avatar_img_url = ""

    if not avatar_img_url:
        email = (user.email or "").strip().lower()
        if email:
            email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
            avatar_img_url = f"https://www.gravatar.com/avatar/{email_hash}?s=192&d=identicon"
        else:
            avatar_img_url = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="

    ctx = {
        "user_full_name": full_name,
        "user_username": user.username,
        "user_email": user.email,
        "avatar_img_url": avatar_img_url,
        "twofa_enabled": twofa_enabled,
        "twofa_status": twofa_status,
        "twofa_manage_url": twofa_manage_url,
        "change_password_url": change_pw_url,
        "upload_avatar_url": upload_avatar_url,
    }

    try:
        return render(request, "inventory/settings.html", ctx)
    except TemplateDoesNotExist:
        return render(
            request,
            "accounts/settings_profile.html",
            {"form": ProfileForm(instance=getattr(request.user, "profile", None))},
        )


# ---------- seeding for fresh tenants ----------
def _seed_defaults_for_business(biz) -> None:
    """
    Create minimal per-tenant objects so new managers see a ready UI.
    Tries inventory.Store and inventory.Warehouse if present.
    """
    try:
        Store = apps.get_model("inventory", "Store")
        Warehouse = apps.get_model("inventory", "Warehouse")
    except Exception:
        return

    store = Store.objects.filter(business=biz).order_by("id").first()
    if not store:
        store_kwargs = {"business": biz, "name": f"{biz.name} Store"}
        if hasattr(Store, "is_default"):
            store_kwargs["is_default"] = True
        store = Store.objects.create(**store_kwargs)

    wh = Warehouse.objects.filter(business=biz).order_by("id").first()
    if not wh:
        wh_kwargs = {"business": biz, "name": "Main Warehouse"}
        if hasattr(Warehouse, "store"):
            wh_kwargs["store"] = store
        if hasattr(Warehouse, "is_default"):
            wh_kwargs["is_default"] = True
        Warehouse.objects.create(**wh_kwargs)


# =========================================
# Manager sign-up (auto-tenant + auto-select, ACTIVE immediately)
# =========================================
@require_http_methods(["GET", "POST"])
def signup_manager(request):
    # If already signed in, just go to app
    if request.user.is_authenticated:
        return redirect(_safe_redirect("inventory:inventory_dashboard", "dashboard:home", default="/inventory/dashboard/"))

    form = ManagerSignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        full_name = form.cleaned_data["full_name"].strip()
        biz_name = form.cleaned_data["business_name"].strip()
        subdomain = (form.cleaned_data.get("subdomain") or "").strip().lower()
        password = form.cleaned_data["password1"]

        # Create user (username = email)
        user = User.objects.create_user(username=email, email=email, password=password)

        # Optional name split
        try:
            parts = full_name.split()
            user.first_name = parts[0]
            user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            user.save(update_fields=["first_name", "last_name"])
        except Exception:
            pass

        # Add to Manager group
        try:
            mgr_group = _get_or_create_manager_group()
            user.groups.add(mgr_group)
        except Exception:
            pass

        # Create ACTIVE business immediately
        biz = None
        if Business is not None:
            base = slugify(biz_name)[:40] or "store"
            unique = base
            i = 1
            while Business.objects.filter(slug=unique).exists():
                i += 1
                unique = f"{base}-{i}"

            bkwargs = {"name": biz_name, "slug": unique}
            if hasattr(Business, "created_by"):
                bkwargs["created_by"] = user
            if hasattr(Business, "subdomain") and subdomain:
                bkwargs["subdomain"] = subdomain
            if hasattr(Business, "status"):
                bkwargs["status"] = "ACTIVE"

            biz = Business.objects.create(**bkwargs)

            # Ensure membership MANAGER → ACTIVE
            try:
                if Membership is not None:
                    Membership.objects.update_or_create(
                        user=user,
                        business=biz,
                        defaults={"role": "MANAGER", "status": "ACTIVE"},
                    )
            except Exception:
                pass

            # Seed default Store/Warehouse
            _seed_defaults_for_business(biz)

        # Ensure Profile exists and flag as manager if field exists
        try:
            profile = getattr(user, "profile", None)
            if profile is None:
                profile, _ = Profile.objects.get_or_create(user=user)
            if hasattr(profile, "is_manager"):
                profile.is_manager = True
                profile.save(update_fields=["is_manager"])
        except Exception:
            pass

        # Auto-login and auto-select their biz in session
        login(request, user)
        if biz is not None:
            try:
                request.session[getattr(settings, "TENANT_SESSION_KEY", "active_business_id")] = biz.pk
            except Exception:
                pass
            messages.success(request, f"Welcome to {biz.name}! Your store is ready.")
        else:
            messages.success(request, "Your manager account is ready.")

        # Straight to the dashboard
        return redirect(_safe_redirect("inventory:inventory_dashboard", default="/inventory/dashboard/"))

    return render(request, "accounts/signup_manager.html", {"form": form})


# ----------------------------
# Template debugging utilities
# ----------------------------
def _debug_template_origin(tpl_name: str) -> str | None:
    try:
        t = get_template(tpl_name)
        origin = getattr(t, "origin", None)
        path = getattr(origin, "name", str(origin)) if origin else "(unknown)"
        msg = f">> USING TEMPLATE {tpl_name}: {path}"
        print(msg)
        log.debug(msg)
        return path
    except Exception as e:
        msg = f">> TEMPLATE RESOLVE ERROR for {tpl_name}: {e}"
        print(msg)
        log.error(msg)
        return None
