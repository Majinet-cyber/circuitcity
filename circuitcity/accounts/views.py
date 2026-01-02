# circuitcity/accounts/views.py
from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import quote_plus, urlencode

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
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token

from .forms import (
    AvatarForm,
    ForgotPasswordRequestForm,
    VerifyCodeResetForm,
    IdentifierLoginForm,
    ProfileForm,
    PasswordChangeSimpleForm,
    ManagerSignUpForm,
    WizardStep1Form,
    WizardStep2Form,
    WizardStep3Form,
    WizardStep4Form,
    ManagerWizardStep1Form,
    ManagerWizardStep2Form,
    ManagerWizardStep3Form,
    ManagerWizardStep4Form,
)
from .models import EmailOTP, LoginSecurity, Profile, OnboardingProfile
from .services.email_otp import request_email_otp, verify_email_otp

# Optional tenants (graceful fallbacks if app not installed)
try:
    from tenants.models import Business, Membership  # type: ignore
except Exception:
    Business = None  # type: ignore
    Membership = None  # type: ignore

log = logging.getLogger(__name__)
User = get_user_model()

# ============================
# Templates (centralize names)
# ============================
LOGIN_TEMPLATE = "accounts/login.html"
FORGOT_REQUEST_TEMPLATE = "accounts/forgot_password_request.html"
FORGOT_RESET_TEMPLATE = "accounts/forgot_password_reset.html"
FORGOT_SENT_TEMPLATE = "accounts/forgot_password_sent.html"  # optional
SIGNUP_MANAGER_TEMPLATE = "accounts/signup_manager.html"

# ----------------------------
# OTP config
# ----------------------------
OTP_SESSION_KEY = "otp_verified_at"
OTP_SESSION_UID = "otp_user_id"
OTP_WINDOW_MINUTES = int(getattr(settings, "OTP_WINDOW_MINUTES", 20))

# PRG helper: remember what user typed after failed login
LOGIN_IDENTIFIER_SESSION_KEY = "login_identifier"

# Tenant session key (used by middleware in this project)
TENANT_SESSION_KEY = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")


# ----------------------------
# Helpers
# ----------------------------
def _agree_flag(request) -> bool:
    """
    Safely infer the 'agree' checkbox state without touching QueryDict in templates.
    """
    return bool(request.GET.get("agree") or request.POST.get("agree"))


# --- Product Create (business-aware page) ------------------------------------
def _infer_product_mode(business) -> str:
    """
    Decide which product vertical the tenant is using.
    We check several common attributes defensively.
    Returns one of: "phones", "liquor", "pharmacy", "grocery", "generic".
    """
    val = None
    for attr in ("vertical", "category", "industry", "type", "kind", "sector"):
        v = getattr(business, attr, None)
        if isinstance(v, str) and v.strip():
            val = v.strip().lower()
            break

    if not val:
        return "generic"

    if val in {"phone", "phones", "mobile", "mobiles", "electronics"}:
        return "phones"
    if val in {"liquor", "bar", "alcohol", "pub", "bottle-store", "bottle store"}:
        return "liquor"
    if val in {"pharmacy", "medicine", "chemist", "drugstore"}:
        return "pharmacy"
    if val in {"grocery", "groceries", "supermarket", "retail"}:
        return "grocery"
    return "generic"


def _current_business_from_request(request):
    """
    Try common places the active business is stored by middleware.
    Adjust if your project uses a different attribute.
    """
    return (
        getattr(request, "business", None)
        or getattr(request, "active_business", None)
        or getattr(getattr(request, "user", None), "business", None)
        or getattr(getattr(request, "tenant", None), "business", None)
    )


def merch_product_create(request):
    """
    Plain page view that renders templates/inventory/product_create.html
    with PRODUCT_MODE in the context so the template can show the right form
    (phones vs liquor vs pharmacy vs generic).
    """
    business = _current_business_from_request(request)
    product_mode = _infer_product_mode(business)

    context = {
        "PRODUCT_MODE": product_mode,  # use in the template
        "business": business,
    }
    return render(request, "inventory/product_create.html", context)


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
        user = User.objects.filter(username__iexact=ident).order_by("-last_login", "-date_joined", "-id").first()
        if user:
            return user

    # Then email
    user = User.objects.filter(email__iexact=ident).order_by("-last_login", "-date_joined", "-id").first()
    return user


def _generate_otp(n: int = 6) -> str:
    return f"{random.randint(0, 10**n - 1):0{n}d}"


def _create_email_otp(
    email: str, *, purpose: str, requester_ip: str | None, user_agent: str | None = None
) -> str | None:
    if not email:
        return None
    now = timezone.now()
    # Rate limit: max 3 OTP requests per email per 10 minutes
    window_start = now - timedelta(minutes=10)
    recent_count = EmailOTP.objects.filter(email__iexact=email, purpose=purpose, created_at__gte=window_start).count()
    if recent_count >= 3:
        return None

    raw = _generate_otp(6)
    otp_ttl_minutes = int(getattr(settings, "EMAIL_OTP_TTL_MINUTES", 10))
    otp = EmailOTP(
        email=email.strip().lower(),
        purpose=purpose,
        expires_at=now + timedelta(minutes=otp_ttl_minutes),
        requester_ip=requester_ip,
        user_agent=user_agent or "web",
    )
    otp.set_raw_code(raw)
    otp.save()
    return raw


def _send_email_otp(email: str, code: str, *, purpose: str, otp_id: int | None = None) -> None:
    """
    Send OTP email via notifications emailer and create NotificationEvent.
    Uses transaction.on_commit to ensure email is sent after DB commit.
    """
    from django.db import transaction
    from notifications.services import emit_event

    subject = {
        "reset": "Your password reset code",
        "login": "Your login verification code",
        "verify": "Your verification code",
    }.get(purpose, "Your verification code")

    # Create NotificationEvent and send email after commit
    def _send_after_commit():
        otp_ttl_minutes = int(getattr(settings, "EMAIL_OTP_TTL_MINUTES", 10))
        try:
            emit_event(
                event_type="OTP_CODE",
                recipients=[email],
                dedupe_key=f"OTP:{purpose}:{email}:{otp_id}" if otp_id else f"OTP:{purpose}:{email}",
                payload={
                    "code": code,
                    "purpose": purpose,
                    "expires_in_minutes": otp_ttl_minutes,
                },
                business=None,
            )
        except Exception as e:
            # Log error but don't crash - email sending failures should be handled gracefully
            log.error(f"Failed to send OTP email via NotificationEvent: {e}", exc_info=True)
            # Fallback to direct send_mail if NotificationEvent fails
            try:
                from django.core.mail import send_mail

                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost")
                msg_lines = [
                    "Use the one-time code below:",
                    "",
                    f"    {code}",
                    "",
                    f"This code will expire in {otp_ttl_minutes} minutes.",
                    "If you didn't request this, you can ignore this email.",
                ]
                send_mail(subject, "\n".join(msg_lines), from_email, [email], fail_silently=True)
            except Exception as fallback_error:
                log.error(f"Fallback email send also failed: {fallback_error}", exc_info=True)

    transaction.on_commit(_send_after_commit)


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


def _no_store(resp: HttpResponse) -> HttpResponse:
    """
    Ensure browsers won't cache form pages (avoids stale CSRF + resubmission issues).
    """
    resp["Cache-Control"] = "no-store"
    return resp


