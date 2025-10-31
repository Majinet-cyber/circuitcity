# tenants/scope.py
from __future__ import annotations

from typing import Optional, Tuple, Iterable

from django.conf import settings
from django.utils.functional import cached_property

from .models import Business, Membership, get_current_business_id


# --------------------------------------------------------------------------------------
# Lightweight accessors (import-on-demand to avoid circulars)
# --------------------------------------------------------------------------------------
def _LocationModel():
    try:
        from inventory.models import Location  # local import avoids circular deps
        return Location
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Active business / membership helpers
# --------------------------------------------------------------------------------------
def get_active_business_id_from_request(request) -> Optional[int]:
    """
    Read the active business id in the same priority used by middleware:
      1) request.active_business_id (if middleware set it)
      2) session['active_business_id']
      3) threadlocal (tenants.models.get_current_business_id)
    """
    # 1) set by ActiveBusinessMiddleware
    bid = getattr(request, "active_business_id", None)
    if bid:
        return int(bid)

    # 2) session (if middleware hasn’t run yet)
    try:
        bid = request.session.get("active_business_id")
        if bid:
            return int(bid)
    except Exception:
        pass

    # 3) threadlocal (set by middleware or using_business context)
    bid = get_current_business_id()
    return int(bid) if bid else None


def get_active_business(request) -> Optional[Business]:
    bid = get_active_business_id_from_request(request)
    if not bid:
        return None
    try:
        return Business.objects.get(pk=bid)
    except Business.DoesNotExist:
        return None


def get_membership(user, business: Business | int) -> Optional[Membership]:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    biz_id = business.id if isinstance(business, Business) else business
    if not biz_id:
        return None
    try:
        return (
            Membership.objects
            .select_related("business", "location", "user")
            .get(user_id=user.id, business_id=biz_id, status="ACTIVE")
        )
    except Membership.DoesNotExist:
        return None


def is_manager(user, business: Business | int) -> bool:
    m = get_membership(user, business)
    return bool(m and (m.role or "").upper() == "MANAGER")


def is_agent(user, business: Business | int) -> bool:
    m = get_membership(user, business)
    return bool(m and (m.role or "").upper() == "AGENT")


# --------------------------------------------------------------------------------------
# Location resolution (ONE source of truth)
# --------------------------------------------------------------------------------------
def _parse_location_id_from_request(request) -> Optional[int]:
    """
    Accepts ?location=<pk> or ?location_id=<pk> on the URL, or session key.
    Returns an int or None. Never raises.
    """
    val = None
    try:
        val = request.GET.get("location") or request.GET.get("location_id")
    except Exception:
        val = None
    if not val:
        try:
            val = request.session.get("active_location_id")
        except Exception:
            val = None
    try:
        return int(val) if val not in (None, "", "0") else None
    except Exception:
        return None


def _coerce_location_for_business(location_id: Optional[int], business_id: Optional[int]) -> Optional[int]:
    """
    Make sure the provided location actually belongs to the active business.
    If not, return None.
    """
    if not location_id or not business_id:
        return None
    Location = _LocationModel()
    if not Location:
        return None
    try:
        ok = Location.objects.filter(pk=location_id, business_id=business_id).exists()
        return location_id if ok else None
    except Exception:
        return None


def _default_location_for_business(business: Optional[Business]) -> Optional[int]:
    Location = _LocationModel()
    if not business or not Location:
        return None

    # Prefer explicit default if your model supports it
    if hasattr(Location, "is_default"):
        loc = Location.objects.filter(business=business, is_default=True).first()
        if loc:
            return loc.id

    # Fallback to first by name/id
    loc = Location.objects.filter(business=business).order_by("name", "id").first()
    return loc.id if loc else None


def resolve_location_for_user(request) -> Optional[int]:
    """
    Determine the effective location **id** for this request:
      • Managers: explicit ?location / session override; else business default.
      • Agents: always their Membership.location (no override).
    Returns an integer pk or None.
    """
    business = get_active_business(request)
    if not business:
        return None

    user = getattr(request, "user", None)
    m = get_membership(user, business) if user and user.is_authenticated else None

    # Agent: hard lock to membership.location
    if m and (m.role or "").upper() == "AGENT":
        return getattr(m, "location_id", None)

    # Manager: allow override via query/session, but keep within business
    loc_id = _parse_location_id_from_request(request)
    loc_id = _coerce_location_for_business(loc_id, business.id)
    if loc_id:
        return loc_id

    # Fallback (manager or no membership): default/first
    return _default_location_for_business(business)


