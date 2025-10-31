# circuitcity/tenants/views.py
from __future__ import annotations

from typing import Optional, List, Set
from urllib.parse import quote_plus
from datetime import timedelta  # <-- FIX: use datetime.timedelta (not timezone.timedelta)

from django.contrib import messages
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from .forms import CreateBusinessForm, JoinAsAgentForm, InviteAgentForm
from .models import Business, Membership, AgentInvite
from .utils import (
    require_business,
    require_role,
    set_active_business,
    get_active_business,
    # NEW helpers (added, non-breaking)
    resolve_default_business_for_user,
    user_highest_role,
    user_has_membership,
)

import logging
log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------

TOKEN_FIELDS = ("token", "code", "uid", "uuid", "slug", "key")


def _home_redirect(request: HttpRequest) -> HttpResponse:
    """Redirect to your main *tenant* dashboard if defined; otherwise to root."""
    try:
        return redirect("dashboard:home")
    except NoReverseMatch:
        return redirect("/")


def _superuser_landing(request: HttpRequest) -> HttpResponse:
    """Where superusers should land by default (HQ dashboard or home)."""
    try:
        return redirect("hq:dashboard")
    except NoReverseMatch:
        return _home_redirect(request)


def _redirect_next_or_home(
    request: HttpRequest, fallback: str = "tenants:choose_business"
) -> HttpResponse:
    """
    Respect ?next= when present. Otherwise:
      - superusers → HQ dashboard
      - everyone else → fallback (usually the chooser)
    """
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt:
        return redirect(nxt)

    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.is_superuser:
        return _superuser_landing(request)

    try:
        return redirect(fallback)
    except Exception:
        return _home_redirect(request)


def _ensure_seed_on_switch(biz: Business) -> None:
    """Seed defaults (store/warehouse) when switching into a brand-new tenant."""
    try:
        biz.seed_defaults()
    except Exception:
        pass  # never block a switch


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _model_field_names(model) -> Set[str]:
    """Return concrete field names for a model (safe for kwargs filtering)."""
    names: Set[str] = set()
    for f in model._meta.get_fields():
        if hasattr(f, "attname"):
            names.add(f.name)
    return names


def _get_invite_display_name(invite: AgentInvite) -> str:
    """Find a name-ish field no matter the model (invited_name/full_name/name)."""
    for key in ("invited_name", "full_name", "name"):
        try:
            val = getattr(invite, key, "") or ""
            if val.strip():
                return val.strip()
        except Exception:
            pass
    return ""


def _invite_token_value(invite: AgentInvite) -> str:
    """Return the token value from whichever common field your model uses."""
    for f in TOKEN_FIELDS:
        try:
            v = getattr(invite, f, None)
            if v:
                return str(v)
        except Exception:
            pass
    return ""


def _get_invite_by_token(token: str) -> Optional[AgentInvite]:
    """Fetch an invite by checking multiple likely token fields."""
    fields = _model_field_names(AgentInvite)
    for f in TOKEN_FIELDS:
        if f in fields:
            try:
                obj = AgentInvite.objects.filter(**{f: token}).first()
                if obj:
                    return obj
            except Exception:
                continue
    return None


def _share_text(invite: AgentInvite) -> str:
    """Message text: Hi (name), please click this link to join (shop)."""
    name = _get_invite_display_name(invite) or "there"
    shop = invite.business.name
    url = getattr(invite, "accept_url", "")
    return f"Hi {name}, please click this link to join {shop}: {url}"


def _mailto_link(invite: AgentInvite) -> str:
    subject = f"Join {invite.business.name}"
    body = _share_text(invite)
    return (
        f"mailto:{getattr(invite,'email','') or ''}?subject={quote_plus(subject)}&body={quote_plus(body)}"
        if getattr(invite, "email", "")
        else f"mailto:?subject={quote_plus(subject)}&body={quote_plus(body)}"
    )


def _whatsapp_link(invite: AgentInvite) -> str:
    """WhatsApp universal share link."""
    return f"https://wa.me/?text={quote_plus(_share_text(invite))}"


# -------------------------------------------------------------------
# Activation / selection flow
# -------------------------------------------------------------------

