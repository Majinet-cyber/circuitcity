# tenants/views_invites.py
from __future__ import annotations

from typing import Optional, Any
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, authenticate
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from tenants.models import AgentInvite
from tenants.services.invites import accept_invite_by_token
from .forms import AgentInviteAcceptForm

TENANT_SESSION_KEY = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _reverse_or(path_name: str, default: str = "/") -> str:
    try:
        return reverse(path_name)
    except NoReverseMatch:
        return default


def _best_post_accept_redirect(request: HttpRequest) -> str:
    """
    After successfully joining, send the user somewhere sensible, preferring
    dashboards if available, then tenant activator/switcher, then home.
    """
    for name in [
        "inventory:inventory_dashboard",  # most agent-friendly
        "dashboard:home",
        "dashboard:dashboard",
        "tenants:activate_mine",
        "tenants:choose_business",
        "home",
    ]:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/"


def _render_safe(request: HttpRequest, template: str, ctx: dict, *, status: int = 200) -> HttpResponse:
    """
    Try to render a template; if missing, fall back to a tiny inline page
    so the flow never crashes in dev.
    """
    try:
        return render(request, template, ctx, status=status)
    except Exception:
        # Minimal fallback HTML
        title = ctx.get("title", "Invitation")
        body = ctx.get("message", "")
        extra = ""
        inv = ctx.get("invite")
        if inv:
            extra = f"<p><small>Business: {getattr(getattr(inv, 'business', None), 'name', '—')}</small></p>"
        return HttpResponse(f"<h1>{title}</h1><p>{body}</p>{extra}", status=status)


# ---------------------------------------------------------------------------
# Robust invite lookup (accept both token and code style links)
# ---------------------------------------------------------------------------

def _invite_q_for_value(val: str) -> Q:
    """
    Build a Q() that ORs across common identifier fields.
    Support models that used 'token', 'code', 'uid', 'uuid', 'slug', 'key'.
    """
    val = (val or "").strip().strip("/")
    fields = ("token", "code", "uid", "uuid", "slug", "key")
    q = Q()
    for f in fields:
        # Only include fields that really exist on the model
        try:
            AgentInvite._meta.get_field(f)  # type: ignore[attr-defined]
            q = q | Q(**{f: val})
        except Exception:
            continue
    # If none of those fields exist (unlikely), use token as a best-effort
    if q == Q():
        q = Q(token=val)
    return q


def _get_invite_any(token_or_code: str) -> Optional[AgentInvite]:
    """
    Try to find an invite by any identifier field. Prefer .all_objects if present
    so 'EXPIRED' or soft-deleted invites can still render an 'expired' page.
    """
    manager = getattr(AgentInvite, "all_objects", AgentInvite.objects)  # type: ignore[attr-defined]
    q = _invite_q_for_value(token_or_code)
    try:
        return manager.select_related("business").filter(q).first()  # type: ignore[attr-defined]
    except Exception:
        # very defensive fallback
        try:
            return AgentInvite.objects.select_related("business").filter(q).first()
        except Exception:
            return None


def _is_invite_expired(inv: AgentInvite) -> bool:
    """
    Honor a model method/property if present; else derive from 'expires_at'.
    """
    try:
        fn = getattr(inv, "is_expired", None)
        if callable(fn):
            return bool(fn())
        if isinstance(fn, bool):
            return fn
    except Exception:
        pass

    try:
        from django.utils import timezone
        expires_at = getattr(inv, "expires_at", None)
        if expires_at:
            now = timezone.now()
            return expires_at <= now
    except Exception:
        pass

    return False


def _ensure_share_url(request: HttpRequest, inv: AgentInvite) -> None:
    """
    Ensure an invite has a share_url attribute so UI can always show a copyable link.
    """
    try:
        has = getattr(inv, "share_url", None)
    except Exception:
        has = None

    if has:
        return

    # Determine the best identifier we can echo back
    ident = None
    for f in ("token", "code", "uid", "uuid", "slug", "key"):
        try:
            v = getattr(inv, f, None)
            if v:
                ident = str(v)
                break
        except Exception:
            pass

    if not ident:
        return

    try:
        rel = _reverse_or("tenants:invite_accept")
        # If we have the named route, rebuild with args
        if rel and "tenants/invites/accept" in rel:
            rel = reverse("tenants:invite_accept", args=[ident])
        setattr(inv, "share_url", request.build_absolute_uri(rel))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Username helper (avoid collisions when email local-parts repeat)
# ---------------------------------------------------------------------------

def _unique_username_from_email(email: str) -> str:
    User = get_user_model()
    base = (email or "").split("@")[0] or "user"
    candidate = base
    n = 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