def set_scope_in_session(request, *, business_id: Optional[int] = None, location_id: Optional[int] = None) -> None:
    """
    Persist chosen scope to session so the UI remembers selections between pages.
    Safe even if sessions are disabled (no-op).
    """
    try:
        if business_id is not None:
            request.session["active_business_id"] = int(business_id)
        if location_id is not None:
            request.session["active_location_id"] = int(location_id)
    except Exception:
        # Sessionless scenarios (API tokens, CLI) — ignore
        pass


def get_active_scope(request) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (business_id, location_id) after applying all the rules above.
    """
    biz = get_active_business(request)
    bid = biz.id if biz else None
    lid = resolve_location_for_user(request) if bid else None
    return bid, lid


# --------------------------------------------------------------------------------------
# QuerySet scopers (works for InventoryItem; no-ops for other models)
# --------------------------------------------------------------------------------------
def scope_queryset_to_location(qs, location_id: Optional[int]):
    """
    Apply a location filter if the model has a 'current_location' or 'location' FK.
    If not, return the queryset unchanged.
    """
    if not location_id:
        return qs
    model = getattr(qs, "model", None)
    if not model:
        return qs

    fields = {f.name for f in getattr(model, "_meta", [] )} if hasattr(model, "_meta") else set()
    try:
        if "current_location" in fields:
            return qs.filter(current_location_id=location_id)
        if "location" in fields:
            return qs.filter(location_id=location_id)
    except Exception:
        # If the ORM complains (e.g., aliasing), leave unfiltered rather than break.
        return qs
    return qs


def scope_inventory_qs_for_request(qs, request):
    """
    InventoryItem list scoper:
      • Always tenant-scoped by your TenantManager already.
      • If AGENT → force their membership.location
      • If MANAGER → accept optional ?location filter; otherwise no location filter (manager sees all)
    """
    business = get_active_business(request)
    if not business:
        return qs.none()

    user = getattr(request, "user", None)
    m = get_membership(user, business) if user and user.is_authenticated else None

    if m and (m.role or "").upper() == "AGENT" and getattr(m, "location_id", None):
        return qs.filter(current_location_id=m.location_id)

    # Manager: optional filter if the page passed one
    loc_id = _parse_location_id_from_request(request)
    loc_id = _coerce_location_for_business(loc_id, business.id)
    if loc_id:
        return qs.filter(current_location_id=loc_id)

    return qs


# --------------------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------------------
def location_choices_for_user(user, business: Business | int) -> Iterable[Tuple[int, str]]:
    """
    Build a list of (id, label) choices for a picker:
      • Manager → all locations in business
      • Agent   → only their membership location
    """
    biz_id = business.id if isinstance(business, Business) else business
    if not biz_id:
        return []

    Location = _LocationModel()
    if not Location:
        return []

    if is_manager(user, biz_id):
        rows = Location.objects.filter(business_id=biz_id).order_by("name", "id")
        return [(r.id, r.name) for r in rows]

    m = get_membership(user, biz_id)
    if m and m.location_id:
        try:
            loc = Location.objects.get(pk=m.location_id)
            return [(loc.id, loc.name)]
        except Location.DoesNotExist:
            return []

    return []


def serialize_scope_for_ui(request) -> dict:
    """
    Small JSON blob for templates/JS to understand the current scope.
    """
    biz = get_active_business(request)
    bid, lid = get_active_scope(request)
    role = None
    if getattr(request, "user", None) and request.user.is_authenticated and biz:
        mem = get_membership(request.user, biz)
        role = (mem.role if mem else None) or None

    return {
        "business_id": bid,
        "business_name": getattr(biz, "name", None),
        "location_id": lid,
        "role": role,  # 'MANAGER' | 'AGENT' | None
    }