@login_required
def activate_mine(request: HttpRequest) -> HttpResponse:
    """
    Auto-activate a sensible business for the current user.

    HARDENING:
    - Prefer OWNER/MANAGER/ADMIN memberships (ACTIVE if available).
    - If none active, still *avoid* sending managers/owners to Join-as-agent.
    - If the user previously created a PENDING business, never suggest joining.
    """
    # If we already have an active business, honor ?next= or chooser
    if get_active_business(request):
        return _redirect_next_or_home(request, fallback="tenants:choose_business")

    if request.user.is_superuser:
        return _superuser_landing(request)

    user = request.user

    # Preferred default (owners/managers first; ACTIVE preferred)
    preferred = resolve_default_business_for_user(user)
    if preferred:
        # Ensure only businesses the user actually belongs to can be set
        if user_has_membership(user, preferred.id):
            _ensure_seed_on_switch(preferred)
            set_active_business(request, preferred)
            messages.success(request, f"Switched to {preferred.name}.")
            return _redirect_next_or_home(request, fallback="tenants:choose_business")

    # Legacy logic: enumerate ACTIVE memberships (business ACTIVE too)
    active_memberships = list(
        Membership.objects.filter(user=user, status="ACTIVE")
        .select_related("business")
        .order_by("-created_at")
    )
    active_memberships = [
        m for m in active_memberships
        if getattr(m.business, "status", "ACTIVE") == "ACTIVE"
    ]

    if len(active_memberships) == 1:
        b = active_memberships[0].business
        _ensure_seed_on_switch(b)
        set_active_business(request, b)
        messages.success(request, f"Switched to {b.name}.")
        return _redirect_next_or_home(request, fallback="tenants:choose_business")

    if len(active_memberships) > 1:
        return redirect("tenants:choose_business")

    # If the user created a pending business, do not suggest joining
    pending_i_created = Business.objects.filter(
        created_by=user, status="PENDING"
    ).order_by("-created_at").first()
    if pending_i_created:
        messages.info(
            request,
            "Your business is pending approval. You can still browse or request to join another.",
        )
        return redirect("tenants:choose_business")

    # If the user is a MANAGER/OWNER anywhere (even non-active), never show agent join
    role = (user_highest_role(user) or "").upper()
    if role in {"OWNER", "MANAGER", "ADMIN"}:
        messages.info(request, "Select or set up your business to continue.")
        return redirect("tenants:choose_business")

    # True blank-slate agent
    messages.info(request, "Join an existing business to get started.")
    return redirect("tenants:join_as_agent")


@login_required
def clear_active(request: HttpRequest) -> HttpResponse:
    set_active_business(request, None)
    messages.info(request, "Cleared active business.")
    return _redirect_next_or_home(request, fallback="tenants:choose_business")


@login_required
def set_active(request: HttpRequest, biz_id) -> HttpResponse:
    """Switch active business for this session (membership required unless superuser)."""
    b = get_object_or_404(Business, pk=biz_id, status="ACTIVE")

    user = request.user
    if not user.is_superuser:
        has_access = Membership.objects.filter(
            business=b, user=user, status="ACTIVE"
        ).exists()
        if not has_access:
            messages.error(request, "You do not have access to that business.")
            return redirect("tenants:choose_business")

    _ensure_seed_on_switch(b)
    set_active_business(request, b)
    messages.success(request, f"Switched to {b.name}.")
    return _home_redirect(request)


@login_required
def choose_business(request: HttpRequest) -> HttpResponse:
    """Chooser page for users with multiple businesses."""
    user = request.user

    memberships_qs = (
        Membership.objects.filter(user=user, status="ACTIVE")
        .select_related("business")
        .order_by("-created_at")
    )

    all_active_businesses = None
    if user.is_superuser:
        all_active_businesses = Business.objects.filter(status="ACTIVE").order_by("name")

    if request.method == "POST":
        bid = request.POST.get("business_id")
        if not bid:
            messages.error(request, "No business selected.")
            return redirect("tenants:choose_business")

        b = get_object_or_404(Business, pk=bid, status="ACTIVE")

        if not user.is_superuser:
            ok = Membership.objects.filter(
                business=b, user=user, status="ACTIVE"
            ).exists()
            if not ok:
                messages.error(request, "You cannot switch to that business.")
                return redirect("tenants:choose_business")

        _ensure_seed_on_switch(b)
        set_active_business(request, b)
        messages.success(request, f"Switched to {b.name}.")
        return _home_redirect(request)

    return render(
        request,
        "tenants/choose_business.html",
        {
            "memberships": memberships_qs,
            "all_active_businesses": all_active_businesses,
        },
    )


