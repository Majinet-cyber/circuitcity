from __future__ import annotations

from typing import Optional, List, Iterable, Any, Dict, Callable
import inspect
import uuid
from datetime import timedelta
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
from django.utils import timezone

from tenants.models import Business, Membership
from tenants.utils import redirect_manager_safe_choose

# Optional: AgentInvite & Location for local fallback
try:
    from tenants.models import AgentInvite  # type: ignore
except Exception:  # pragma: no cover
    AgentInvite = None  # type: ignore
try:
    from tenants.models import Location  # type: ignore
except Exception:  # pragma: no cover
    Location = None  # type: ignore

# Optional services (we'll call them defensively)
try:
    from tenants.services.invites import (  # type: ignore
        create_agent_invite as create_agent_invite_service,
        invites_for_business,
        pending_invites_for_business,
        annotate_shares,
    )
except Exception:  # pragma: no cover
    # Soft fallbacks if services module or names are missing
    def create_agent_invite_service(*args, **kwargs):  # type: ignore
        raise RuntimeError("create_agent_invite service is unavailable")

    def invites_for_business(_biz):  # type: ignore
        return []

    def pending_invites_for_business(_biz):  # type: ignore
        return []

    def annotate_shares(items, _request=None):  # type: ignore
        return list(items)


# ---------------------------------------------------------------------------
# Active business helpers
# ---------------------------------------------------------------------------

ACTIVE_BIZ_KEYS = ("active_business_id", "biz_id")  # session keys we accept


def _set_active_on_request_and_session(request: HttpRequest, biz: Business) -> None:
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
    """Return all agent memberships (active and suspended) for this business."""
    qs = Membership.objects.filter(business=biz, role="AGENT").select_related("user", "business", "location")
    try:
        # Include both ACTIVE and SUSPENDED, exclude only REJECTED
        field_names = {f.name for f in Membership._meta.fields}
        if "status" in field_names:
            qs = qs.exclude(status="REJECTED")
    except Exception:
        pass
    try:
        return list(qs.order_by("-created_at"))
    except Exception:
        return list(qs.order_by("-id"))


def _render_agents_template(request: HttpRequest, ctx: dict) -> HttpResponse:
    tpl = select_template(
        [
            "tenants/manager_review_agents.html",  # primary
            "tenants/manager/agents.html",         # alias
            "tenants/manager_agents.html",         # legacy alias
        ]
    )
    return HttpResponse(tpl.render(ctx, request))


# ---------------------------------------------------------------------------
# Share helpers (ensure template fields exist even if services are no-op)
# ---------------------------------------------------------------------------

def _invite_accept_absolute_url(request: HttpRequest, inv: Any) -> str:
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


def _ensure_share_urls(request: HttpRequest, items: Iterable[Any]) -> List[Any]:
    """
    Guarantee that each item has .share_url (using invite token/code if needed).
    """
    result: List[Any] = []
    for i in items:
        try:
            has = getattr(i, "share_url", None)
        except Exception:
            has = None
        if not has:
            try:
                url = _invite_accept_absolute_url(request, i)
                if url:
                    setattr(i, "share_url", url)
            except Exception:
                pass
        result.append(i)
    return result


def _attach_share_fields(request: HttpRequest, biz: Business, items: Iterable[Any]) -> List[Any]:
    """
    Ensure every invite has share_url, share_copy_text, share_wa, share_mailto.
    Template code relies on these.
    """
    out: List[Any] = []
    biz_name = getattr(biz, "name", "") or "your shop"
    for i in items:
        try:
            url = getattr(i, "share_url", None) or _invite_accept_absolute_url(request, i)
            if url:
                setattr(i, "share_url", url)
                display_name = getattr(i, "display_name", None) or getattr(i, "invited_name", None) or "there"
                msg = f"Hi {display_name}, please click this link to join {biz_name}: {url}"
                setattr(i, "share_copy_text", msg)
                setattr(i, "share_wa", f"https://wa.me/?text={quote(msg)}")
                setattr(i, "share_mailto", f"mailto:?subject={quote('Join ' + biz_name)}&body={quote(msg)}")
        except Exception:
            # Best effort; proceed
            pass
        out.append(i)
    return out


def _latest_share_text(latest_link: str, biz_name: str) -> str:
    return f"Share: Hi there, please click this link to join {biz_name}: {latest_link}"


