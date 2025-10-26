# tenants/views_invites.py
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import get_user_model, login, authenticate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from tenants.models import AgentInvite
from tenants.services.invites import accept_invite_by_token
from .forms import AgentInviteAcceptForm


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
    your dashboards if available, then tenant activator/switcher, then home.
    """
    for name in [
        "dashboard:home",
        "dashboard:dashboard",
        "inventory:inventory_dashboard",
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
    Try to render a template; if it's missing, fall back to a tiny inline page
    so the flow never crashes in dev.
    """
    try:
        return render(request, template, ctx, status=status)
    except Exception:
        # Minimal fallback HTML (kept very short)
        title = ctx.get("title", "Invitation")
        body = ctx.get("message", "")
        extra = ""
        inv = ctx.get("invite")
        if inv:
            extra = f"<p><small>Business: {getattr(getattr(inv, 'business', None), 'name', '—')}</small></p>"
        return HttpResponse(f"<h1>{title}</h1><p>{body}</p>{extra}", status=status)


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

@never_cache
@require_http_methods(["GET", "POST"])
def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """
    Redeem an agent invite token.

    Updated Flow:
      - Locate invite by token; show invalid if not found.
      - If expired → mark EXPIRED and show 'expired'.
      - If authenticated and email matches invite (when invite has email), accept immediately (idempotent).
      - If not authenticated → show signup form with invited email prefilled/locked
        (or editable if invite has no email). On submit, create user, set password,
        log them in, accept invite, and redirect.
    """
    # 1) Find the invite quickly (no exceptions)
    invite: Optional[AgentInvite] = (
        AgentInvite.all_objects.filter(token=token).select_related("business").first()
    )
    if not invite:
        ctx = {
            "title": "Invalid invite",
            "message": "This invitation link is not valid. Please request a new invite from the manager.",
            "invite": None,
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=404)

    # 2) Expiry (and explicit EXPIRED status) check
    if invite.is_expired():
        # Keep status consistent
        if (invite.status or "").upper() != "EXPIRED":
            invite.status = "EXPIRED"
            try:
                invite.save(update_fields=["status"])
            except Exception:
                pass

        ctx = {
            "title": "Invite expired",
            "message": "This invitation has expired. Ask your manager to resend a new link.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/expired.html", ctx, status=410)

    # 3) If already authenticated and (if invite has email) it matches → accept directly
    if getattr(request, "user", None) and request.user.is_authenticated:
        invited_email = (invite.email or "").lower().strip()
        if invited_email and request.user.email.lower().strip() != invited_email:
            # Logged-in user is not the invited email: block to prevent hijack.
            ctx = {
                "title": "Wrong account",
                "message": "You are signed in as a different user than the invited email. "
                           "Please sign out and open the link again, or ask your manager to resend the invite.",
                "invite": invite,
            }
            return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)

        # Accept (idempotent) and attach membership
        try:
            accept_invite_by_token(token=token, user=request.user, role="AGENT")
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

        try:
            messages.success(
                request,
                f"You're now part of {getattr(invite.business, 'name', 'the business')}. Welcome!",
            )
        except Exception:
            pass

        return redirect(_best_post_accept_redirect(request))

    # 4) Not authenticated → show signup page that lets the invitee set a password
    #    Email is prefilled and locked if the invite has an email; otherwise user must provide one.
    if request.method == "GET":
        form = AgentInviteAcceptForm(initial_email=invite.email or None)
        if not invite.email:
            form.fields["email"].disabled = False
            form.fields["email"].required = True
        ctx = {"form": form, "invite": invite, "title": "Join as Agent"}
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=200)

    # POST: create (or update) user with new password, then accept
    form = AgentInviteAcceptForm(request.POST, initial_email=invite.email or None)
    if not invite.email:
        form.fields["email"].disabled = False
        form.fields["email"].required = True

    if not form.is_valid():
        ctx = {"form": form, "invite": invite, "title": "Join as Agent"}
        return _render_safe(request, "tenants/invite_accept.html", ctx, status=400)

    User = get_user_model()
    email = (invite.email or form.cleaned_data.get("email") or "").lower().strip()
    if not email:
        ctx = {
            "title": "Email required",
            "message": "Please enter a valid email address to continue.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)

    password = form.cleaned_data["password1"]

    # Create or update the user
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"username": email.split("@")[0]},
    )
    user.set_password(password)
    user.save()

    # Log them in
    # Some projects require a backend path; default backend should work.
    user_auth = authenticate(request, username=user.username, password=password)
    if user_auth is None:
        # fallback login without re-authenticate (rare backends)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    else:
        login(request, user_auth)

    # Accept (idempotent) and attach membership
    try:
        accept_invite_by_token(token=token, user=request.user, role="AGENT")
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

    try:
        messages.success(
            request,
            f"You're now part of {getattr(invite.business, 'name', 'the business')}. Welcome!",
        )
    except Exception:
        pass

    return redirect(_best_post_accept_redirect(request))