def _post_login_url(request=None) -> str:
    """
    Best-effort landing page after successful login.

    CRITICAL: Always redirect to vertical dashboard (NOT analytics/insights).
    Routes by business_kind: phones → phones dashboard, liquor → liquor dashboard, etc.
    """
    # If we have a request with an active business, route to vertical dashboard
    if request:
        business = getattr(request, "business", None)
        if not business:
            # Try to get from session
            try:
                from tenants.models import Business

                business_id = request.session.get("active_business_id")
                if business_id:
                    business = Business.objects.filter(id=business_id).first()
            except Exception:
                pass

        # Redirect to vertical-specific dashboard based on business_kind
        if business:
            try:
                from inventory.business_kinds import BusinessKind

                business_kind = getattr(business, "business_kind", None)

                # Map business_kind to vertical dashboard
                vertical_routes = {
                    BusinessKind.PHONES: "inventory_verticals:phones_dashboard",
                    "phones": "inventory_verticals:phones_dashboard",
                    BusinessKind.LIQUOR: "inventory_verticals:liquor_dashboard",
                    "liquor": "inventory_verticals:liquor_dashboard",
                    BusinessKind.CLOTHING: "inventory_verticals:clothing_dashboard",
                    "clothing": "inventory_verticals:clothing_dashboard",
                    BusinessKind.PHARMACY: "inventory_verticals:pharmacy_dashboard",
                    "pharmacy": "inventory_verticals:pharmacy_dashboard",
                    BusinessKind.GYM: "inventory_verticals:gym_dashboard",
                    "gym": "inventory_verticals:gym_dashboard",
                    BusinessKind.GROCERY: "groceries:dashboard",
                    "grocery": "groceries:dashboard",
                    "groceries": "groceries:dashboard",
                }

                route = vertical_routes.get(business_kind)
                if route:
                    try:
                        return reverse(route)
                    except NoReverseMatch:
                        pass
            except Exception:
                pass

    # Fallback: try generic dashboard routes (NOT analytics)
    for name in (
        "dashboard:home",
        "dashboard:dashboard_home",
        "inventory:inventory_dashboard",
        "inventory:dashboard",
        "inventory:stock_list",
    ):
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/inventory/dashboard/"


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


# ----------------------------
# Active business selection (no 'is_active' field assumptions)
# ----------------------------
def _select_active_business_for_user(request, user) -> None:
    """
    Best-effort: if the user has exactly one membership, store it in session.
    Avoids filtering by non-existent fields like 'is_active'.
    """
    if Membership is None:
        return
    try:
        qs = Membership.objects.filter(user=user)
        # If the model has 'status', prefer ACTIVE ones
        if hasattr(Membership, "status"):
            try:
                qs = qs.filter(status="ACTIVE")
            except Exception:
                pass
        m = qs.select_related("business").order_by("id")
        if m.count() == 1:
            request.session[TENANT_SESSION_KEY] = m.first().business_id  # type: ignore[attr-defined]
    except Exception:
        # never break login flow
        pass