# -------------------------------------------------------------------
# Onboarding
# -------------------------------------------------------------------

@login_required
def create_business_as_manager(request: HttpRequest) -> HttpResponse:
    """
    Manager proposes a new Business (PENDING).
    HARDENING:
    - After creation, set active_business to the new business (even if PENDING)
      so managers will never be offered the agent-join path.
    """
    if request.method == "POST":
        form = CreateBusinessForm(request.POST)
        if form.is_valid():
            b: Business = form.save(commit=False)
            b.slug = form.cleaned_data["slug"]
            b.created_by = request.user
            b.status = "PENDING"
            b.save()

            Membership.objects.create(
                user=request.user,
                business=b,
                role="MANAGER",
                status="PENDING",
            )

            # NEW: set active business immediately (privacy-safe; it’s the creator’s)
            set_active_business(request, b)

            messages.success(
                request,
                "Business submitted. A developer will approve it shortly."
            )
            return redirect("tenants:choose_business")
    else:
        form = CreateBusinessForm()

    return render(request, "tenants/create_business.html", {"form": form})


@login_required
def join_as_agent(request: HttpRequest) -> HttpResponse:
    """
    Agent requests to join an ACTIVE business by name.

    HARDENING:
    - If user is OWNER/MANAGER/ADMIN anywhere, block this view (never allow demotion path).
    - If user already has an active business, send them home.
    """
    if request.user.is_superuser:
        return _superuser_landing(request)

    # Never show agent-join to managers/owners/admins
    role = (user_highest_role(request.user) or "").upper()
    if role in {"OWNER", "MANAGER", "ADMIN"}:
        # You can change to redirect("/") if you prefer; 403 is explicit
        return HttpResponseForbidden("Managers and owners cannot join as agents.")

    if get_active_business(request):
        return _home_redirect(request)

    if request.method == "POST":
        form = JoinAsAgentForm(request.POST)
        if form.is_valid():
            b: Business = form.cleaned_data["business"]

            if b.status != "ACTIVE":
                messages.error(request, "You can only join a business that is ACTIVE.")
                return redirect("tenants:join_as_agent")

            mem, created = Membership.objects.get_or_create(
                user=request.user,
                business=b,
                defaults={"role": "AGENT", "status": "PENDING"},
            )

            if not created:
                if mem.status == "ACTIVE":
                    _ensure_seed_on_switch(b)
                    set_active_business(request, b)
                    messages.info(request, f"Already active in {b.name}. Switched.")
                    return _home_redirect(request)
                elif mem.status == "REJECTED":
                    mem.status = "PENDING"
                    mem.role = "AGENT"
                    mem.save(update_fields=["status", "role"])

            messages.success(request, f"Join request sent to {b.name}'s managers.")
            return redirect("tenants:choose_business")
    else:
        form = JoinAsAgentForm()

    return render(request, "tenants/join_as_agent.html", {"form": form})


# -------------------------------------------------------------------
# Staff approval / manager tools
# -------------------------------------------------------------------

