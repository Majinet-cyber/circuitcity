# tenants/views_manager.py
from __future__ import annotations

from typing import Optional, List, Iterable, Any, Dict, Callable
import inspect
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.template.loader import select_template

from tenants.models import Business, Membership
# Optional: AgentInvite for local fallback
try:
    from tenants.models import AgentInvite  # type: ignore
except Exception:  # pragma: no cover
    AgentInvite = None  # type: ignore

from tenants.services.invites import (
    create_agent_invite as create_agent_invite_service,
    invites_for_business,
    pending_invites_for_business,
    annotate_shares,
)

# ---------------------------------------------------------------------------
# Active business helpers (self-contained & legacy-friendly)
# ---------------------------------------------------------------------------

ACTIVE_BIZ_KEYS = ("active_business_id", "biz_id")  # session keys we accept


def _set_active_on_request_and_session(request: HttpRequest, biz: Business) -> None:
    """Persist chosen business on both request and session (covers legacy keys)."""
    try:
        request.business = biz
        request.active_business = biz
        bid = getattr(biz, "id", None)
        request.active_business_id = bid
        request.session["active_business_id"] = bid
        request.session["biz_id"] = bid  # legacy
        request.session.modified = True
    except Exception:
        pass


def _active_business_from_request(request: HttpRequest) -> Optional[Business]:
    """
    Get currently active business from request or session (safe, no raises).
    Order:
      1) request.business / request.active_business
      2) session['active_business_id'] / session['biz_id']
    """
    biz = getattr(request, "business", None) or getattr(request, "active_business", None)
    if isinstance(biz, Business):
        return biz

    bid = None
    try:
        for k in ACTIVE_BIZ_KEYS:
            bid = request.session.get(k)
            if bid:
                break
    except Exception:
        bid = None

    if not bid:
        return None

    try:
        return Business.objects.get(pk=bid)
    except Business.DoesNotExist:
        return None