# ---------------------------------------------------------------------------
# Invite creation – service call with safe fallback
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
    location_id: Optional[int] = None,
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
    put("created_at", timezone.now())
    if "token" in mdl_fields:
        data["token"] = uuid.uuid4().hex
    if "code" in mdl_fields and "token" not in mdl_fields:
        data["code"] = uuid.uuid4().hex[:12]
    if "expires_at" in mdl_fields:
        data["expires_at"] = timezone.now() + timedelta(days=max(1, ttl_days))
    # Optional: location for later membership.location
    if location_id and ("location_id" in mdl_fields or "location" in mdl_fields):
        data["location_id"] = location_id

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
    location_id: Optional[int] = None,
) -> tuple:
    """
    Call tenants.services.invites.create_agent_invite if compatible.
    If its signature is 0-arg or mismatched, fall back to a local creator.
    Returns: (invite, temp_password_plaintext or None)
    """
    fn: Callable[..., Any] = create_agent_invite_service

    try:
        sig = inspect.signature(fn)
        if len(sig.parameters) == 0:
            result = _local_fallback_create_invite(
                business=business,
                requested_by=requested_by,
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_days,
                message=message,
                location_id=location_id,
            )
            # Ensure it's a tuple
            return (result, None) if not isinstance(result, tuple) else result
    except Exception:
        pass

    # Try the rich service call; include location if supported.
    try:
        kwargs = dict(
            tenant=business,
            created_by=requested_by,
            invited_name=invited_name,
            email=email,
            phone=phone,
            ttl_days=ttl_days,
            message=message,
            mark_sent=True,
            generate_temp_password=True,  # ✅ Enable password generation
        )
        if location_id is not None:
            # Location model needs to be loaded
            try:
                from inventory.models import Location
                location = Location.objects.get(pk=location_id, business=business)
                kwargs["location"] = location
            except Exception:
                pass
        result = fn(**kwargs)
        # Service returns (invite, temp_password)
        return result if isinstance(result, tuple) else (result, None)
    except TypeError as te:
        msg = str(te)
        if (
            "positional arguments" in msg
            or "unexpected keyword" in msg
            or "takes 0 positional arguments" in msg
        ):
            result = _local_fallback_create_invite(
                business=business,
                requested_by=requested_by,
                invited_name=invited_name,
                email=email,
                phone=phone,
                ttl_days=ttl_days,
                message=message,
                location_id=location_id,
            )
            return (result, None) if not isinstance(result, tuple) else result
        raise


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
      - POST: create an invite (posting here works too)
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.warning(request, "Please choose a business first.")
        return redirect_manager_safe_choose(request)

    # Handle POST creation here too (inline create)
    if request.method == "POST":
        action = request.POST.get("action", "")
        
        # Handle commission settings update
        if action == "update_commission_settings":
            try:
                from decimal import Decimal
                from sales.models import CommissionConfig
                
                config = CommissionConfig.ensure_config(biz)
                
                commissions_enabled = request.POST.get('commissions_enabled') == 'on'
                commission_mode = request.POST.get('commission_mode', 'PERCENT')
                
                # Validate mode
                if commission_mode not in ['PERCENT', 'FIXED']:
                    commission_mode = 'PERCENT'
                
                # Get values
                base_commission_pct = Decimal(request.POST.get('base_commission_pct', '12.00'))
                fixed_commission_amount = Decimal(request.POST.get('fixed_commission_amount', '2000.00'))
                
                # Validate ranges
                if base_commission_pct < 0 or base_commission_pct > 100:
                    messages.error(request, "Commission percentage must be between 0 and 100.")
                    return redirect(request.path)
                
                if fixed_commission_amount < 0:
                    messages.error(request, "Fixed commission amount must be non-negative.")
                    return redirect(request.path)
                
                # Update config
                config.commissions_enabled = commissions_enabled
                config.commission_mode = commission_mode
                config.base_commission_pct = base_commission_pct
                config.fixed_commission_amount = fixed_commission_amount
                config.save()
                
                messages.success(request, "Commission settings updated successfully.")
                return redirect(reverse("tenants:manager_review_agents"))
                
            except ValueError as e:
                messages.error(request, f"Invalid number format: {e}")
            except Exception as e:
                messages.error(request, f"Failed to update settings: {e}")
        else:
            # Original invite creation logic
            invited_name = (request.POST.get("invited_name") or "").strip()
            email = (request.POST.get("email") or "").strip()
            phone = (request.POST.get("phone") or "").strip()
            ttl_days = (request.POST.get("ttl_days") or "").strip()
            message_text = (request.POST.get("message") or "").strip()
            loc_id = (request.POST.get("location_id") or "").strip()
            try:
                ttl_val = int(ttl_days) if ttl_days else 7
            except Exception:
                ttl_val = 7
            try:
                location_id = int(loc_id) if loc_id else None
            except Exception:
                location_id = None

            try:
                inv, temp_password = _safe_service_create_invite(
                    business=biz,
                    requested_by=getattr(request, "user", None),
                    invited_name=invited_name,
                    email=email,
                    phone=phone,
                    ttl_days=ttl_val,
                    message=message_text,
                    location_id=location_id,
                )
                latest_link = _invite_accept_absolute_url(request, inv)
                messages.success(request, "Invitation created.")
                url = reverse("tenants:manager_review_agents")
                # Pass both link and password via URL params (one-time display)
                if latest_link:
                    url = f"{url}?latest_link={quote(latest_link)}"
                if temp_password:
                    url = f"{url}&temp_password={quote(temp_password)}"
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

    # Pull lists (services may be no-op in local envs)
    invites_all = annotate_shares(_safe_iter(invites_for_business(biz)), request)
    invites_pending = annotate_shares(_safe_iter(pending_invites_for_business(biz)), request)

    # Always ensure downstream template fields exist
    invites_all = _ensure_share_urls(request, invites_all)
    invites_pending = _ensure_share_urls(request, invites_pending)
    invites_all = _attach_share_fields(request, biz, invites_all)
    invites_pending = _attach_share_fields(request, biz, invites_pending)

    # Accepted / joined
    invites_accepted = [
        i for i in invites_all
        if (getattr(i, "status", "") or "").upper() in {"JOINED", "ACCEPTED", "ACTIVE"}
    ]

    # Expired helper
    def _is_expired(x) -> bool:
        try:
            fn = getattr(x, "is_expired", None)
            return fn() if callable(fn) else bool(fn)
        except Exception:
            # derive from expires_at
            try:
                exp = getattr(x, "expires_at", None)
                return bool(exp and exp <= timezone.now())
            except Exception:
                return False

    invites_expired = [i for i in invites_all if _is_expired(i)]
    invites_declined, invites_revoked = [], []  # reserved for future filters

    # Optional: provide locations list for template select (if model exists)
    locations = []
    try:
        if Location is not None:
            locations = list(Location.objects.filter(business=biz).order_by("name"))  # type: ignore
    except Exception:
        locations = []

    latest_link = (request.GET.get("latest_link") or "").strip()
    temp_password = (request.GET.get("temp_password") or "").strip()  # ✅ One-time password display
    latest_share = _latest_share_text(latest_link, getattr(biz, "name", "") or "your shop") if latest_link else ""

    # Get commission config
    commission_config = None
    try:
        from sales.models import CommissionConfig
        commission_config = CommissionConfig.ensure_config(biz)
    except Exception:
        pass

    ctx = {
        "tenant": biz,
        "config": commission_config,     # Commission settings
        "active_members": active_members,
        "invites_all": invites_all,
        "invites_pending": invites_pending,
        "invites_accepted": invites_accepted,
        "invites_expired": invites_expired,
        "invites_declined": invites_declined,
        "invites_revoked": invites_revoked,
        "has_pending": bool(invites_pending),
        "has_any_invites": bool(invites_all),
        "locations": locations,          # for optional location dropdown
        "latest_link": latest_link,      # makes share box show the latest link
        "temp_password": temp_password,  # ✅ Temporary password (one-time display)
        "latest_share": latest_share,    # small helper text shown under share box
    }
    return _render_agents_template(request, ctx)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def manager_commission_settings(request: HttpRequest) -> HttpResponse:
    """
    Manager-only: Configure commission settings (PERCENT or FIXED, and ON/OFF toggle).
    
    GET: Show current settings
    POST: Update settings
    """
    from decimal import Decimal
    from sales.models import CommissionConfig
    
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.warning(request, "Please choose a business first.")
        return redirect_manager_safe_choose(request)
    
    # Check manager permission
    user = getattr(request, "user", None)
    is_manager = False
    if user and user.is_authenticated:
        if user.is_staff or user.is_superuser:
            is_manager = True
        else:
            # Check membership
            try:
                membership = Membership.objects.filter(
                    user=user,
                    business=biz,
                    status='ACTIVE'
                ).first()
                if membership and membership.role in ['MANAGER', 'OWNER']:
                    is_manager = True
            except Exception:
                pass
    
    if not is_manager:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Manager access required")
    
    # Get or create commission config
    config = CommissionConfig.ensure_config(biz)
    
    if request.method == "POST":
        # Update commission settings
        try:
            commissions_enabled = request.POST.get('commissions_enabled') == 'on'
            commission_mode = request.POST.get('commission_mode', 'PERCENT')
            
            # Validate mode
            if commission_mode not in ['PERCENT', 'FIXED']:
                commission_mode = 'PERCENT'
            
            # Get values
            base_commission_pct = Decimal(request.POST.get('base_commission_pct', '12.00'))
            fixed_commission_amount = Decimal(request.POST.get('fixed_commission_amount', '2000.00'))
            
            # Validate ranges
            if base_commission_pct < 0 or base_commission_pct > 100:
                messages.error(request, "Commission percentage must be between 0 and 100.")
                return redirect(request.path)
            
            if fixed_commission_amount < 0:
                messages.error(request, "Fixed commission amount must be non-negative.")
                return redirect(request.path)
            
            # Update config
            config.commissions_enabled = commissions_enabled
            config.commission_mode = commission_mode
            config.base_commission_pct = base_commission_pct
            config.fixed_commission_amount = fixed_commission_amount
            config.save()
            
            messages.success(request, "Commission settings updated successfully.")
            return redirect(reverse("tenants:manager_review_agents"))
            
        except ValueError as e:
            messages.error(request, f"Invalid number format: {e}")
        except Exception as e:
            messages.error(request, f"Failed to update settings: {e}")
    
    # Render settings form
    ctx = {
        "tenant": biz,
        "config": config,
    }
    
    return _render_agents_template(request, ctx)


