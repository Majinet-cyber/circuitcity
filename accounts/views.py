# accounts/views.py
from __future__ import annotations

import logging
import random
from datetime import timedelta

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
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import get_template
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    AvatarForm,
    ForgotPasswordRequestForm,
    VerifyCodeResetForm,
    IdentifierLoginForm,      # allows email or username on login
    ProfileForm,              # Settings → Profile
    PasswordChangeSimpleForm, # Settings → Security
)
from .models import Profile, LoginSecurity, EmailOTP

log = logging.getLogger(__name__)
User = get_user_model()

# Single source of truth for the login template
LOGIN_TEMPLATE = "accounts/login.html"


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


# ----------------------------
# Template debugging utilities
# ----------------------------
def _debug_template_origin(tpl_name: str) -> str | None:
    """
    Resolve a template and print/log the physical file path Django will use.
    Returns the origin path (or None).
    """
    try:
        t = get_template(tpl_name)
        origin = getattr(t, "origin", None)
        path = getattr(origin, "name", str(origin)) if origin else "(unknown)"
        msg = f">> USING TEMPLATE {tpl_name}: {path}"
        print(msg)  # visible in runserver console
        log.debug(msg)
        return path
    except Exception as e:
        msg = f">> TEMPLATE RESOLVE ERROR for {tpl_name}: {e}"
        print(msg)
        log.error(msg)
        return None


# ----------------------------
# Login (renders HTML)
# ----------------------------
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Minimal login with staged lockouts:
      - 3 fails -> lock 5 minutes
      - then 2 fails -> lock 45 minutes
      - then 2 fails -> hard block (admin must unblock)
    Uses IdentifierLoginForm so users can enter email or username.
    """
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    # If already authenticated, don't show the form—go to next/dashboard.
    if request.user.is_authenticated:
        return redirect(next_url or getattr(settings, "LOGIN_REDIRECT_URL", "/"))

    # Always log which template we're about to use:
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
                resp = render(request, LOGIN_TEMPLATE, {"form": form, "next": next_url})
                if origin_path:
                    resp["X-Template-Origin"] = origin_path
                return resp
            if sec.is_locked():
                messages.error(request, generic_err)
                resp = render(request, LOGIN_TEMPLATE, {"form": form, "next": next_url})
                if origin_path:
                    resp["X-Template-Origin"] = origin_path
                return resp

        if user:
            auth_user = authenticate(request, username=user.username, password=password)
        else:
            auth_user = authenticate(request, username=identifier, password=password)

        if auth_user is not None and auth_user.is_active:
            sec, _ = LoginSecurity.objects.get_or_create(user=auth_user)
            sec.note_success()
            login(request, auth_user)
            return redirect(next_url or getattr(settings, "LOGIN_REDIRECT_URL", "/"))
        else:
            if user:
                sec, _ = LoginSecurity.objects.get_or_create(user=user)
                sec.note_failure()
            messages.error(request, generic_err)

    resp = render(request, LOGIN_TEMPLATE, {"form": form, "next": next_url})
    if origin_path:
        resp["X-Template-Origin"] = origin_path
    return resp


# ----------------------------
# Logout (accept GET or POST to avoid 405 locally)
# ----------------------------
@require_http_methods(["GET", "POST"])
def logout_get_or_post(request):
    """
    Ends the user session and redirects to the login page (or ?next=).
    Accepts GET for convenience in dev and simple “Logout” links.
    """
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
# Debug probe to confirm template origin
# ----------------------------
def login_template_probe(request):
    """
    DEBUG helper: Renders the same template but injects the resolved origin path
    so you can verify which file Django actually used.
    Visit: /accounts/login/_which/
    """
    if not settings.DEBUG:
        return HttpResponse("Not available when DEBUG=False.", status=404)

    origin = _debug_template_origin(LOGIN_TEMPLATE) or "(unknown origin)"
    ctx = {
        "form": IdentifierLoginForm(),
        "next": request.GET.get("next", ""),
    }

    # Render the normal page first
    html = render(request, LOGIN_TEMPLATE, ctx).content.decode("utf-8")

    # Small banner to show origin (tries to place after <body> or at top)
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
        from django.http import HttpResponseForbidden
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
# Forgot password: Step 1
# ----------------------------
@require_http_methods(["GET", "POST"])
def forgot_password_request_view(request):
    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = _get_user_by_identifier(form.cleaned_data["identifier"])
        if user and user.email:
            ip = _client_ip(request)
            code = _create_email_otp(user.email, purpose="reset", requester_ip=ip)
            if code:
                _send_email_otp(user.email, code, purpose="reset")

        messages.success(request, "If an account exists, we’ve emailed a reset code.")
        return redirect("accounts:forgot_password_reset")

    return render(request, "accounts/forgot_password_request.html", {"form": form})


# ----------------------------
# Forgot password: Step 2
# ----------------------------
@require_http_methods(["GET", "POST"])
def forgot_password_verify_view(request):
    form = VerifyCodeResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        user = _get_user_by_identifier(identifier)
        if not user or not user.email:
            messages.error(request, "Invalid code or identifier.")
            return redirect("accounts:forgot_password_reset")

        code = form.cleaned_data["code"]
        if not _verify_email_otp(user.email, code, purpose="reset"):
            messages.error(request, "Invalid or expired code.")
            return redirect("accounts:forgot_password_reset")

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
        return redirect(getattr(settings, "LOGIN_URL", "accounts:login"))

    return render(request, "accounts/forgot_password_reset.html", {"form": form})


# ----------------------------
# Admin: Unblock
# ----------------------------
@login_required
@require_POST
def admin_unblock_user_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        from django.http import HttpResponseForbidden
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
