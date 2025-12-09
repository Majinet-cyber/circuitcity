# tenants/views_invites.py
from __future__ import annotations

import logging
from typing import Optional, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

from tenants.models import AgentInvite
from tenants.services.invites import accept_invite_by_token
from tenants.utils import set_active_business  # <-- ensure active business is mirrored into session + thread-local
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
    After successfully joining, send the user somewhere agent-friendly.
    These views should pick up the ACTIVE BUSINESS from session/thread-local,
    which we set via set_active_business().
    
    Security: Also checks for a safe 'next' parameter, but only allows internal URLs.
    """
    # Check for a safe 'next' parameter (must be internal URL)
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url:
        allowed_hosts = {request.get_host()}
        if url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts=allowed_hosts,
            require_https=request.is_secure()
        ):
            return next_url
    
    # Default agent-friendly landing pages
    for name in [
        "inventory:scan_sold",           # most agent-centric
        "inventory:inventory_dashboard",  # inventory hub
        "dashboard:home",
        "dashboard:dashboard",
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
            biz_name = _biz_name(inv)
            greet = ctx.get("greeting") or f"Welcome to {biz_name}."
            extra = (
                f"<p><small>Business: {biz_name}</small></p>"
                f"<p><small>{greet}</small></p>"
            )
        return HttpResponse(f"<h1>{title}</h1><p>{body}</p>{extra}", status=status)


# ---------------------------------------------------------------------------
# Business/greeting helpers (for dynamic page copy)
# ---------------------------------------------------------------------------

def _biz_name(invite: AgentInvite) -> str:
    try:
        return (getattr(getattr(invite, "business", None), "name", None) or "").strip() or "this shop"
    except Exception:
        return "this shop"


def _recipient_short(invite: AgentInvite) -> str:
    """
    Choose a friendly recipient label: explicit name → email local-part → 'there'.
    """
    try:
        name = (getattr(invite, "recipient_name", "") or "").strip()
        if name:
            return name
    except Exception:
        pass
    try:
        email = (getattr(invite, "email", "") or "").strip()
        if email and "@" in email:
            return email.split("@", 1)[0]
    except Exception:
        pass
    return "there"


def _greeting(invite: AgentInvite) -> str:
    person = _recipient_short(invite)
    biz = _biz_name(invite)
    return f"Hi {person}, welcome to {biz}."


# ---------------------------------------------------------------------------
# Robust invite lookup (accept token OR code style links)
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
# POST helpers (robust extraction)
# ---------------------------------------------------------------------------

def _post_val(request: HttpRequest, *keys: str) -> str:
    """
    Safe extractor: returns the first non-empty POST value among provided keys.
    """
    for k in keys:
        v = (request.POST.get(k) or "").strip()
        if v:
            return v
    return ""


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

@never_cache
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """
    Redeem an agent invite token/code.

    Policy:
      • Accept ANY valid email (no domain / no invite-email enforcement).
      • Create user if needed; otherwise authenticate (set password if unusable).
      • Accept invite, SET ACTIVE BUSINESS (session + thread-local), redirect to agent view.
    """
    invite: Optional[AgentInvite] = _get_invite_any(token)
    if not invite:
        ctx = {
            "title": "Invalid invite",
            "message": "This invitation link is not valid. Please request a new invite from the manager.",
            "invite": None,
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": None,
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
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "expires_at": getattr(invite, "expires_at", None),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": None,
        }
        return _render_safe(request, "tenants/invites/expired.html", ctx, status=410)

    # If already authenticated: ACCEPT IMMEDIATELY (no email match check)
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            # accept_invite_by_token gets location from the invite automatically
            accept_invite_by_token(token=token, user=request.user, role="AGENT")
        except ValueError as e:
            logger.warning(f"Invite accept ValueError for token {token}: {e}", exc_info=True)
            ctx = {
                "title": "Invite problem",
                "message": str(e) or "This invitation cannot be used. Please ask for a new one.",
                "invite": invite,
                "biz_name": _biz_name(invite),
                "greeting": _greeting(invite),
                "compact": True,
                "active_tab": "",
                "show_search": False,
                "error": str(e) if e else None,
            }
            return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)
        except Exception:
            logger.exception(f"Unexpected error accepting invite for authenticated user, token {token}")
            ctx = {
                "title": "Something went wrong",
                "message": "We couldn't complete your invitation right now. Please try again.",
                "invite": invite,
                "biz_name": _biz_name(invite),
                "greeting": _greeting(invite),
                "compact": True,
                "active_tab": "",
                "show_search": False,
                "error": "An unexpected error occurred",
            }
            return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

        # Pin ACTIVE BUSINESS for this session + thread-local (authoritative)
        try:
            set_active_business(request, invite.business)
        except Exception:
            # ultra-safe fallback
            try:
                biz_id = getattr(getattr(invite, "business", None), "id", None)
                if biz_id:
                    request.session[TENANT_SESSION_KEY] = biz_id
                    request.session.modified = True
            except Exception:
                pass

        try:
            messages.success(request, f"You're now part of {_biz_name(invite)}. Welcome!")
        except Exception:
            pass

        return redirect(_best_post_accept_redirect(request))

    # Not authenticated → show signup page
    if request.method == "GET":
        form = AgentInviteAcceptForm(initial_email=getattr(invite, "email", None) or None)
        # If the invite didn't specify an email, allow the user to enter any email
        if not getattr(invite, "email", None):
            form.fields["email"].disabled = False
            form.fields["email"].required = True

        ctx = {
            "form": form,
            "invite": invite,
            "title": f"Join {_biz_name(invite)}",
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "expires_at": getattr(invite, "expires_at", None),
            "compact": True,  # template can hide app bottom nav for perfect mobile fit
            "active_tab": "",  # suppress base template warning
            "show_search": False,
            "error": None,
        }
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=200)

    # POST: tolerant extraction
    try:
        form = AgentInviteAcceptForm(request.POST, initial_email=getattr(invite, "email", None) or None)
        if not getattr(invite, "email", None):
            form.fields["email"].disabled = False
            form.fields["email"].required = True
    except Exception as e:
        logger.exception(f"Error creating form for invite {token}: {e}")
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't process your form. Please try again or contact support.",
            "invite": invite,
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Form processing error",
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    # If the form isn't valid, re-render with errors (never a blank page)
    if not form.is_valid():
        ctx = {
            "form": form,
            "invite": invite,
            "title": f"Join {_biz_name(invite)}",
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "expires_at": getattr(invite, "expires_at", None),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Please correct the errors below",
        }
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)

    User = get_user_model()

    # Accept ANY email:
    # prefer invite.email; else get from form; else try common POST aliases as last resort
    try:
        email = (
            (getattr(invite, "email", None) or "") or
            (form.cleaned_data.get("email") or "") or
            _post_val(request, "email", "user_email", "username", "login")
        ).lower().strip()
    except Exception as e:
        logger.exception(f"Error extracting email for invite {token}: {e}")
        ctx = {
            "form": form,
            "invite": invite,
            "title": f"Join {_biz_name(invite)}",
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "expires_at": getattr(invite, "expires_at", None),
            "message": "Could not process your email. Please try again.",
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Could not process your email",
        }
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)

    if not email:
        # Inline error instead of a bare "Email required" page
        try:
            form.add_error("email", "Please enter a valid email.")
        except Exception:
            pass
        ctx = {
            "form": form,
            "invite": invite,
            "title": f"Join {_biz_name(invite)}",
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "expires_at": getattr(invite, "expires_at", None),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Email is required",
        }
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)

    password = (
        form.cleaned_data.get("password1") or
        _post_val(request, "password", "password1")
    )

    # Create user if not exists; otherwise require correct password
    try:
        user = User.objects.filter(email__iexact=email).first()
    except Exception as e:
        logger.exception(f"Error querying user for invite {token}: {e}")
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't complete your invitation right now. Please try again.",
            "invite": invite,
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Database error",
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    if user is None:
        # Validate password before creating user (additional safeguard)
        if password:
            try:
                temp_user = User(username=email.split("@")[0], email=email)
                validate_password(password, user=temp_user)
            except ValidationError as e:
                logger.warning(f"Password validation failed for invite {token}: {e}")
                try:
                    for error in e.messages:
                        form.add_error("password1", error)
                except Exception:
                    form.add_error("password1", "Password does not meet security requirements.")
                ctx = {
                    "form": form,
                    "invite": invite,
                    "title": f"Join {_biz_name(invite)}",
                    "biz_name": _biz_name(invite),
                    "greeting": _greeting(invite),
                    "expires_at": getattr(invite, "expires_at", None),
                    "message": "Password does not meet security requirements.",
                    "compact": True,
                    "active_tab": "",
                    "show_search": False,
                    "error": "Weak password",
                }
                return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)
        
        try:
            username = _unique_username_from_email(email)
            user = User.objects.create_user(username=username, email=email, password=password or "changeme-now")
            if not password:
                # ensure the account is usable even if password missing
                user.set_password("changeme-now")
                user.save(update_fields=["password"])
            logger.info(f"Created new user {user.username} ({email}) for invite {token}")
        except Exception as e:
            logger.exception(f"Error creating user for invite {token}: {e}")
            ctx = {
                "form": form,
                "invite": invite,
                "title": f"Join {_biz_name(invite)}",
                "biz_name": _biz_name(invite),
                "greeting": _greeting(invite),
                "expires_at": getattr(invite, "expires_at", None),
                "message": "Could not create your account. This email may already be in use.",
                "compact": True,
                "active_tab": "",
                "show_search": False,
                "error": "Account creation failed",
            }
            return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)
    else:
        # If account exists and has a usable password, authenticate
        if user.has_usable_password():
            if not password:
                try:
                    form.add_error("password1", "Enter the existing account password.")
                except Exception:
                    pass
                ctx = {
                    "form": form,
                    "invite": invite,
                    "title": f"Join {_biz_name(invite)}",
                    "biz_name": _biz_name(invite),
                    "greeting": _greeting(invite),
                    "message": "An account with this email already exists. Please enter its correct password.",
                    "compact": True,
                    "active_tab": "",
                    "show_search": False,
                    "error": "Password required for existing account",
                }
                return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)
            auth_ok = authenticate(request, username=user.username, password=password)
            if not auth_ok:
                try:
                    form.add_error("password1", "Incorrect password for existing account.")
                except Exception:
                    pass
                ctx = {
                    "form": form,
                    "invite": invite,
                    "title": f"Join {_biz_name(invite)}",
                    "biz_name": _biz_name(invite),
                    "greeting": _greeting(invite),
                    "message": "Incorrect password for existing account.",
                    "compact": True,
                    "active_tab": "",
                    "show_search": False,
                    "error": "Incorrect password",
                }
                return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)
        else:
            # If no usable password, set one now
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])

    # Log in (authenticate if possible; otherwise force login)
    try:
        auth_user = None
        if password:
            auth_user = authenticate(request, username=user.username, password=password)
        if auth_user is None:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        else:
            login(request, auth_user)
        logger.info(f"User {user.username} logged in via invite {token}")
    except Exception as e:
        logger.exception(f"Error logging in user for invite {token}: {e}")
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't log you in. Please try signing in manually.",
            "invite": invite,
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Login failed",
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    # Accept the invite
    try:
        # accept_invite_by_token gets location from the invite automatically
        accept_invite_by_token(token=token, user=request.user, role="AGENT")
    except ValueError as e:
        logger.warning(f"Invite accept ValueError for token {token} after user creation: {e}", exc_info=True)
        ctx = {
            "title": "Invite problem",
            "message": str(e) or "This invitation cannot be used. Please ask for a new one.",
            "invite": invite,
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": str(e) if e else "Invite cannot be used",
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)
    except Exception:
        logger.exception(f"Unexpected error accepting invite after user creation, token {token}")
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't complete your invitation right now. Please try again.",
            "invite": invite,
            "biz_name": _biz_name(invite),
            "greeting": _greeting(invite),
            "compact": True,
            "active_tab": "",
            "show_search": False,
            "error": "Unexpected error",
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    # AUTHORITATIVE: set active business (session + thread-local) so agent UI opens in the right tenant
    try:
        set_active_business(request, invite.business)
    except Exception:
        # ultra-safe fallback
        try:
            biz_id = getattr(getattr(invite, "business", None), "id", None)
            if biz_id:
                request.session[TENANT_SESSION_KEY] = biz_id
                request.session.modified = True
        except Exception:
            pass

    try:
        messages.success(request, f"You're now part of {_biz_name(invite)}. Welcome!")
    except Exception:
        pass

    return redirect(_best_post_accept_redirect(request))
