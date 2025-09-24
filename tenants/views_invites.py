# tenants/views_invites.py
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, NoReverseMatch
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from tenants.models import AgentInvite
from tenants.services.invites import accept_invite_by_token


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
        body  = ctx.get("message", "")
        extra = ""
        inv = ctx.get("invite")
        if inv:
            extra = f"<p><small>Business: {getattr(getattr(inv, 'business', None), 'name', '—')}</small></p>"
        return HttpResponse(f"<h1>{title}</h1><p>{body}</p>{extra}", status=status)


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

@never_cache
@require_http_methods(["GET"])
def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """
    Redeem an agent invite token.

    Flow:
      - If token invalid → show 'invalid invite' page (404).
      - If expired → mark EXPIRED and show 'expired' page (410).
      - If user not authenticated → redirect to login with ?next back here.
      - If authenticated → attach membership (idempotent) and redirect to app.
    """
    # 1) Find the invite quickly (no exceptions)
    invite: Optional[AgentInvite] = AgentInvite.all_objects.filter(token=token).select_related("business").first()
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

    # 3) Require login (preserve round-trip with next)
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        login_url = _reverse_or("accounts:login", "/accounts/login/")
        next_url = request.get_full_path()  # /tenants/invites/accept/<token>/
        return redirect(f"{login_url}?next={quote(next_url, safe='/:?=&')}")

    # 4) Accept (idempotent) and attach membership
    try:
        accept_invite_by_token(token=token, user=request.user, role="AGENT")
    except ValueError as e:
        # Token invalid or expired between the checks above; show a safe message
        ctx = {
            "title": "Invite problem",
            "message": str(e) or "This invitation cannot be used. Please ask for a new one.",
            "invite": invite,
        }
        # Treat as 400 Bad Request
        return _render_safe(request, "tenants/invites/invalid.html", ctx, status=400)
    except Exception as e:
        # Unexpected edge; don't leak internals
        ctx = {
            "title": "Something went wrong",
            "message": "We couldn't complete your invitation right now. Please try again.",
            "invite": invite,
        }
        return _render_safe(request, "tenants/invites/error.html", ctx, status=500)

    # 5) Success
    try:
        messages.success(
            request,
            f"You're now part of {getattr(invite.business, 'name', 'the business')}. Welcome!"
        )
    except Exception:
        pass

    return redirect(_best_post_accept_redirect(request))