# ============================
# Login (PRG with messages)
# ============================
@ensure_csrf_cookie
@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Implements PRG (Post -> Redirect -> Get) so refresh/back never re-POSTs.
    Shows clear error messages and repopulates identifier after a failed attempt.
    """
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.user.is_authenticated:
        return redirect(next_url or _post_login_url(request))

    origin_path = _debug_template_origin(LOGIN_TEMPLATE)

    if request.method == "POST":
        form = IdentifierLoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]
            password = form.cleaned_data["password"]

            user = _get_user_by_identifier(identifier)
            generic_err = "Invalid email/username or password."

            if user:
                sec, _ = LoginSecurity.objects.get_or_create(user=user)
                if sec.hard_blocked:
                    messages.error(request, "This account is blocked. Contact an admin.")
                    request.session[LOGIN_IDENTIFIER_SESSION_KEY] = identifier
                    return _redirect_back_to_login(next_url)
                if sec.is_locked():
                    messages.error(request, generic_err)
                    request.session[LOGIN_IDENTIFIER_SESSION_KEY] = identifier
                    return _redirect_back_to_login(next_url)

            auth_user = authenticate(
                request,
                username=(user.username if user else identifier),
                password=password,
            )

            if auth_user is not None and auth_user.is_active:
                sec, _ = LoginSecurity.objects.get_or_create(user=auth_user)
                sec.note_success()
                login(request, auth_user)

                # Pick an active business for the session if possible
                _select_active_business_for_user(request, auth_user)

                # Check if SMS 2FA is enabled for this user
                from .models import is_twofa_enabled

                if is_twofa_enabled(auth_user):
                    # Set session flags for 2FA challenge
                    request.session["twofa_required"] = True
                    request.session["twofa_passed"] = False

                    # Redirect to 2FA challenge page
                    from django.urls import reverse

                    challenge_url = reverse("accounts:twofa_challenge")
                    if next_url:
                        challenge_url += f"?next={next_url}"
                    return redirect(challenge_url)

                return redirect(next_url or _post_login_url(request))

            if user:
                sec, _ = LoginSecurity.objects.get_or_create(user=user)
                sec.note_failure()

            messages.error(request, generic_err)
            request.session[LOGIN_IDENTIFIER_SESSION_KEY] = identifier
            return _redirect_back_to_login(next_url)

        # Form invalid — still PRG for clean refresh
        messages.error(request, "Please correct the errors and try again.")
        request.session[LOGIN_IDENTIFIER_SESSION_KEY] = request.POST.get("identifier", "")
        return _redirect_back_to_login(next_url)

    # GET — build unbound form and prefill identifier from session after PRG
    form = IdentifierLoginForm()
    remembered = request.session.pop(LOGIN_IDENTIFIER_SESSION_KEY, "")
    if remembered:
        form.fields["identifier"].initial = remembered

    return _render_login(request, form, next_url, origin_path)


def _redirect_back_to_login(next_url: str):
    url = reverse("accounts:login")
    q = {}
    if next_url:
        q["next"] = next_url
    if q:
        url += f"?{urlencode(q)}"
    return redirect(url)


def _render_login(request, form, next_url, origin_path):
    try:
        resp = render(request, LOGIN_TEMPLATE, {"form": form, "next": next_url})
    except TemplateDoesNotExist:
        return _login_inline_fallback(request, form, next_url, origin_path)
    if origin_path:
        resp["X-Template-Origin"] = origin_path
    return _no_store(resp)


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
    return _no_store(resp)


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
                ip = _client_ip(request)
                user_agent = request.META.get("HTTP_USER_AGENT", "web")[:500]
                code = _create_email_otp(
                    request.user.email,
                    purpose="verify",
                    requester_ip=ip,
                    user_agent=user_agent,
                )
                if code:
                    # Get the OTP record ID for NotificationEvent dedupe_key
                    otp_record = (
                        EmailOTP.objects.filter(email__iexact=request.user.email, purpose="verify")
                        .order_by("-created_at")
                        .first()
                    )
                    otp_id = otp_record.id if otp_record else None
                    _send_email_otp(request.user.email, code, purpose="verify", otp_id=otp_id)
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

    banner = f"""
    <div style="margin:10px 0;padding:10px 12px;border-radius:10px;
                background:#ecfeff;border:1px solid #bae6fd;color:#0c4a6e;
                font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;">
      <strong>Template Origin:</strong> {origin}
      <div>URL: /accounts/login/_which/ (debug probe)</div>
    </div>
    """

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
@never_cache
@require_http_methods(["GET", "POST"])
def forgot_password_request_view(request):
    """
    Step 1: Ask for identifier (email/username). Email a code *if* user exists.
    Transaction-safe: OTP creation and email sending happen after DB commit.
    """
    from django.db import transaction
    from notifications.services import emit_event

    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = _get_user_by_identifier(form.cleaned_data["identifier"])
            if user and user.email:
                ip = _client_ip(request)
                user_agent = request.META.get("HTTP_USER_AGENT", "web")[:500]  # Limit length
                code = _create_email_otp(user.email, purpose="reset", requester_ip=ip, user_agent=user_agent)
                if code:
                    # Get the OTP record ID for NotificationEvent dedupe_key
                    otp_record = (
                        EmailOTP.objects.filter(email__iexact=user.email, purpose="reset")
                        .order_by("-created_at")
                        .first()
                    )
                    otp_id = otp_record.id if otp_record else None

                    # Send OTP via emit_event with transaction.on_commit
                    # This ensures NotificationEvent is created and email is sent after DB commit
                    otp_ttl_minutes = int(getattr(settings, "EMAIL_OTP_TTL_MINUTES", 10))
                    transaction.on_commit(
                        lambda: emit_event(
                            event_type="OTP_RESET",
                            recipients=[user.email],
                            dedupe_key=f"OTP_RESET:{user.email}:{otp_id}" if otp_id else f"OTP_RESET:{user.email}",
                            payload={
                                "code": code,
                                "purpose": "reset",
                                "expires_in_minutes": otp_ttl_minutes,
                            },
                            business=None,
                            user=user,
                        )
                    )
        except Exception as e:
            # Log error but show generic success message (don't reveal if user exists)
            log.error(f"Error in forgot password request: {e}", exc_info=True)

        # Do not leak whether the account exists - always show success
        messages.success(request, "If an account exists, we've emailed a reset code.")
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


@never_cache
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
        # Prevent reusing the same password
        if user.check_password(new_password):
            messages.error(request, "New password cannot be the same as your old password.")
            try:
                return redirect("accounts:forgot_password_reset")
            except NoReverseMatch:
                return redirect("/accounts/password/reset/")

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
@require_http_methods(["POST"])
def settings_currency(request):
    """
    Quick currency switcher endpoint.
    Accepts POST with 'currency' parameter ('MWK' or 'USD').
    Returns JSON response or redirects back.
    """
    from django.http import JsonResponse

    currency = request.POST.get("currency", "").upper().strip()
    if currency not in ["MWK", "USD"]:
        if request.headers.get("Accept", "").startswith("application/json"):
            return JsonResponse({"error": "Invalid currency"}, status=400)
        messages.error(request, "Invalid currency selection.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    profile = getattr(request.user, "profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=request.user)

    profile.display_currency = currency
    profile.save(update_fields=["display_currency"])

    if request.headers.get("Accept", "").startswith("application/json"):
        return JsonResponse({"success": True, "currency": currency})

    messages.success(request, f"Display currency set to {currency}.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


def _inject_sms_twofa_context(request, context):
    """
    Inject SMS 2FA context variables for the _twofa_sms_card.html partial.
    Safe to call even if imports fail - will set twofa_available=False.

    Adds to context:
    - twofa_available (bool): Whether Twilio Verify is enabled
    - twofa_sms_enabled (bool): Whether user has SMS 2FA enabled
    - twofa_phone_masked (str): Masked phone number or empty string
    - twofa_enable_pending (bool): Whether enable OTP verification is pending
    - twofa_disable_pending (bool): Whether disable OTP verification is pending
    - twofa_pending_phone_masked (str): Masked pending phone during enable flow
    """
    try:
        from django.conf import settings as dj_settings
        from .models import UserTwoFactor

        # Try to import mask_phone from templatetags, fallback to models
        try:
            from .templatetags.account_extras import mask_phone
        except Exception:
            try:
                from .models import mask_phone
            except Exception:
                # Fallback mask_phone implementation
                def mask_phone(phone_e164):
                    if not phone_e164 or len(phone_e164) < 7:
                        return phone_e164
                    if phone_e164.startswith("+"):
                        visible_start = phone_e164[:5] if len(phone_e164) > 8 else phone_e164[:4]
                        visible_end = phone_e164[-3:]
                        masked_middle = "*" * (len(phone_e164) - len(visible_start) - len(visible_end))
                        return f"{visible_start}{masked_middle}{visible_end}"
                    return phone_e164

        tf, _ = UserTwoFactor.objects.get_or_create(user=request.user)
        context["twofa_available"] = bool(getattr(dj_settings, "TWILIO_VERIFY_ENABLED", False))
        context["twofa_sms_enabled"] = bool(tf.sms_enabled)
        context["twofa_phone_masked"] = mask_phone(tf.phone_e164) if tf.phone_e164 else ""

        # Session flags for pending enable/disable flows
        context["twofa_enable_pending"] = bool(request.session.get("twofa_enable_flow"))
        context["twofa_disable_pending"] = bool(request.session.get("twofa_disable_flow"))

        # Masked pending phone for enable flow
        pending_phone = request.session.get("twofa_pending_phone", "")
        context["twofa_pending_phone_masked"] = mask_phone(pending_phone) if pending_phone else ""

    except Exception as e:
        # Fail safe: set unavailable
        logger.warning(f"Failed to inject SMS 2FA context: {e}")
        context["twofa_available"] = False
        context["twofa_sms_enabled"] = False
        context["twofa_phone_masked"] = ""
        context["twofa_enable_pending"] = False
        context["twofa_disable_pending"] = False
        context["twofa_pending_phone_masked"] = ""

    return context


@login_required
@require_http_methods(["GET", "POST"])
def settings_security(request):
    """
    Security settings page: password change and 2FA management.
    Password change requires recent 2FA if enabled.
    """
    from .models import get_or_create_twofactor, is_twofa_enabled
    from django.conf import settings as django_settings

    # Get user's 2FA settings
    tf = get_or_create_twofactor(request.user)

    if request.method == "POST":
        # Check if this is a password change request (requires recent 2FA)
        if "old_password" in request.POST:
            # Apply step-up auth for password changes
            if is_twofa_enabled(request.user):
                from .models import is_twofa_recent

                if not is_twofa_recent(request, max_age_seconds=1800):
                    # Redirect to 2FA challenge
                    from django.urls import reverse

                    challenge_url = reverse("accounts:twofa_challenge")
                    next_url = request.get_full_path()
                    return redirect(f"{challenge_url}?next={next_url}")

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

    context = {
        "form": form,
        "twofactor": tf,
        "settings": django_settings,
    }

    # Inject SMS 2FA context for _twofa_sms_card.html partial
    context = _inject_sms_twofa_context(request, context)

    return render(request, "accounts/settings_security.html", context)


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
@require_http_methods(["GET", "POST"])
def settings_danger_zone(request):
    """
    Danger zone page for resetting business account.
    Only accessible to business owners/managers.
    """
    from tenants.scope import get_active_business, get_membership

    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business found.")
        return redirect("accounts:settings_profile")

    # Check if user is manager/owner
    membership = get_membership(request.user, business)
    if not membership or membership.role != "MANAGER" or membership.status != "ACTIVE":
        if not request.user.is_superuser:
            messages.error(request, "Only business owners can reset account data.")
            return redirect("accounts:settings_profile")

    if request.method == "POST":
        # Validate confirmation inputs
        reset_text = request.POST.get("reset_text", "").strip().upper()
        business_name = request.POST.get("business_name", "").strip()
        password = request.POST.get("password", "")
        keep_catalog = request.POST.get("keep_catalog") == "on"

        # Validation
        if reset_text != "RESET":
            messages.error(request, "You must type 'RESET' to confirm.")
            return render(
                request,
                "accounts/settings_danger_zone.html",
                {
                    "business": business,
                },
            )

        # Check business name (last 4 chars of business ID or full name)
        business_id_last4 = str(business.id)[-4:]
        if business_name != business.name and business_name != business_id_last4:
            messages.error(
                request, f"Business name must match '{business.name}' or last 4 digits of ID: {business_id_last4}"
            )
            return render(
                request,
                "accounts/settings_danger_zone.html",
                {
                    "business": business,
                },
            )

        # Verify password
        if not request.user.check_password(password):
            messages.error(request, "Password is incorrect.")
            return render(
                request,
                "accounts/settings_danger_zone.html",
                {
                    "business": business,
                },
            )

        # Perform reset
        try:
            from tenants.services.reset_business import reset_business_data

            deleted_counts = reset_business_data(
                business,
                initiated_by=request.user,
                keep_catalog=keep_catalog,
            )

            total_deleted = sum(deleted_counts.values())
            messages.success(
                request,
                f"Business data reset successfully. Deleted {total_deleted} records across {len(deleted_counts)} models.",
            )

            # Redirect to dashboard or home
            return redirect("dashboard:home")

        except PermissionError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f"Failed to reset business {business.id}: {e}")
            messages.error(request, "Reset failed. Nothing was deleted. Please contact support if this persists.")

    return render(
        request,
        "accounts/settings_danger_zone.html",
        {
            "business": business,
        },
    )


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

    # Inject SMS 2FA context for _twofa_sms_card.html partial
    ctx = _inject_sms_twofa_context(request, ctx)

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
    For phone businesses, also seeds default phone products and accessories.
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

    # Seed phone products and accessories for phone businesses
    business_kind = getattr(biz, "business_kind", "").lower()
    if business_kind in ("phones", "phone", "electronics", "mobile", "mobiles"):
        try:
            from django.core.management import call_command

            call_command("seed_default_phone_products", business_id=biz.id, verbosity=0)
        except Exception as e:
            log.warning(f"Failed to seed phone products for {biz.name}: {e}")

        # Also seed accessories for phone businesses
        try:
            from django.core.management import call_command

            call_command("seed_accessories", business=biz.id, verbosity=0)
        except Exception as e:
            log.warning(f"Failed to seed accessories for {biz.name}: {e}")


# =========================================
# Manager sign-up WIZARD (4 steps, auto-tenant + auto-select, ACTIVE immediately)
# =========================================
MANAGER_WIZARD_SESSION_KEY = "manager_wizard_data"


def _get_manager_wizard_data(request):
    """Get manager wizard data from session"""
    return request.session.get(MANAGER_WIZARD_SESSION_KEY, {})


def _set_manager_wizard_data(request, data):
    """Save manager wizard data to session"""
    request.session[MANAGER_WIZARD_SESSION_KEY] = data
    request.session.modified = True


def _clear_manager_wizard_data(request):
    """Clear manager wizard data from session"""
    if MANAGER_WIZARD_SESSION_KEY in request.session:
        del request.session[MANAGER_WIZARD_SESSION_KEY]
        request.session.modified = True


@ensure_csrf_cookie
@never_cache
@require_http_methods(["GET", "POST"])
def signup_manager(request):
    """
    4-step wizard for manager signup:
    Step 1: Account (email, full name, password)
    Step 2: Store basics (business name, type, subdomain)
    Step 3: Brand (logo upload)
    Step 4: Review & Create
    """
    # If already signed in, just go to app
    if request.user.is_authenticated:
        return redirect(
            _safe_redirect("inventory:inventory_dashboard", "dashboard:home", default="/inventory/dashboard/")
        )

    # Determine current step from query param or POST
    step = int(request.GET.get("step", request.POST.get("step", 1)))
    if step < 1 or step > 4:
        step = 1

    wizard_data = _get_manager_wizard_data(request)

    # Step 1: Account
    if step == 1:
        form = ManagerWizardStep1Form(request.POST or None, initial=wizard_data.get("step1", {}))
        if request.method == "POST":
            action = request.POST.get("action", "next")
            if action == "next" and form.is_valid():
                wizard_data["step1"] = form.cleaned_data
                _set_manager_wizard_data(request, wizard_data)
                return redirect(f"{reverse('accounts:signup_manager')}?step=2")
        return render(
            request,
            "accounts/signup_manager_wizard_step1.html",
            {
                "form": form,
                "step": step,
                "total_steps": 4,
                "wizard_data": wizard_data,
            },
        )

    # Step 2: Store basics
    elif step == 2:
        # Must have completed step 1
        if "step1" not in wizard_data:
            return redirect(f"{reverse('accounts:signup_manager')}?step=1")

        form = ManagerWizardStep2Form(request.POST or None, initial=wizard_data.get("step2", {}))
        if request.method == "POST":
            action = request.POST.get("action", "next")
            if action == "back":
                return redirect(f"{reverse('accounts:signup_manager')}?step=1")
            elif action == "next" and form.is_valid():
                wizard_data["step2"] = form.cleaned_data
                _set_manager_wizard_data(request, wizard_data)
                return redirect(f"{reverse('accounts:signup_manager')}?step=3")
        return render(
            request,
            "accounts/signup_manager_wizard_step2.html",
            {
                "form": form,
                "step": step,
                "total_steps": 4,
                "wizard_data": wizard_data,
            },
        )

    # Step 3: Brand
    elif step == 3:
        # Must have completed steps 1 & 2
        if "step1" not in wizard_data or "step2" not in wizard_data:
            return redirect(f"{reverse('accounts:signup_manager')}?step=1")

        form = ManagerWizardStep3Form(request.POST or None, request.FILES or None, initial=wizard_data.get("step3", {}))
        if request.method == "POST":
            action = request.POST.get("action", "next")
            if action == "back":
                return redirect(f"{reverse('accounts:signup_manager')}?step=2")
            elif action == "skip":
                # Skip button: no logo, just store empty step3 and proceed
                wizard_data["step3"] = {}
                _set_manager_wizard_data(request, wizard_data)
                return redirect(f"{reverse('accounts:signup_manager')}?step=4")
            elif action == "next":
                # Defensive logo upload handling - never crash signup
                try:
                    if form.is_valid():
                        # Store logo file in session (as base64 if provided)
                        logo_file = form.cleaned_data.get("logo")
                        if logo_file:
                            import base64

                            # Validate basic constraints (5MB limit)
                            if logo_file.size > 5 * 1024 * 1024:
                                raise ValueError("Logo file too large (max 5MB)")

                            wizard_data["step3"] = {
                                "logo_name": logo_file.name,
                                "logo_content_type": logo_file.content_type,
                                "logo_data": base64.b64encode(logo_file.read()).decode("utf-8"),
                            }
                        else:
                            wizard_data["step3"] = {}
                        _set_manager_wizard_data(request, wizard_data)
                        return redirect(f"{reverse('accounts:signup_manager')}?step=4")
                except (ValidationError, ValueError, OSError, IOError) as e:
                    # Expected errors: validation, file I/O, image processing
                    log.warning("Logo upload failed during wizard step 3: %s", e)
                    messages.info(request, "Logo upload is not available yet — continuing without a logo.")
                    wizard_data["step3"] = {}
                    _set_manager_wizard_data(request, wizard_data)
                    return redirect(f"{reverse('accounts:signup_manager')}?step=4")
                except Exception as e:
                    # Safety net for any unexpected errors
                    log.error("Unexpected error during logo upload in wizard step 3: %s", e, exc_info=True)
                    messages.info(request, "Logo upload is not available yet — continuing without a logo.")
                    wizard_data["step3"] = {}
                    _set_manager_wizard_data(request, wizard_data)
                    return redirect(f"{reverse('accounts:signup_manager')}?step=4")
        return render(
            request,
            "accounts/signup_manager_wizard_step3.html",
            {
                "form": form,
                "step": step,
                "total_steps": 4,
                "wizard_data": wizard_data,
            },
        )

    # Step 4: Review & Create
    elif step == 4:
        # Must have completed steps 1, 2, & 3
        if "step1" not in wizard_data or "step2" not in wizard_data or "step3" not in wizard_data:
            return redirect(f"{reverse('accounts:signup_manager')}?step=1")

        form = ManagerWizardStep4Form(request.POST or None)
        if request.method == "POST":
            action = request.POST.get("action", "create")
            if action == "back":
                return redirect(f"{reverse('accounts:signup_manager')}?step=3")
            elif action == "create" and form.is_valid():
                # Create everything
                try:
                    return _complete_manager_wizard_signup(request, wizard_data)
                except Exception as e:
                    log.error("Manager wizard signup failed: %s", e, exc_info=True)
                    # Don't expose raw database errors to users
                    if "NOT NULL constraint" in str(e) or "IntegrityError" in str(type(e).__name__):
                        messages.error(request, "Could not create store. Please try again or contact support.")
                    else:
                        messages.error(request, f"Something went wrong: {str(e)}. Please try again or contact support.")

        # Prepare summary data for review
        summary = {
            "email": wizard_data.get("step1", {}).get("email"),
            "full_name": wizard_data.get("step1", {}).get("full_name"),
            "business_name": wizard_data.get("step2", {}).get("business_name"),
            "business_kind": wizard_data.get("step2", {}).get("business_kind"),
            "subdomain": wizard_data.get("step2", {}).get("subdomain"),
            "has_logo": bool(wizard_data.get("step3", {}).get("logo_data")),
        }

        return render(
            request,
            "accounts/signup_manager_wizard_step4.html",
            {
                "form": form,
                "step": step,
                "total_steps": 4,
                "wizard_data": wizard_data,
                "summary": summary,
            },
        )

    # Fallback
    return redirect(f"{reverse('accounts:signup_manager')}?step=1")


def _complete_manager_wizard_signup(request, wizard_data):
    """
    Complete the manager wizard signup by creating all entities.
    This keeps all the existing business logic intact.
    """
    from django.db import transaction
    from django.core.files.base import ContentFile
    import base64

    step1 = wizard_data.get("step1", {})
    step2 = wizard_data.get("step2", {})
    step3 = wizard_data.get("step3", {})

    with transaction.atomic():
        # 1. Create User
        email = step1["email"].strip().lower()
        full_name = step1["full_name"].strip()
        password = step1["password1"]

        # Guard: unique user/email (double-check)
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            messages.error(request, "An account with that email already exists. Please sign in instead.")
            return redirect(f"{reverse('accounts:signup_manager')}?step=1")

        user = User.objects.create_user(username=email, email=email, password=password)

        # Split name
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

        # 2. Create Business
        biz = None
        if Business is not None:
            biz_name = step2["business_name"].strip()
            business_kind = step2["business_kind"]
            subdomain = (step2.get("subdomain") or "").strip().lower()

            # Validate subdomain
            if subdomain:
                import re

                if not re.fullmatch(r"[a-z0-9-]+", subdomain):
                    raise ValueError("Invalid subdomain format")
                if Business.objects.filter(subdomain__iexact=subdomain).exists():
                    raise ValueError("Subdomain already taken")

            # Unique slug
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
            if hasattr(Business, "business_kind"):
                bkwargs["business_kind"] = business_kind

            # Add section flags based on vertical (prevents NOT NULL constraint errors)
            try:
                from tenants.section_defaults import build_section_defaults

                section_flags = build_section_defaults(business_kind)
                # Only include flags that exist on the model (defensive)
                for key, value in section_flags.items():
                    if hasattr(Business, key):
                        bkwargs[key] = value
            except Exception as e:
                log.warning("Failed to set section defaults: %s", e)

            biz = Business.objects.create(**bkwargs)

            # Membership
            if Membership is not None:
                Membership.objects.update_or_create(
                    user=user,
                    business=biz,
                    defaults={"role": "MANAGER", "status": "ACTIVE"},
                )

            # Seed defaults
            _seed_defaults_for_business(biz)

            # 3. Save logo if provided (with defensive handling)
            logo_data = step3.get("logo_data")
            if logo_data and hasattr(biz, "logo"):
                try:
                    import base64
                    from django.core.files.base import ContentFile

                    logo_bytes = base64.b64decode(logo_data)
                    logo_name = step3.get("logo_name", "logo.png")
                    biz.logo.save(logo_name, ContentFile(logo_bytes), save=True)
                except (ValueError, OSError, IOError) as e:
                    # Expected errors: base64 decode, file storage, I/O
                    log.warning("Failed to save logo during manager wizard: %s", e)
                except Exception as e:
                    # Safety net - never crash signup due to logo
                    log.error("Unexpected error saving logo during manager wizard: %s", e, exc_info=True)

        # 4. Ensure Profile exists and mark as manager (NOT an agent)
        try:
            profile = getattr(user, "profile", None)
            if profile is None:
                profile, _ = Profile.objects.get_or_create(user=user)
            if hasattr(profile, "is_manager"):
                profile.is_manager = True
                profile.save(update_fields=["is_manager"])
        except Exception:
            pass

        # 5. Explicitly ensure NO AgentProfile is created for managers
        try:
            from inventory.models import AgentProfile

            # Delete any accidentally created AgentProfile
            AgentProfile.objects.filter(user=user).delete()
        except Exception:
            pass

        # 6. Auto-login + select business
        login(request, user)
        if biz is not None:
            try:
                request.session[TENANT_SESSION_KEY] = biz.pk
            except Exception:
                pass
            messages.success(request, f"🎉 Welcome to {biz.name}! Your store is ready.")
        else:
            messages.success(request, "🎉 Your manager account is ready!")

        # Clear wizard data
        _clear_manager_wizard_data(request)

        # Send welcome email after transaction commit
        from django.db import transaction
        from notifications.services import emit_event

        transaction.on_commit(
            lambda: emit_event(
                event_type="WELCOME_MANAGER",
                recipients=[user.email] if user.email else [],
                dedupe_key=f"WELCOME_MANAGER:{user.id}",
                payload={
                    "manager_name": user.get_full_name() or user.username,
                    "business_name": biz.name if biz else "",
                    "login_url": request.build_absolute_uri("/dashboard/"),
                    "support_url": "https://emajinet.africa/support" or request.build_absolute_uri("/support/"),
                    "next_steps": [
                        "Scan In - Add products to your inventory",
                        "Scan & Sell - Process sales quickly",
                    ],
                },
                business=biz,
                user=user,  # Pass user for preference checking (though transactional emails bypass preferences)
            )
        )

        # Redirect to main dashboard (manager dashboard, not inventory dashboard)
        return redirect(_safe_redirect("dashboard:home", default="/dashboard/"))


# =========================================
# Multi-step Signup Wizard
# =========================================
WIZARD_SESSION_KEY = "signup_wizard_data"


def _get_wizard_data(request):
    """Get wizard data from session"""
    return request.session.get(WIZARD_SESSION_KEY, {})


def _set_wizard_data(request, data):
    """Save wizard data to session"""
    request.session[WIZARD_SESSION_KEY] = data
    request.session.modified = True


def _clear_wizard_data(request):
    """Clear wizard data from session"""
    if WIZARD_SESSION_KEY in request.session:
        del request.session[WIZARD_SESSION_KEY]
        request.session.modified = True


@ensure_csrf_cookie
@never_cache
@require_http_methods(["GET", "POST"])
def signup_wizard(request, step=0):
    """
    Multi-step signup wizard with gamification.

    Steps:
    0 - Welcome (no form, just intro)
    1 - Your Account (user credentials)
    2 - Your Business (business details)
    3 - First Location (shop setup)
    4 - Goals & Finish (onboarding goals)
    """
    # If already authenticated, redirect to dashboard
    if request.user.is_authenticated:
        return redirect(
            _safe_redirect("inventory:inventory_dashboard", "dashboard:home", default="/inventory/dashboard/")
        )

    # Validate step
    step = int(step)
    if step < 0 or step > 4:
        return redirect("accounts:signup_wizard_step", step=0)

    wizard_data = _get_wizard_data(request)

    # Step 0: Welcome page (no form)
    if step == 0:
        if request.method == "POST":
            # Just move to step 1
            return redirect("accounts:signup_wizard_step", step=1)
        return render(
            request,
            "registration/signup_wizard_step0.html",
            {
                "step": step,
                "total_steps": 5,
            },
        )

    # Step 1: Your Account
    elif step == 1:
        form = WizardStep1Form(request.POST or None, initial=wizard_data.get("step1", {}))
        if request.method == "POST":
            if form.is_valid():
                wizard_data["step1"] = form.cleaned_data
                _set_wizard_data(request, wizard_data)
                return redirect("accounts:signup_wizard_step", step=2)
        return render(
            request,
            "registration/signup_wizard_step1.html",
            {
                "form": form,
                "step": step,
                "total_steps": 5,
                "wizard_data": wizard_data,
            },
        )

    # Step 2: Your Business
    elif step == 2:
        # Must have completed step 1
        if "step1" not in wizard_data:
            return redirect("accounts:signup_wizard_step", step=1)

        form = WizardStep2Form(request.POST or None, initial=wizard_data.get("step2", {}))
        if request.method == "POST":
            if form.is_valid():
                wizard_data["step2"] = form.cleaned_data
                _set_wizard_data(request, wizard_data)
                return redirect("accounts:signup_wizard_step", step=3)
        return render(
            request,
            "registration/signup_wizard_step2.html",
            {
                "form": form,
                "step": step,
                "total_steps": 5,
                "wizard_data": wizard_data,
            },
        )

    # Step 3: First Location
    elif step == 3:
        # Must have completed steps 1 & 2
        if "step1" not in wizard_data or "step2" not in wizard_data:
            return redirect("accounts:signup_wizard_step", step=1)

        form = WizardStep3Form(request.POST or None, initial=wizard_data.get("step3", {}))
        if request.method == "POST":
            if form.is_valid():
                wizard_data["step3"] = form.cleaned_data
                _set_wizard_data(request, wizard_data)
                return redirect("accounts:signup_wizard_step", step=4)
        return render(
            request,
            "registration/signup_wizard_step3.html",
            {
                "form": form,
                "step": step,
                "total_steps": 5,
                "wizard_data": wizard_data,
            },
        )

    # Step 4: Goals & Finish
    elif step == 4:
        # Must have completed steps 1, 2, & 3
        if "step1" not in wizard_data or "step2" not in wizard_data or "step3" not in wizard_data:
            return redirect("accounts:signup_wizard_step", step=1)

        form = WizardStep4Form(request.POST or None, initial=wizard_data.get("step4", {}))
        if request.method == "POST":
            if form.is_valid():
                wizard_data["step4"] = form.cleaned_data
                _set_wizard_data(request, wizard_data)

                # Now create everything: User, Business, Location, Membership, OnboardingProfile
                try:
                    return _complete_wizard_signup(request, wizard_data)
                except Exception as e:
                    log.error("Wizard signup failed: %s", e, exc_info=True)
                    messages.error(request, "Something went wrong. Please try again or contact support.")
                    return render(
                        request,
                        "registration/signup_wizard_step4.html",
                        {
                            "form": form,
                            "step": step,
                            "total_steps": 5,
                            "wizard_data": wizard_data,
                        },
                    )

        return render(
            request,
            "registration/signup_wizard_step4.html",
            {
                "form": form,
                "step": step,
                "total_steps": 5,
                "wizard_data": wizard_data,
            },
        )

    # Fallback
    return redirect("accounts:signup_wizard_step", step=0)


def _complete_wizard_signup(request, wizard_data):
    """
    Complete the wizard signup by creating all entities.
    This keeps all the existing business logic intact.
    """
    from django.db import transaction

    step1 = wizard_data.get("step1", {})
    step2 = wizard_data.get("step2", {})
    step3 = wizard_data.get("step3", {})
    step4 = wizard_data.get("step4", {})

    with transaction.atomic():
        # 1. Create User
        email = step1["email"].strip().lower()
        full_name = step1["full_name"].strip()
        password = step1["password1"]

        # Guard: unique user/email (double-check)
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            messages.error(request, "An account with that email already exists. Please sign in instead.")
            return redirect("accounts:signup_wizard_step", step=1)

        user = User.objects.create_user(username=email, email=email, password=password)

        # Split name
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

        # 2. Create Business
        biz = None
        if Business is not None:
            biz_name = step2["business_name"].strip()
            business_kind = step2["business_kind"]

            # Unique slug
            base = slugify(biz_name)[:40] or "store"
            unique = base
            i = 1
            while Business.objects.filter(slug=unique).exists():
                i += 1
                unique = f"{base}-{i}"

            bkwargs = {"name": biz_name, "slug": unique}
            if hasattr(Business, "created_by"):
                bkwargs["created_by"] = user
            if hasattr(Business, "status"):
                bkwargs["status"] = "ACTIVE"
            if hasattr(Business, "business_kind"):
                bkwargs["business_kind"] = business_kind

            # Add section flags based on vertical (prevents NOT NULL constraint errors)
            try:
                from tenants.section_defaults import build_section_defaults

                section_flags = build_section_defaults(business_kind)
                # Only include flags that exist on the model (defensive)
                for key, value in section_flags.items():
                    if hasattr(Business, key):
                        bkwargs[key] = value
            except Exception as e:
                log.warning("Failed to set section defaults: %s", e)

            biz = Business.objects.create(**bkwargs)

            # Membership
            if Membership is not None:
                Membership.objects.update_or_create(
                    user=user,
                    business=biz,
                    defaults={"role": "MANAGER", "status": "ACTIVE"},
                )

            # Seed defaults
            _seed_defaults_for_business(biz)

            # 3. Create first Location
            try:
                from inventory.models import Location as InvLocation

                location_name = step3["location_name"].strip()
                city = step3.get("city", "").strip()

                InvLocation.objects.create(
                    business=biz,
                    name=location_name,
                    city=city,
                    is_default=True,
                )
            except Exception as e:
                log.warning("Failed to create location during wizard: %s", e)

        # 4. Create OnboardingProfile
        try:
            OnboardingProfile.objects.create(
                user=user,
                goal_stop_theft=step4.get("goal_stop_theft", False),
                goal_see_profit=step4.get("goal_see_profit", False),
                goal_track_performance=step4.get("goal_track_performance", False),
                goal_move_off_notebooks=step4.get("goal_move_off_notebooks", False),
                completed_at=timezone.now(),
                wizard_version="v1",
                first_business_name=step2.get("business_name", ""),
                first_location_name=step3.get("location_name", ""),
                chosen_vertical=step2.get("business_kind", ""),
            )
        except Exception as e:
            log.warning("Failed to create onboarding profile: %s", e)

        # 5. Ensure Profile exists and mark as manager
        try:
            profile = getattr(user, "profile", None)
            if profile is None:
                profile, _ = Profile.objects.get_or_create(user=user)
            if hasattr(profile, "is_manager"):
                profile.is_manager = True
                profile.save(update_fields=["is_manager"])
        except Exception:
            pass

        # 6. Email verification (if enabled)
        enable_email_otp = getattr(settings, "ENABLE_EMAIL_OTP", False)
        if enable_email_otp and email:
            try:
                profile = getattr(user, "profile", None)
                if profile:
                    profile.email_verified = False
                    profile.save(update_fields=["email_verified"])

                # Send OTP for signup verification
                try:
                    request_email_otp(email, "signup", user=user, request=request)
                    # Store email in session for verification step
                    request.session["signup_email"] = email
                    request.session["signup_user_id"] = user.id
                    # Clear wizard data but keep session for verification
                    _clear_wizard_data(request)
                    # Redirect to verification step
                    messages.info(request, "Please verify your email address. We've sent you a code.")
                    return redirect("accounts:signup_verify_email")
                except Exception as e:
                    log.warning(f"Failed to send signup OTP: {e}", exc_info=True)
                    # Continue with signup even if OTP fails
            except Exception as e:
                log.warning(f"Failed to set email_verified=False: {e}", exc_info=True)

        # 7. Auto-login + select business (if email verification not required or skipped)
        login(request, user)
        if biz is not None:
            try:
                request.session[TENANT_SESSION_KEY] = biz.pk
            except Exception:
                pass
            messages.success(request, f"🎉 Welcome to {biz.name}! Your dashboard is ready.")
        else:
            messages.success(request, "🎉 Your account is ready!")

        # Clear wizard data
        _clear_wizard_data(request)

        # Send welcome email after transaction commit
        from notifications.services import emit_event

        transaction.on_commit(
            lambda: emit_event(
                event_type="WELCOME_MANAGER",
                recipients=[user.email] if user.email else [],
                dedupe_key=f"WELCOME_MANAGER:{user.id}",
                payload={
                    "manager_name": user.get_full_name() or user.username,
                    "business_name": biz.name if biz else "",
                    "login_url": request.build_absolute_uri("/inventory/dashboard/"),
                    "support_url": "https://emajinet.africa/support" or request.build_absolute_uri("/support/"),
                    "next_steps": [
                        "Scan In - Add products to your inventory",
                        "Scan & Sell - Process sales quickly",
                    ],
                },
                business=biz,
                user=user,  # Pass user for preference checking (though transactional emails bypass preferences)
            )
        )

        # Redirect to dashboard
        return redirect(_safe_redirect("inventory:inventory_dashboard", default="/inventory/dashboard/"))


# ----------------------------
# OTP JSON API Endpoints
# ----------------------------
@never_cache
@require_http_methods(["GET", "POST"])
@ensure_csrf_cookie
def signup_verify_email(request):
    """
    Email verification step after signup.
    Shows a form to enter the OTP code sent to the user's email.
    """
    # Check if we have signup session data
    signup_email = request.session.get("signup_email")
    signup_user_id = request.session.get("signup_user_id")

    if not signup_email or not signup_user_id:
        messages.error(request, "No pending email verification found. Please sign up again.")
        return redirect("accounts:signup")

    # Get user
    try:
        user = User.objects.get(id=signup_user_id, email__iexact=signup_email)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please sign up again.")
        request.session.pop("signup_email", None)
        request.session.pop("signup_user_id", None)
        return redirect("accounts:signup")

    # Check if already verified
    try:
        if user.profile.email_verified:
            messages.success(request, "Your email is already verified!")
            request.session.pop("signup_email", None)
            request.session.pop("signup_user_id", None)
            login(request, user)
            return redirect(_safe_redirect("inventory:inventory_dashboard", default="/inventory/dashboard/"))
    except Exception:
        pass

    if request.method == "POST":
        action = request.POST.get("action", "verify")

        if action == "resend":
            # Resend OTP
            try:
                request_email_otp(signup_email, "signup", user=user, request=request)
                messages.success(request, "Verification code sent! Please check your email.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                log.error(f"Failed to resend OTP: {e}", exc_info=True)
                messages.error(request, "Failed to send verification code. Please try again.")
        else:
            # Verify code
            code = (request.POST.get("code") or "").strip()
            if not code:
                messages.error(request, "Please enter the verification code.")
            elif len(code) != 6 or not code.isdigit():
                messages.error(request, "Code must be 6 digits.")
            else:
                if verify_email_otp(signup_email, "signup", code):
                    # Mark as verified
                    try:
                        profile = user.profile
                        profile.email_verified = True
                        profile.save(update_fields=["email_verified"])
                    except Exception:
                        pass

                    # Clear session
                    request.session.pop("signup_email", None)
                    request.session.pop("signup_user_id", None)

                    # Log in and redirect
                    login(request, user)
                    messages.success(request, "Email verified! Welcome to Emajinet!")

                    # Set active business if available
                    try:
                        if Membership is not None:
                            membership = Membership.objects.filter(user=user, status="ACTIVE").first()
                            if membership and hasattr(membership, "business"):
                                request.session[TENANT_SESSION_KEY] = membership.business.pk
                    except Exception:
                        pass

                    return redirect(_safe_redirect("inventory:inventory_dashboard", default="/inventory/dashboard/"))
                else:
                    messages.error(request, "Invalid or expired code. Please try again.")

    return render(
        request,
        "registration/signup_verify_email.html",
        {
            "email": signup_email,
            "email_masked": _mask_email(signup_email),
        },
    )


@require_http_methods(["POST"])
@ensure_csrf_cookie
def otp_request_api(request):
    """
    JSON endpoint to request an email OTP.
    POST /auth/otp/request
    Body: {"email": "user@example.com", "purpose": "signup"}
    Returns: {"ok": true} or {"ok": false, "error": "..."}
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    email = (data.get("email") or "").strip()
    purpose = (data.get("purpose") or "signup").strip()

    if not email:
        return JsonResponse({"ok": False, "error": "Email is required"}, status=400)

    if purpose not in ["signup", "login", "reset", "2fa"]:
        return JsonResponse({"ok": False, "error": "Invalid purpose"}, status=400)

    # Optional: get user if exists (for login/reset purposes)
    user = None
    if purpose in ["login", "reset"]:
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            if purpose == "login":
                # Don't reveal if user exists for security
                pass

    try:
        request_email_otp(email, purpose, user=user, request=request)
        return JsonResponse({"ok": True})
    except ValueError as e:
        error_msg = str(e)
        status = 429 if "rate" in error_msg.lower() or "too many" in error_msg.lower() else 400
        return JsonResponse({"ok": False, "error": error_msg}, status=status)
    except Exception as e:
        log.error(f"OTP request failed: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": "Failed to send OTP. Please try again."}, status=500)