@never_cache
@login_required
@require_http_methods(["POST"])
@transaction.atomic
def suspend_agent(request: HttpRequest, membership_id: int) -> HttpResponse:
    """
    Suspend an agent (set their membership and user to inactive).
    Manager can only suspend agents in their own business.
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.error(request, "Please select a business first.")
        return redirect("tenants:manager_review_agents")
    
    try:
        membership = Membership.objects.get(pk=membership_id, business=biz, role="AGENT")
        user = membership.user
        
        # Set membership inactive
        membership.status = "SUSPENDED"
        membership.save(update_fields=["status"])
        
        # Also set user inactive so they can't log in
        if user and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        
        messages.success(request, f"Agent {user.get_full_name() or user.username} has been suspended.")
    except Membership.DoesNotExist:
        messages.error(request, "Agent not found or not in your business.")
    except Exception as e:
        messages.error(request, f"Error suspending agent: {e}")
    
    return redirect("tenants:manager_review_agents")


@never_cache
@login_required
@require_http_methods(["POST"])
@transaction.atomic
def restore_agent(request: HttpRequest, membership_id: int) -> HttpResponse:
    """
    Restore a suspended agent (set their membership and user back to active).
    Manager can only restore agents in their own business.
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.error(request, "Please select a business first.")
        return redirect("tenants:manager_review_agents")
    
    try:
        membership = Membership.objects.get(pk=membership_id, business=biz, role="AGENT")
        user = membership.user
        
        # Set membership active
        membership.status = "ACTIVE"
        membership.save(update_fields=["status"])
        
        # Also set user active so they can log in
        if user and not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        
        messages.success(request, f"Agent {user.get_full_name() or user.username} has been restored.")
    except Membership.DoesNotExist:
        messages.error(request, "Agent not found or not in your business.")
    except Exception as e:
        messages.error(request, f"Error restoring agent: {e}")
    
    return redirect("tenants:manager_review_agents")


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit_agent_location(request: HttpRequest, membership_id: int) -> HttpResponse:
    """
    Edit an agent's location assignment.
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.error(request, "Please select a business first.")
        return redirect("tenants:manager_review_agents")
    
    try:
        membership = Membership.objects.get(pk=membership_id, business=biz, role="AGENT")
        
        if request.method == "POST":
            location_id = request.POST.get("location_id")
            if location_id:
                try:
                    from inventory.models import Location
                    location = Location.objects.get(pk=int(location_id), business=biz)
                    membership.location = location
                    membership.save(update_fields=["location"])
                    messages.success(request, f"Updated location for {membership.user.get_full_name() or membership.user.username}.")
                except Exception as e:
                    messages.error(request, f"Invalid location: {e}")
            else:
                # Clear location
                membership.location = None
                membership.save(update_fields=["location"])
                messages.success(request, f"Cleared location for {membership.user.get_full_name() or membership.user.username}.")
            
            return redirect("tenants:manager_review_agents")
        
        # GET: show form (or redirect if we want inline editing)
        return redirect("tenants:manager_review_agents")
        
    except Membership.DoesNotExist:
        messages.error(request, "Agent not found.")
        return redirect("tenants:manager_review_agents")


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
    loc_id = (request.POST.get("location_id") or "").strip()
    try:
        ttl_val = int(ttl_days) if ttl_days else 7
    except Exception:
        ttl_val = 7
    try:
        location_id = int(loc_id) if loc_id else None
    except Exception:
        location_id = None

    try:
        inv, temp_password = _safe_service_create_invite(
            business=biz,
            requested_by=getattr(request, "user", None),
            invited_name=invited_name,
            email=email,
            phone=phone,
            ttl_days=ttl_val,
            message=message_text,
            location_id=location_id,
        )
        latest_link = _invite_accept_absolute_url(request, inv)
        messages.success(request, "Invitation created.")
        url = reverse("tenants:manager_review_agents")
        # Pass both link and password via URL params (one-time display)
        if latest_link:
            url = f"{url}?latest_link={quote(latest_link)}"
        if temp_password:
            url = f"{url}&temp_password={quote(temp_password)}"
        return redirect(url)
    except Exception as e:
        messages.error(request, f"Could not create invite: {e}")
        return redirect("tenants:manager_review_agents")


@never_cache
@login_required
@require_http_methods(["GET"])
def manager_agents_earnings(request: HttpRequest) -> HttpResponse:
    """
    Manager Agent Earnings view: show agent performance rankings.
    
    Filters:
    - ?range=today
    - ?range=7d (last 7 days)
    - ?range=month (this month, default)
    - ?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    biz = _active_business_from_request(request) or _force_pick_any_membership(request)
    if not biz:
        messages.warning(request, "Please choose a business first.")
        return redirect_manager_safe_choose(request)
    
    # Parse date range from query params
    from datetime import datetime, date
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    range_param = request.GET.get('range', 'month').lower()
    
    if range_param == 'today':
        start_date = today_start
        end_date = now
        range_label = 'Today'
    elif range_param == '7d':
        start_date = today_start - timedelta(days=7)
        end_date = now
        range_label = 'Last 7 Days'
    elif range_param == 'custom':
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        try:
            start_d = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
            start_date = timezone.make_aware(datetime.combine(start_d, datetime.min.time()))
            end_date = timezone.make_aware(datetime.combine(end_d, datetime.max.time()))
            range_label = f"{start_d.strftime('%b %d')} – {end_d.strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            # Fallback to this month
            month_start = today_start.replace(day=1)
            start_date = month_start
            end_date = now
            range_label = 'This Month'
    else:
        # Default: this month
        month_start = today_start.replace(day=1)
        start_date = month_start
        end_date = now
        range_label = 'This Month'
    
    # Get agent earnings data
    try:
        from inventory.services.agent_earnings import get_agent_earnings
        
        location = getattr(request, 'active_location', None) or getattr(request, 'location', None)
        
        earnings_data = get_agent_earnings(
            business=biz,
            start_date=start_date.date() if hasattr(start_date, 'date') else start_date,
            end_date=end_date.date() if hasattr(end_date, 'date') else end_date,
            location=location,
        )
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to fetch agent earnings: %s", e)
        earnings_data = []
        messages.error(request, f"Error loading earnings data: {e}")
    
    # Calculate totals
    from decimal import Decimal
    total_revenue = sum((row.total_revenue for row in earnings_data), Decimal('0.00'))
    total_commission = sum((row.total_commission for row in earnings_data), Decimal('0.00'))
    total_units = sum((row.units_sold for row in earnings_data), 0)
    
    ctx = {
        "tenant": biz,
        "business": biz,
        "earnings_data": earnings_data,
        "range_key": range_param,
        "range_label": range_label,
        "start_date": start_date.date() if hasattr(start_date, 'date') else start_date,
        "end_date": end_date.date() if hasattr(end_date, 'date') else end_date,
        "total_revenue": total_revenue,
        "total_commission": total_commission,
        "total_units": total_units,
        "agent_count": len(earnings_data),
    }
    
    # Render template
    from django.template.loader import select_template
    from django.http import HttpResponse
    
    tpl = select_template([
        "tenants/manager_agents_earnings.html",
        "tenants/manager/agents_earnings.html",
    ])
    return HttpResponse(tpl.render(ctx, request))