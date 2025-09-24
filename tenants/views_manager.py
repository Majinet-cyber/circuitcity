# tenants/views_manager.py
from __future__ import annotations

from typing import Optional, List

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.template.loader import select_template

from tenants.models import Business, Membership
from tenants.services.invites import (
    create_agent_invite,
    invites_for_business,
    pending_invites_for_business,
    annotate_shares,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_business_from_request(request: HttpRequest) -> Optional[Business]:
    """
    Resolve the active tenant without raising.
    Priority:
      1) request.active_business (if middleware set it)
      2) request.business (alternate attr you used elsewhere)
      3) session['active_business_id'] → DB lookup
    """
    biz = getattr(request, "active_business", None) or getattr(request, "business", None)
    if biz:
        return biz

    bid = None
    try:
        bid = request.session.get("active_business_id")
    except Exception:
        pass

    if not bid:
        return None

    try:
        return Business.objects.get(pk=bid)  # not tenant-scoped manager
    except Business.DoesNotExist:
        return None


def _active_agents_for_business(biz: Business) -> List[Membership]:
    """
    Return ACTIVE members for display under 'Active agents'.
    Managers are often shown here too, but you can filter to AGENT only if you like.
    """
    return list(
        Membership.objects.filter(business=biz, status="ACTIVE")
        .order_by("role", "-created_at")
        .select_related("user", "business")
    )


def _render_agents_template(request: HttpRequest, ctx: dict) -> HttpResponse:
    """
    Prefer your existing template path, but gracefully accept common aliases
    so future renames don’t 500 the page.
    """
    tpl = select_template([
        "tenants/manager_review_agents.html",  # your existing file
        "tenants/manager/agents.html",         # alias some code referenced
        "tenants/manager_agents.html",         # legacy alias just in case
    ])
    return HttpResponse(tpl.render(ctx, request))


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def manager_agents(request: HttpRequest) -> HttpResponse:
    """
    Agents dashboard:
      - GET: show active members + invites (pending/accepted/etc.)
      - POST: create an invite (name/email/phone are optional)
    Only minimal logic here; link generation lives on the model.
    """
    biz = _active_business_from_request(request)
    if not biz:
        messages.error(request, "Please select a business first.")
        # If you have a business switcher route, go there; else go home.
        return redirect("/")

    # --- Handle invite creation (POST) -------------------------------------
    if request.method == "POST":
        invited_name = (request.POST.get("invited_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        ttl_days = request.POST.get("ttl_days")
        message_text = (request.POST.get("message") or "").strip()

        try:
            ttl_val = int(ttl_days) if ttl_days else 7
        except Exception:
            ttl_val = 7

        try:
            create_agent_invite(
                tenant=biz,
                created_by=getattr(request, "user", None),
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_val,
                message=message_text,
                mark_sent=True,
            )
            messages.success(request, "Invitation created.")
            # PRG pattern to avoid resubmission on refresh
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f"Could not create invite: {e}")

    # --- Read-only data for display ----------------------------------------
    active_members = _active_agents_for_business(biz)

    invites_all = invites_for_business(biz)
    invites_pending = pending_invites_for_business(biz)

    # Attach share links/buttons (computed by AgentInvite.share_payload)
    invites_all = annotate_shares(invites_all, request)
    invites_pending = annotate_shares(invites_pending, request)

    # Some UIs like to show other buckets too:
    invites_accepted = [i for i in invites_all if (i.status or "").upper() == "JOINED"]
    invites_expired = [i for i in invites_all if i.is_expired()]
    invites_declined = []  # not tracked as a distinct status in this model
    invites_revoked = []   # revoke → EXPIRED (keeps model simple)

    ctx = {
        "tenant": biz,
        "active_members": active_members,

        # Tabs/filters
        "invites_all": invites_all,
        "invites_pending": invites_pending,
        "invites_accepted": invites_accepted,
        "invites_expired": invites_expired,
        "invites_declined": invites_declined,
        "invites_revoked": invites_revoked,

        # Convenience flags for template conditions
        "has_pending": bool(invites_pending),
        "has_any_invites": bool(invites_all),
    }

    return _render_agents_template(request, ctx)