@require_http_methods(["POST"])
@ensure_csrf_cookie
def otp_verify_api(request):
    """
    JSON endpoint to verify an email OTP.
    POST /auth/otp/verify
    Body: {"email": "user@example.com", "purpose": "signup", "code": "123456"}
    Returns: {"ok": true} or {"ok": false, "error": "..."}
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    email = (data.get("email") or "").strip()
    purpose = (data.get("purpose") or "signup").strip()
    code = (data.get("code") or "").strip()

    if not email or not code:
        return JsonResponse({"ok": False, "error": "Email and code are required"}, status=400)

    if purpose not in ["signup", "login", "reset", "2fa"]:
        return JsonResponse({"ok": False, "error": "Invalid purpose"}, status=400)

    if len(code) != 6 or not code.isdigit():
        return JsonResponse({"ok": False, "error": "Code must be 6 digits"}, status=400)

    success = verify_email_otp(email, purpose, code)

    if success:
        return JsonResponse({"ok": True})
    else:
        return JsonResponse({"ok": False, "error": "Invalid or expired code"}, status=400)


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


# ============================================================================
# Two-Factor Authentication (SMS OTP) Views
# ============================================================================


def _check_2fa_rate_limit(user, action: str) -> tuple[bool, str | None]:
    """
    Check rate limits for 2FA actions.

    Args:
        user: User object
        action: "send" or "verify"

    Returns:
        (allowed: bool, error_message: str | None)
    """
    from django.core.cache import cache
    import time

    user_id = user.id
    now = time.time()

    if action == "send":
        # Check cooldown (60 seconds between sends)
        last_send_key = f"twofa:sms:last_send_at:{user_id}"
        last_send = cache.get(last_send_key)

        if last_send:
            elapsed = now - last_send
            if elapsed < 60:
                wait_seconds = int(60 - elapsed)
                return False, f"Please wait {wait_seconds} seconds before requesting a new code."

        # Check max sends (3 per 10 minutes)
        send_count_key = f"twofa:sms:send_count:{user_id}"
        send_count = cache.get(send_count_key, 0)

        if send_count >= 3:
            return False, "Too many attempts. Contact your admin."

        # Update counters
        cache.set(last_send_key, now, 60)  # 60 second TTL
        cache.set(send_count_key, send_count + 1, 600)  # 10 minute TTL

        return True, None

    elif action == "verify":
        # Check max verify attempts (8 per 10 minutes)
        verify_count_key = f"twofa:sms:verify_count:{user_id}"
        verify_count = cache.get(verify_count_key, 0)

        if verify_count >= 8:
            return False, "Too many attempts. Contact your admin."

        # Update counter
        cache.set(verify_count_key, verify_count + 1, 600)  # 10 minute TTL

        return True, None

    return False, "Invalid action"


@login_required
@require_http_methods(["POST"])
def twofa_sms_enable_start(request):
    """
    Step 1 of enabling SMS 2FA: validate phone number and send OTP.
    Stores pending_phone in session for verification.
    Supports resend: if phone not provided, uses session phone.
    """
    from .models import get_or_create_twofactor
    from .services.twilio_verify import send_otp
    from django.conf import settings

    # Check if Twilio is configured
    if not getattr(settings, "TWILIO_VERIFY_ENABLED", False):
        messages.error(request, "SMS verification is not available. Please contact your administrator.")
        return redirect("accounts:settings_security")

    phone = request.POST.get("phone", "").strip()

    # Support resend: if no phone provided, try session (for resend button)
    if not phone:
        phone = request.session.get("twofa_pending_phone", "")
        if not phone:
            messages.error(request, "Phone number is required.")
            return redirect("accounts:settings_security")

    # Basic phone validation (E.164 format)
    if not phone.startswith("+"):
        messages.error(request, "Phone number must be in international format (e.g. +265991234567)")
        return redirect("accounts:settings_security")

    if len(phone) < 8 or len(phone) > 20:
        messages.error(request, "Invalid phone number length.")
        return redirect("accounts:settings_security")

    # Check rate limits
    allowed, error_msg = _check_2fa_rate_limit(request.user, "send")
    if not allowed:
        messages.error(request, error_msg)
        return redirect("accounts:settings_security")

    # Send OTP
    success, error_msg = send_otp(phone)

    if not success:
        messages.error(request, error_msg or "Failed to send verification code.")
        return redirect("accounts:settings_security")

    # Store pending phone in session
    request.session["twofa_pending_phone"] = phone
    request.session["twofa_enable_flow"] = True

    messages.success(request, f"Verification code sent to {phone}")
    return redirect("accounts:settings_security")


@login_required
@require_http_methods(["POST"])
def twofa_sms_enable_verify(request):
    """
    Step 2 of enabling SMS 2FA: verify OTP and enable 2FA.
    """
    from .models import get_or_create_twofactor
    from .services.twilio_verify import check_otp
    from django.utils import timezone

    code = request.POST.get("code", "").strip()
    pending_phone = request.session.get("twofa_pending_phone")

    if not pending_phone:
        messages.error(request, "No pending verification. Please start the process again.")
        return redirect("accounts:settings_security")

    if not code:
        messages.error(request, "Verification code is required.")
        return redirect("accounts:settings_security")

    # Check rate limits
    allowed, error_msg = _check_2fa_rate_limit(request.user, "verify")
    if not allowed:
        messages.error(request, error_msg)
        return redirect("accounts:settings_security")

    # Verify OTP
    approved, error_msg = check_otp(pending_phone, code)

    if not approved:
        messages.error(request, error_msg or "Invalid verification code.")
        return redirect("accounts:settings_security")

    # Enable 2FA
    tf = get_or_create_twofactor(request.user)
    tf.sms_enabled = True
    tf.phone_e164 = pending_phone
    tf.phone_verified_at = timezone.now()
    tf.save(update_fields=["sms_enabled", "phone_e164", "phone_verified_at", "updated_at"])

    # Clear session
    request.session.pop("twofa_pending_phone", None)
    request.session.pop("twofa_enable_flow", None)

    messages.success(request, "Two-factor authentication enabled successfully.")
    return redirect("accounts:settings_security")


@login_required
@require_http_methods(["POST"])
def twofa_sms_disable_start(request):
    """
    Step 1 of disabling SMS 2FA: send OTP to verify identity.
    """
    from .models import get_or_create_twofactor
    from .services.twilio_verify import send_otp

    tf = get_or_create_twofactor(request.user)

    if not tf.sms_enabled:
        messages.error(request, "Two-factor authentication is not enabled.")
        return redirect("accounts:settings_security")

    # Check rate limits
    allowed, error_msg = _check_2fa_rate_limit(request.user, "send")
    if not allowed:
        messages.error(request, error_msg)
        return redirect("accounts:settings_security")

    # Send OTP to stored phone
    success, error_msg = send_otp(tf.phone_e164)

    if not success:
        messages.error(request, error_msg or "Failed to send verification code.")
        return redirect("accounts:settings_security")

    # Mark disable flow in session
    request.session["twofa_disable_flow"] = True

    from .models import mask_phone

    messages.success(request, f"Verification code sent to {mask_phone(tf.phone_e164)}")
    return redirect("accounts:settings_security")


@login_required
@require_http_methods(["POST"])
def twofa_sms_disable_verify(request):
    """
    Step 2 of disabling SMS 2FA: verify OTP and disable 2FA.
    """
    from .models import get_or_create_twofactor
    from .services.twilio_verify import check_otp

    code = request.POST.get("code", "").strip()
    disable_flow = request.session.get("twofa_disable_flow")

    if not disable_flow:
        messages.error(request, "No pending verification. Please start the process again.")
        return redirect("accounts:settings_security")

    if not code:
        messages.error(request, "Verification code is required.")
        return redirect("accounts:settings_security")

    tf = get_or_create_twofactor(request.user)

    if not tf.sms_enabled:
        messages.error(request, "Two-factor authentication is not enabled.")
        return redirect("accounts:settings_security")

    # Check rate limits
    allowed, error_msg = _check_2fa_rate_limit(request.user, "verify")
    if not allowed:
        messages.error(request, error_msg)
        return redirect("accounts:settings_security")

    # Verify OTP
    approved, error_msg = check_otp(tf.phone_e164, code)

    if not approved:
        messages.error(request, error_msg or "Invalid verification code.")
        return redirect("accounts:settings_security")

    # Disable 2FA
    tf.sms_enabled = False
    tf.save(update_fields=["sms_enabled", "updated_at"])

    # Clear session
    request.session.pop("twofa_disable_flow", None)

    messages.success(request, "Two-factor authentication disabled.")
    return redirect("accounts:settings_security")


@require_http_methods(["GET", "POST"])
def twofa_challenge(request):
    """
    2FA challenge screen after password login.
    User must enter OTP sent to their phone to complete login.
    """
    from .models import get_or_create_twofactor, is_twofa_enabled, mask_phone
    from .services.twilio_verify import send_otp, check_otp
    from django.utils import timezone
    import time

    # Must be authenticated to see this page
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    # Check if user has 2FA enabled
    if not is_twofa_enabled(request.user):
        # No 2FA required, redirect to intended destination
        next_url = request.GET.get("next") or request.POST.get("next") or "/"
        return redirect(next_url)

    # Get user's 2FA settings
    tf = get_or_create_twofactor(request.user)
    masked_phone = mask_phone(tf.phone_e164)

    # On first GET, send OTP automatically (if rate limits allow)
    if request.method == "GET":
        # Check if we already sent recently (from session)
        challenge_otp_sent = request.session.get("twofa_challenge_otp_sent")

        if not challenge_otp_sent:
            # Try to send OTP
            allowed, error_msg = _check_2fa_rate_limit(request.user, "send")

            if allowed:
                success, error_msg = send_otp(tf.phone_e164)
                if success:
                    request.session["twofa_challenge_otp_sent"] = True
                else:
                    messages.error(request, error_msg or "Failed to send verification code.")
            else:
                # Rate limit hit - show error but still show form
                messages.error(request, error_msg)

    # Handle POST (verify code)
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "resend":
            # Resend OTP
            allowed, error_msg = _check_2fa_rate_limit(request.user, "send")

            if not allowed:
                messages.error(request, error_msg)
            else:
                success, error_msg = send_otp(tf.phone_e164)

                if success:
                    request.session["twofa_challenge_otp_sent"] = True
                    messages.success(request, "New verification code sent.")
                else:
                    messages.error(request, error_msg or "Failed to send verification code.")

            return redirect(f"{request.path}?next={request.POST.get('next', '/')}")

        elif action == "verify":
            code = request.POST.get("code", "").strip()

            if not code:
                messages.error(request, "Verification code is required.")
                return redirect(f"{request.path}?next={request.POST.get('next', '/')}")

            # Check rate limits
            allowed, error_msg = _check_2fa_rate_limit(request.user, "verify")
            if not allowed:
                messages.error(request, error_msg)
                return redirect(f"{request.path}?next={request.POST.get('next', '/')}")

            # Verify OTP
            approved, error_msg = check_otp(tf.phone_e164, code)

            if not approved:
                messages.error(request, error_msg or "Invalid verification code.")
                return redirect(f"{request.path}?next={request.POST.get('next', '/')}")

            # Success! Mark 2FA as passed
            request.session["twofa_passed"] = True
            request.session["twofa_passed_at"] = time.time()
            request.session.pop("twofa_required", None)
            request.session.pop("twofa_challenge_otp_sent", None)

            # Redirect to intended destination
            next_url = request.POST.get("next") or request.GET.get("next") or "/"

            # Sanitize next URL to prevent open redirect
            from django.utils.http import url_has_allowed_host_and_scheme

            if not url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                next_url = "/"

            return redirect(next_url)

    # Render challenge page
    next_url = request.GET.get("next") or request.POST.get("next") or "/"

    context = {
        "masked_phone": masked_phone,
        "next": next_url,
    }

    return render(request, "accounts/2fa_challenge.html", context)
