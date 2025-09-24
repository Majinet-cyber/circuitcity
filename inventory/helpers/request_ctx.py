# inventory/helpers/request_ctx.py
from __future__ import annotations
from typing import Optional, Tuple

def _attach_business_to_request(request, biz):
    try:
        request.business = biz
        request.active_business = biz  # legacy alias
        request.active_business_id = getattr(biz, "id", None)
        request.session["active_business_id"] = request.active_business_id
        # legacy keys some templates expect
        request.session["biz_id"] = request.active_business_id
    except Exception:
        pass

def _attach_location_to_request(request, loc):
    try:
        request.active_location = loc
        request.active_location_id = getattr(loc, "id", None)
        request.session["active_location_id"] = request.active_location_id
    except Exception:
        pass

def _get_active_business(request) -> Tuple[Optional[object], Optional[int]]:
    """
    Return (business_obj, business_id). Accepts pre-attached request.business.
    If only an object is available in legacy code, we still normalize to tuple.
    """
    # Already attached?
    biz = getattr(request, "business", None) or getattr(request, "active_business", None)
    if biz and getattr(biz, "id", None):
        return biz, biz.id

    # Session-stored id?
    sid = request.session.get("active_business_id") or request.session.get("biz_id")
    if sid:
        try:
            from tenants.models import Business
            b = Business.objects.filter(id=sid).first()
            if b:
                _attach_business_to_request(request, b)
                return b, b.id
        except Exception:
            pass

    # Exactly one accepted membership? auto-pick it.
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        try:
            from tenants.models import BusinessMembership, Business
            qs = BusinessMembership.objects.filter(user=user)
            # prefer active/accepted if such fields exist
            for field in ("is_active", "active", "accepted"):
                if field in [f.name for f in BusinessMembership._meta.fields]:
                    try:
                        qs = qs.filter(**{field: True})
                    except Exception:
                        pass
            # if only one membership, choose it
            if qs.count() == 1:
                m = qs.first()
                b = getattr(m, "business", None)
                if b:
                    _attach_business_to_request(request, b)
                    return b, getattr(b, "id", None)
            # fallback: first membership
            m = qs.first()
            if m:
                b = getattr(m, "business", None)
                if b:
                    _attach_business_to_request(request, b)
                    return b, getattr(b, "id", None)
        except Exception:
            pass

    return None, None

def default_location_for_request(request):
    try:
        from inventory.models import Location
        biz, biz_id = _get_active_business(request)
        if not biz_id:
            return None
        # user’s preferred/home location?
        user = getattr(request, "user", None)
        home_loc_id = getattr(getattr(user, "profile", None), "home_location_id", None)
        if home_loc_id:
            loc = Location.objects.filter(id=home_loc_id, business_id=biz_id).first()
            if loc:
                return loc
        # otherwise first active location in the business
        return Location.objects.filter(business_id=biz_id, is_active=True).order_by("id").first()
    except Exception:
        return None

def ensure_request_defaults(request):
    """
    Ensure request has business and location attached & persisted to session.
    Idempotent and safe to call in any view.
    """
    biz, biz_id = _get_active_business(request)
    if biz_id and not getattr(request, "active_location", None):
        loc = default_location_for_request(request)
        if loc:
            _attach_location_to_request(request, loc)