def _force_pick_any_membership(request: HttpRequest) -> Optional[Business]:
    """If user has ANY membership, pick the first and set it active."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    try:
        m = (
            Membership.objects.filter(user=user)
            .select_related("business")
            .order_by("id")
            .first()
        )
        if m and m.business:
            _set_active_on_request_and_session(request, m.business)
            return m.business
    except Exception:
        pass
    return None


def _active_agents_for_business(biz: Business) -> List[Membership]:
    """Return members for display (prefer ACTIVE when available, but never fail)."""
    qs = Membership.objects.filter(business=biz).select_related("user", "business")

    # Prefer ACTIVE if the field exists and there are any active rows.
    try:
        field_names = {f.name for f in Membership._meta.fields}
        if "status" in field_names:
            qs_active = qs.filter(status="ACTIVE")
            if qs_active.exists():
                qs = qs_active
    except Exception:
        pass

    try:
        return list(qs.order_by("role", "-created_at"))
    except Exception:
        return list(qs.order_by("role", "-id"))


def _render_agents_template(request: HttpRequest, ctx: dict) -> HttpResponse:
    """Render primary template, with fallbacks if the path changes."""
    tpl = select_template(
        [
            "tenants/manager_review_agents.html",  # primary
            "tenants/manager/agents.html",         # alias
            "tenants/manager_agents.html",         # legacy alias
        ]
    )
    return HttpResponse(tpl.render(ctx, request))


# ---------------------------------------------------------------------------
# Invite creation â€“ service call with safe fallback
# ---------------------------------------------------------------------------

def _local_fallback_create_invite(
    *,
    business: Business,
    requested_by,
    invited_name: str,
    email: str,
    phone: str,
    ttl_days: int,
    message: str,
) -> Any:
    """
    Minimal local creator using AgentInvite model if available.
    annotate_shares() later adds share_url/copy strings for display.
    """
    if AgentInvite is None:  # type: ignore[truthy-bool]
        raise RuntimeError(
            "Invite service signature invalid and AgentInvite model is unavailable for fallback."
        )

    mdl_fields = {f.name for f in AgentInvite._meta.fields}  # type: ignore[attr-defined]
    data: Dict[str, Any] = {}

    def put(field: str, value: Any) -> None:
        if field in mdl_fields:
            data[field] = value

    put("business", business)
    put("invited_name", invited_name or "")
    put("name", invited_name or "")
    put("email", email or "")
    put("phone", phone or "")
    put("message", message or "")
    put("status", "UNATTENDED")
    put("created_by", requested_by)
    put("created_at", datetime.utcnow())
    if "token" in mdl_fields:
        data["token"] = uuid.uuid4().hex
    if "code" in mdl_fields and "token" not in mdl_fields:
        data["code"] = uuid.uuid4().hex[:12]
    if "expires_at" in mdl_fields:
        data["expires_at"] = datetime.utcnow() + timedelta(days=max(1, ttl_days))

    inv = AgentInvite.objects.create(**data)  # type: ignore[attr-defined]
    return inv


def _safe_service_create_invite(
    *,
    business: Business,
    requested_by,
    invited_name: str,
    email: str,
    phone: str,
    ttl_days: int,
    message: str,
) -> Any:
    """
    Call tenants.services.invites.create_agent_invite if compatible.
    If its signature is 0-arg or mismatched, fall back to a local creator.
    """
    fn: Callable[..., Any] = create_agent_invite_service

    try:
        sig = inspect.signature(fn)
        if len(sig.parameters) == 0:
            return _local_fallback_create_invite(
                business=business,
                requested_by=requested_by,
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_days,
                message=message,
            )
    except Exception:
        # If we can't inspect, try and catch TypeError below
        pass

    try:
        return fn(
            tenant=business,
            created_by=requested_by,
            invited_name=invited_name,
            email=email,
            phone=phone,
            ttl_days=ttl_days,
            message=message,
            mark_sent=True,
        )
    except TypeError as te:
        msg = str(te)
        if (
            "positional arguments" in msg
            or "unexpected keyword" in msg
            or "takes 0 positional arguments" in msg
        ):
            return _local_fallback_create_invite(
                business=business,
                requested_by=requested_by,
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_days,
                message=message,
            )
        raise


def _invite_accept_absolute_url(request: HttpRequest, inv: Any) -> str:
    """
    Best-effort way to produce an accept URL for the newly created invite.
    Looks for common token-ish fields; falls back to empty string.
    """
    token = None
    for f in ("token", "code", "uid", "uuid", "slug", "key"):
        try:
            v = getattr(inv, f, None)
            if v:
                token = str(v)
                break
        except Exception:
            pass
    if not token:
        return ""
    try:
        rel = reverse("tenants:invite_accept", args=[token])
        return request.build_absolute_uri(rel)
    except Exception:
        return ""


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
      - GET: show members + invites
      - POST: create an invite (convenience: posting back to same URL also works)
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.warning(request, "Please choose a business first.")
        return redirect("tenants:choose_business")

    # Handle POST here too (in case the form posts to this URL)
    if request.method == "POST":
        invited_name = (request.POST.get("invited_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        ttl_days = (request.POST.get("ttl_days") or "").strip()
        message_text = (request.POST.get("message") or "").strip()
        try:
            ttl_val = int(ttl_days) if ttl_days else 7
        except Exception:
            ttl_val = 7

        try:
            inv = _safe_service_create_invite(
                business=biz,
                requested_by=getattr(request, "user", None),
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_val,
                message=message_text,
            )
            latest_link = _invite_accept_absolute_url(request, inv)
            messages.success(request, "Invitation created.")
            url = reverse("tenants:manager_review_agents")
            if latest_link:
                url = f"{url}?latest_link={quote(latest_link)}"
            return redirect(url)  # PRG
        except Exception as e:
            messages.error(request, f"Could not create invite: {e}")

    # ----- Read-only data for display -----
    active_members: List[Membership] = _active_agents_for_business(biz)

    def _safe_iter(x: Iterable) -> list:
        try:
            return list(x)
        except Exception:
            return []

    invites_all = annotate_shares(_safe_iter(invites_for_business(biz)), request)
    invites_pending = annotate_shares(_safe_iter(pending_invites_for_business(biz)), request)

    # Accepted / joined
    invites_accepted = [
        i for i in invites_all
        if (getattr(i, "status", "") or "").upper() in {"JOINED", "ACCEPTED", "ACTIVE"}
    ]

    # Expired (supports method or boolean/property)
    def _is_expired(x) -> bool:
        try:
            fn = getattr(x, "is_expired", None)
            return fn() if callable(fn) else bool(fn)
        except Exception:
            return False

    invites_expired = [i for i in invites_all if _is_expired(i)]
    invites_declined, invites_revoked = [], []

    ctx = {
        "tenant": biz,
        "active_members": active_members,
        "invites_all": invites_all,
        "invites_pending": invites_pending,
        "invites_accepted": invites_accepted,
        "invites_expired": invites_expired,
        "invites_declined": invites_declined,
        "invites_revoked": invites_revoked,
        "has_pending": bool(invites_pending),
        "has_any_invites": bool(invites_all),
    }
    return _render_agents_template(request, ctx)


# ---------------------------------------------------------------------------
# Standalone POST endpoint for the form at /tenants/manager/agents/invite/
# ---------------------------------------------------------------------------

@never_cache
@login_required
@require_http_methods(["POST"])
@transaction.atomic
def create_agent_invite(request: HttpRequest) -> HttpResponse:
    """
    Dedicated POST view so {% url 'tenants:create_agent_invite' %} works.
    It uses the same safe invite creation as the inline POST above,
    then redirects back to the agents page (PRG) with ?latest_link=...
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.error(request, "Please select a business first.")
        return redirect("tenants:manager_review_agents")

    invited_name = (request.POST.get("invited_name") or "").strip()
    email = (request.POST.get("email") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    ttl_days = (request.POST.get("ttl_days") or "").strip()
    message_text = (request.POST.get("message") or "").strip()
    try:
        ttl_val = int(ttl_days) if ttl_days else 7
    except Exception:
        ttl_val = 7

    try:
        inv = _safe_service_create_invite(
            business=biz,
            requested_by=getattr(request, "user", None),
            invited_name=invited_name,
            email=email,
            phone=phone,
            ttl_days=ttl_val,
            message=message_text,
        )
        latest_link = _invite_accept_absolute_url(request, inv)
        messages.success(request, "Invitation created.")
        url = reverse("tenants:manager_review_agents")
        if latest_link:
            url = f"{url}?latest_link={quote(latest_link)}"
        return redirect(url)
    except Exception as e:
        messages.error(request, f"Could not create invite: {e}")
        return redirect("tenants:manager_review_agents")