@user_passes_test(lambda u: u.is_staff)
def staff_approve_business(request: HttpRequest, pk: int) -> HttpResponse:
    """Staff-only approve/reject a newly created business."""
    b = get_object_or_404(Business, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            b.status = "ACTIVE"
            b.save(update_fields=["status"])
            Membership.objects.filter(
                business=b, role="MANAGER", user=b.created_by
            ).update(status="ACTIVE")

            _ensure_seed_on_switch(b)
            messages.success(request, f"Approved business {b.name}.")
        elif action == "reject":
            b.status = "SUSPENDED"
            b.save(update_fields=["status"])
            Membership.objects.filter(business=b).update(status="REJECTED")
            messages.info(request, f"Rejected business {b.name}.")
        else:
            messages.error(request, "Unknown action.")
        return redirect(request.path)

    pending_members = Membership.objects.filter(business=b).select_related("user")
    return render(
        request,
        "tenants/staff_approve_business.html",
        {"business": b, "members": pending_members},
    )


@login_required
@require_business
@require_role(["Manager", "Admin"])  # group-based manager/admin access
def manager_review_agents(request: HttpRequest) -> HttpResponse:
    """
    Manager screen to:
      - Approve/reject join requests
      - Create an invite
      - Share invite via WhatsApp / Email with prefilled message
    """
    b: Business = request.business

    if request.method == "POST":
        mem_id = request.POST.get("membership_id")
        action = request.POST.get("action")
        mem = get_object_or_404(Membership, pk=mem_id, business=b)

        if action == "approve":
            mem.status = "ACTIVE"
            mem.save(update_fields=["status"])
            messages.success(request, f"Approved {mem.user} as agent.")
        elif action == "reject":
            mem.status = "REJECTED"
            mem.save(update_fields=["status"])
            messages.info(request, f"Rejected {mem.user}.")
        else:
            messages.error(request, "Unknown action.")
        return redirect("tenants:manager_review_agents")

    pending = list(
        Membership.objects.filter(business=b, role="AGENT", status="PENDING")
        .select_related("user")
        .order_by("-created_at")
    )

    # Exclude anyone who is also a MANAGER in this business from Active agents
    manager_user_ids = Membership.objects.filter(
        business=b, role="MANAGER", status="ACTIVE"
    ).values_list("user_id", flat=True)

    active = list(
        Membership.objects.filter(business=b, role="AGENT", status="ACTIVE")
        .exclude(user_id__in=manager_user_ids)
        .select_related("user")
        .order_by("-created_at")
    )

    # Existing invites (mark expired for UI niceness)
    invites: List[AgentInvite] = []
    for inv in AgentInvite.objects.filter(business=b).order_by("-created_at"):
        if hasattr(inv, "mark_expired_if_needed"):
            try:
                inv.mark_expired_if_needed()
            except Exception:
                pass

        # Build accept URL using the actual token-like field on the model
        tok = _invite_token_value(inv)
        try:
            # IMPORTANT: reverse the **URL name** defined in urls.py
            accept_path = reverse("tenants:invite_accept", args=[tok])
            inv.accept_url = request.build_absolute_uri(accept_path)  # type: ignore[attr-defined]
        except Exception:
            inv.accept_url = ""  # type: ignore[attr-defined]

        # Share links for buttons
        inv.mailto = _mailto_link(inv)     # type: ignore[attr-defined]
        inv.whatsapp = _whatsapp_link(inv) # type: ignore[attr-defined]

        invites.append(inv)

    return render(
        request,
        "tenants/manager_review_agents.html",
        {"pending": pending, "active": active, "invites": invites},
    )


def _csrf_input(request: HttpRequest) -> str:
    """Inline CSRF token field for our minimal HTML forms."""
    try:
        from django.middleware.csrf import get_token
        token = get_token(request)
        return f'<input type="hidden" name="csrfmiddlewaretoken" value="{escape(token)}" />'
    except Exception:
        return ""


# -------------------------------------------------------------------
# NEW: Locations (safe, template-free placeholder)
# -------------------------------------------------------------------

@login_required
@require_business
@require_role(["Manager", "Admin"])
def manager_locations(request: HttpRequest) -> HttpResponse:
    """
    Locations manager (uses base.html so the main sidebar appears).
    - Create/Update
    - Delete (or archive if FK blocks)
    - 'Grab GPS' button fills lat/lng and tries to fill city (handled in template JS)
    """
    b: Business = request.business

    # Prefer inventory.Location; fall back to inventory.Store
    Model = None  # type: ignore
    try:
        from inventory.models import Location as _Model  # type: ignore
        Model = _Model
    except Exception:
        try:
            from inventory.models import Store as _Model  # type: ignore
            Model = _Model
        except Exception:
            Model = None
    if Model is None:
        return HttpResponse("Define inventory.Location or inventory.Store.", status=501)

    msg = ""
    # ---------- Create / Update / Delete ----------
    if request.method == "POST":
        try:
            action = (request.POST.get("action") or "upsert").lower()
            loc_id = request.POST.get("loc_id") or ""

            if action == "delete":
                if not loc_id:
                    raise ValueError("Missing location id.")
                loc = Model.objects.get(pk=loc_id)
                if hasattr(loc, "business_id") and getattr(loc, "business_id", None) != b.id:
                    return HttpResponse("Forbidden", status=403)
                try:
                    loc.delete()
                    msg = "Deleted."
                except Exception:
                    # FK blocked – archive/disable instead
                    if hasattr(loc, "is_active"):
                        setattr(loc, "is_active", False)
                        loc.save(update_fields=["is_active"])
                        msg = "Location is in use; archived instead."
                    else:
                        msg = "Could not delete (in use)."
            else:
                # upsert
                name = (request.POST.get("name") or "").strip()
                if not name:
                    raise ValueError("Name is required.")
                city = (request.POST.get("city") or "").strip()
                lat  = (request.POST.get("latitude") or "").replace(",", "").strip() or None
                lng  = (request.POST.get("longitude") or "").replace(",", "").strip() or None
                radius = request.POST.get("radius") or request.POST.get("geofence_radius_m") or "150"
                is_default = request.POST.get("is_default") == "on"

                try:
                    radius = int(float(radius))
                except Exception:
                    radius = 150

                if loc_id:
                    loc = Model.objects.get(pk=loc_id)
                    if hasattr(loc, "business_id") and getattr(loc, "business_id", None) != b.id:
                        return HttpResponse("Forbidden", status=403)
                else:
                    kwargs = {}
                    if hasattr(Model, "business_id"):
                        kwargs["business"] = b
                    loc = Model(**kwargs)

                # Assign if field exists on model
                if hasattr(loc, "name"): loc.name = name
                if hasattr(loc, "city"): loc.city = city
                if hasattr(loc, "latitude"): loc.latitude = lat
                if hasattr(loc, "longitude"): loc.longitude = lng
                if hasattr(loc, "geofence_radius_m"): loc.geofence_radius_m = radius
                if hasattr(loc, "is_active") and getattr(loc, "is_active", None) is None:
                    loc.is_active = True

                loc.save()

                if hasattr(loc, "is_default"):
                    if is_default:
                        loc.is_default = True
                        loc.save(update_fields=["is_default"])
                        if hasattr(Model, "business_id"):
                            Model.objects.filter(business=b, is_default=True)\
                                .exclude(pk=loc.pk).update(is_default=False)
                    else:
                        if getattr(loc, "is_default", False):
                            loc.is_default = False
                            loc.save(update_fields=["is_default"])

                msg = "Saved."
        except Exception as e:
            msg = f"Error: {e!s}"

    # ---------- List ----------
    qs = Model.objects.all()
    if hasattr(Model, "business_id"):
        qs = qs.filter(business=b)
    locations = list(qs.order_by("name" if hasattr(Model, "name") else "id"))

    def _type_for(loc) -> str:
        for f in ("kind", "type", "city"):
            v = getattr(loc, f, None)
            if isinstance(v, str) and v.strip():
                return v
        return "STORE"

    def _active_for(loc) -> bool:
        if hasattr(loc, "is_active"):
            return bool(getattr(loc, "is_active"))
        if hasattr(loc, "is_default"):
            return bool(getattr(loc, "is_default"))
        return True

    rows = [
        {
            "id": getattr(loc, "id", ""),
            "name": getattr(loc, "name", str(loc)),
            "city": getattr(loc, "city", ""),
            "type": _type_for(loc),
            "active": "Yes" if _active_for(loc) else "No",
            "lat": (getattr(loc, "latitude", "") or ""),
            "lng": (getattr(loc, "longitude", "") or ""),
            "radius": (getattr(loc, "geofence_radius_m", "") or "150"),
            "is_default": "1" if getattr(loc, "is_default", False) else "0",
        }
        for loc in locations
    ]

    ctx = {
        "biz": b,
        "rows": rows,
        "flash": msg,
    }
    return render(request, "tenants/manager_locations.html", ctx)

# -------------------------------------------------------------------
# Agent Invite flows
# -------------------------------------------------------------------

def _pick_name_field_for_invite(kwargs: dict, model_fields: Set[str]) -> None:
    """
    Normalize a name value from incoming form data to whatever the model supports.
    Accept 'invited_name'/'full_name'/'name' in POST and map to the first field that exists.
    """
    raw = (kwargs.pop("invited_name", "") or kwargs.get("full_name") or kwargs.get("name") or "").strip()
    kwargs.pop("full_name", None)
    kwargs.pop("name", None)
    if not raw:
        return
    for field in ("invited_name", "full_name", "name"):
        if field in model_fields:
            kwargs[field] = raw
            return
    # else: silently drop


@login_required
@require_business
@require_role(["Manager", "Admin"])
@require_http_methods(["POST"])
@transaction.atomic
def create_agent_invite(request: HttpRequest) -> HttpResponse:
    """
    Managers create an invitation link for the active business.
    IMPORTANT: we let the model generate a short uuid token (<=40 chars)
               to avoid DB truncation.
    """
    b: Business = request.business
    form = InviteAgentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please fix the invite form.")
        return redirect("tenants:manager_review_agents")

    data = form.cleaned_data

    # Expiry: 4 hours from now if the field exists  (FIXED: datetime.timedelta)
    expires_at = timezone.now() + timedelta(hours=4)

    # Build kwargs WITHOUT 'token' so the model can generate it in save()
    invite_kwargs = dict(
        business=b,
        invited_name=(data.get("invited_name") or "").strip(),  # may be remapped below
        email=(data.get("email") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        created_by=request.user,
        # Pick a broad default that's likely visible in your UI tabs:
        status="UNATTENDED",  # fallback; if your UI expects "SENT", change to "SENT"
    )
    if "message" in form.fields:
        invite_kwargs["message"] = (data.get("message") or "").strip()
    if hasattr(AgentInvite, "expires_at"):
        invite_kwargs["expires_at"] = expires_at  # type: ignore[assignment]

    valid_fields = _model_field_names(AgentInvite)
    _pick_name_field_for_invite(invite_kwargs, valid_fields)
    safe_kwargs = {k: v for k, v in invite_kwargs.items() if k in valid_fields}

    inv = AgentInvite.objects.create(**safe_kwargs)

    # Log for certainty
    log.warning(
        "INVITE CREATED id=%s email=%s business=%s status=%s",
        getattr(inv, "id", None),
        getattr(inv, "email", None),
        getattr(inv, "business_id", None),
        getattr(inv, "status", None),
    )

    messages.success(request, "Invitation created.")
    return redirect("tenants:manager_review_agents")


@login_required
@require_business
@require_role(["Manager", "Admin"])
def revoke_agent_invite(request: HttpRequest, pk: int) -> HttpResponse:
    """Managers can revoke an invite that hasn't been used yet."""
    b: Business = request.business
    inv = get_object_or_404(AgentInvite, pk=pk, business=b)
    if getattr(inv, "status", "") in ("SENT", "DRAFT", "UNATTENDED"):
        inv.status = "REVOKED"
        inv.save(update_fields=["status"])
        messages.info(request, "Invite revoked.")
    return redirect("tenants:manager_review_agents")


@transaction.atomic
def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """
    Landing page from the invite link.
    - If not authenticated, show a tiny signup; then continue.
    - Activates membership as AGENT and sets tenant active.
    """
    invite = _get_invite_by_token(token)
    if invite is None:
        return _invite_invalid_page("invalid")

    # Optional: mark expired if model supports it
    if hasattr(invite, "mark_expired_if_needed"):
        try:
            invite.mark_expired_if_needed()  # type: ignore[attr-defined]
        except Exception:
            pass

    if getattr(invite, "status", "") not in ("SENT", "UNATTENDED"):
        return _invite_invalid_page(getattr(invite, "status", "invalid").lower())

    biz = invite.business
    User = get_user_model()

    if not request.user.is_authenticated:
        if request.method == "POST":
            username = (request.POST.get("username") or "").strip()
            p1 = request.POST.get("password1") or ""
            p2 = request.POST.get("password2") or ""
            error = None
            if not username:
                error = "Enter a username."
            elif p1 != p2:
                error = "Passwords do not match."
            elif len(p1) < 6:
                error = "Password must be at least 6 characters."
            elif User.objects.filter(username__iexact=username).exists():
                error = "Username is taken."
            if error:
                invite._request = request  # type: ignore[attr-defined]
                return _invite_signup_page(invite, error=error)
            user = User.objects.create_user(username=username, password=p1, email=getattr(invite, "email", "") or "")
            login(request, user)
        else:
            invite._request = request  # type: ignore[attr-defined]
            return _invite_signup_page(invite)

    # Create or update membership → ACTIVE/AGENT
    mem, _created = Membership.objects.get_or_create(
        business=biz,
        user=request.user,
        defaults={"role": "AGENT", "status": "ACTIVE"},
    )
    updates = {}
    if getattr(mem, "status", None) != "ACTIVE":
        updates["status"] = "ACTIVE"
    if getattr(mem, "role", None) != "AGENT":
        updates["role"] = "AGENT"

    # Try to auto-assign default location if your inventory app supports it
    try:
        try:
            from inventory.utils import ensure_default_location  # type: ignore
            loc = ensure_default_location(biz)  # type: ignore
        except Exception:
            loc = None
            try:
                from inventory.models import Location  # type: ignore
                qs = Location.objects.filter(business=biz)
                loc = qs.filter(is_default=True).first() or qs.first()
                if loc and hasattr(Location, "is_default") and not getattr(loc, "is_default", False):
                    qs.update(is_default=False)
                    loc.is_default = True
                    loc.save(update_fields=["is_default"])
            except Exception:
                loc = None

        if hasattr(mem, "location_id") and not getattr(mem, "location_id", None) and loc:
            updates["location"] = loc
    except Exception:
        pass

    if updates:
        for k, v in updates.items():
            setattr(mem, k, v)
        mem.save(update_fields=list(updates.keys()))

    # Mark invite as joined/accepted
    new_status = "ACCEPTED" if "ACCEPTED" in getattr(AgentInvite, "STATUS_CHOICES", []) else "JOINED"
    try:
        invite.status = new_status  # type: ignore[assignment]
        if hasattr(invite, "joined_user_id"):
            invite.joined_user = request.user  # type: ignore[assignment]
        if hasattr(invite, "joined_at"):
            invite.joined_at = timezone.now()  # type: ignore[assignment]
        invite.save()
    except Exception:
        pass

    set_active_business(request, biz)
    messages.success(request, f"Welcome to {biz.name}! Your agent access is active.")
    try:
        return redirect("dashboard:home")
    except Exception:
        return redirect("/")


# ---------- Inline pages for invite signup / invalid ----------

def _invite_signup_page(invite: AgentInvite, error: Optional[str] = None) -> HttpResponse:
    biz_name = _esc(invite.business.name)
    hi = _esc(_get_invite_display_name(invite) or "there")
    err = f'<div style="color:#b91c1c;margin-bottom:.5rem">{_esc(error)}</div>' if error else ""
    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Join · {biz_name}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; color: #0b1220; }}
      .card {{ border:1px solid #e2e8f0; border-radius: 12px; padding: 16px; max-width: 520px; }}
      label {{ font-weight:700; font-size:12px; color:#334155; display:block; margin-bottom:6px; }}
      input[type=text], input[type=password] {{
        width:100%; border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; font-size:14px;
      }}
      .btn {{ display:inline-block; border:1px solid #e2e8f0; background:#0ea5e9; color:#fff;
             padding:10px 14px; border-radius:10px; text-decoration:none; font-weight:700; font-size:14px; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h2 style="margin:.2rem 0 1rem">Hi {hi}, welcome to {biz_name}</h2>
      <p style="color:#475569;margin:-.5rem 0 1rem">Create your account to continue.</p>
      {err}
      <form method="post" action="">
        {_csrf_input_placeholder()}
        <label>Username</label>
        <input type="text" name="username" placeholder="yourname" required />
        <div style="height:.75rem"></div>
        <label>Password</label>
        <input type="password" name="password1" placeholder="••••••••" required />
        <div style="height:.75rem"></div>
        <label>Confirm Password</label>
        <input type="password" name="password2" placeholder="••••••••" required />
        <div style="height:1rem"></div>
        <button class="btn">Create & Accept</button>
      </form>
    </div>
  </body>
</html>
    """.strip()
    return HttpResponse(html.replace(_csrf_input_placeholder(), _csrf_input(invite._request)))  # type: ignore[attr-defined]


def _invite_invalid_page(reason: str) -> HttpResponse:
    r = _esc(reason or "invalid")
    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Invite invalid</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; color: #0b1220; }}
      .card {{ border:1px solid #fee2e2; border-radius:12px; padding:16px; max-width:520px; background:#fef2f2; color:#991b1b; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h2 style="margin:.2rem 0 1rem">This invite is {r}.</h2>
      <p>Ask the manager to send a new link.</p>
    </div>
  </body>
</html>
    """.strip()
    return HttpResponse(html)


def _csrf_input_placeholder() -> str:
    return "__CSRF__PLACEHOLDER__"