@never_cache
@require_http_methods(["GET", "POST"])
def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """
    Redeem an agent invite token or code.

    Flow:
      - Locate invite by token/code/etc; show invalid if not found.
      - If expired → mark EXPIRED and show 'expired'.
      - If authenticated and (if invite has email) it matches → accept immediately (idempotent).
      - If not authenticated → show signup form with invited email prefilled/locked
        (or editable if invite has no email). On submit, create user, set password
        (only if none), log them in, accept invite, set active business in session,
        and redirect to the agent landing.
    """
    invite: Optional[AgentInvite] = _get_invite_any(token)
    if not invite:
        ctx = {
            "title": "Invalid invite",
            "message": "This invitation link is not valid. Please request a new invite from the manager.",
            "invite": None,
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=404)

    _ensure_share_url(request, invite)

    # Expiry handling
    if _is_invite_expired(invite):
        try:
            status_val = (getattr(invite, "status", "") or "").upper()
            if status_val != "EXPIRED":
                setattr(invite, "status", "EXPIRED")
                invite.save(update_fields=["status"])
        except Exception:
            pass

        ctx = {
            "title": "Invite expired",
            "message": "This invitation has expired. Ask your manager to resend a new link.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/expired.html", ctx, status=410)

    # If already authenticated: accept immediately (email must match if invite has one)
    if getattr(request, "user", None) and request.user.is_authenticated:
        invited_email = (getattr(invite, "email", "") or "").lower().strip()
        if invited_email and (request.user.email or "").lower().strip() != invited_email:
            ctx = {
                "title": "Wrong account",
                "message": "You are signed in as a different user than the invited email. "
                           "Please sign out and open the link again, or ask your manager to resend the invite.",
                "invite": invite,
            }
            return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)

        # Accept (idempotent). If your service supports passing a location, we forward it.
        try:
            kw: dict[str, Any] = {"token": token, "user": request.user, "role": "AGENT"}
            location = getattr(invite, "location", None)
            location_id = getattr(invite, "location_id", None)
            if location or location_id:
                kw["location"] = location or location_id
            accept_invite_by_token(**kw)  # type: ignore[arg-type]
        except ValueError as e:
            ctx = {
                "title": "Invite problem",
                "message": str(e) or "This invitation cannot be used. Please ask for a new one.",
                "invite": invite,
            }
            return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)
        except Exception:
            ctx = {
                "title": "Something went wrong",
                "message": "We couldn't complete your invitation right now. Please try again.",
                "invite": invite,
            }
            return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

        # Pin active business into session (best-effort)
        try:
            biz_id = getattr(getattr(invite, "business", None), "id", None)
            if biz_id:
                request.session[TENANT_SESSION_KEY] = biz_id
        except Exception:
            pass

        try:
            messages.success(
                request,
                f"You're now part of {getattr(invite.business, 'name', 'the business')}. Welcome!",
            )
        except Exception:
            pass

        return redirect(_best_post_accept_redirect(request))

    # Not authenticated → show signup page
    if request.method == "GET":
        form = AgentInviteAcceptForm(initial_email=getattr(invite, "email", None) or None)
        if not getattr(invite, "email", None):
            form.fields["email"].disabled = False
            form.fields["email"].required = True
        ctx = {"form": form, "invite": invite, "title": "Join as Agent"}
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=200)

    # POST: create (or update) user with new password only if needed, then accept
    form = AgentInviteAcceptForm(request.POST, initial_email=getattr(invite, "email", None) or None)
    if not getattr(invite, "email", None):
        form.fields["email"].disabled = False
        form.fields["email"].required = True

    if not form.is_valid():
        ctx = {"form": form, "invite": invite, "title": "Join as Agent"}
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)

    User = get_user_model()
    email = (getattr(invite, "email", None) or form.cleaned_data.get("email") or "").lower().strip()
    if not email:
        ctx = {
            "title": "Email required",
            "message": "Please enter a valid email address to continue.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)

    password = form.cleaned_data["password1"]

    # Create user if not exists; otherwise require correct password (do not overwrite)
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        username = _unique_username_from_email(email)
        user = User.objects.create_user(username=username, email=email, password=password)
    else:
        # If account exists, authenticate with provided password; if the account
        # has no usable password, set one and proceed.
        if user.has_usable_password():
            auth_ok = authenticate(request, username=user.username, password=password)
            if not auth_ok:
                ctx = {
                    "form": form,
                    "invite": invite,
                    "title": "Join as Agent",
                    "message": "An account with this email already exists. Please enter its correct password.",
                }
                # surface a form error near password field
                try:
                    form.add_error("password1", "Incorrect password for existing account.")
                except Exception:
                    pass
                return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)
        else:
            user.set_password(password)
            user.save(update_fields=["password"])

    # Log them in (choose the safe path)
    auth_user = authenticate(request, username=user.username, password=password)
    if auth_user is None:
        # fallback if custom auth backends
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    else:
        login(request, auth_user)

    # Accept the invite and pin business id into session
    try:
        kw: dict[str, Any] = {"token": token, "user": request.user, "role": "AGENT"}
        # forward location if invite has one (so membership.location is set)
        location = getattr(invite, "location", None)
        location_id = getattr(invite, "location_id", None)
        if location or location_id:
            kw["location"] = location or location_id
        accept_invite_by_token(**kw)  # type: ignore[arg-type]
    except ValueError as e:
        ctx = {
            "title": "Invite problem",
            "message": str(e) or "This invitation cannot be used. Please ask for a new one.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)
    except Exception:
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't complete your invitation right now. Please try again.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    # Store active business in session for immediate agent view
    try:
        biz_id = getattr(getattr(invite, "business", None), "id", None)
        if biz_id:
            request.session[TENANT_SESSION_KEY] = biz_id
    except Exception:
        pass

    try:
        messages.success(
            request,
            f"You're now part of {getattr(invite.business, 'name', 'the business')}. Welcome!",
        )
    except Exception:
        pass

    return redirect(_best_post_accept_redirect(request))
