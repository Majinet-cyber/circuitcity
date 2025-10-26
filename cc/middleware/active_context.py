from __future__ import annotations
from typing import Optional
from urllib.parse import urlencode

from django.shortcuts import redirect

# Try to use your existing resolvers, but fall back gracefully.
try:
    from tenants.utils import default_business_for_request  # type: ignore
except Exception:
    def default_business_for_request(request):  # type: ignore
        return getattr(request, "business", None)

try:
    from inventory.utils import default_location_for_request  # type: ignore
except Exception:
    def default_location_for_request(request):  # type: ignore
        return getattr(request, "active_location", None)


# Legacy keys still referenced around the app/templates.
LEGACY_BIZ_IDS = ("active_business_id", "business_id", "tenant_id", "current_business_id")
LEGACY_BIZ_NAMES = ("active_business_name", "business_name", "tenant_name", "current_business_name")
LEGACY_LOC_IDS = ("active_location_id", "location_id", "store_id", "current_location_id")
LEGACY_LOC_NAMES = ("active_location_name", "location_name", "store_name", "current_location_name")


def _first_non_none(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def _coerce_int(v):
    try:
        return int(v)
    except Exception:
        return v


class ActiveContextMiddleware:
    """
    SINGLE SOURCE OF TRUTH for active business/location.
    - Resolves request.business / request.active_location
    - Mirrors to common legacy session keys (ids + names)
    - If a page under /inventory/ or /dashboard/ is missing ?biz/loc,
      but we know them, we redirect to include those params so
      legacy views that read GET instantly agree.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            self._prime_context(request)
            resp = self._maybe_redirect_with_qs(request)
            if resp is not None:
                return resp
        except Exception:
            # Never block the request on context priming.
            pass
        return self.get_response(request)

    # ---------- internals ----------

    def _prime_context(self, request):
        # 1) Respect explicit ?biz / ?loc overrides if present.
        qs_bid = request.GET.get("biz") or request.POST.get("biz")
        qs_lid = request.GET.get("loc") or request.POST.get("loc")
        if qs_bid:
            request.business_id = _coerce_int(qs_bid)
            request.business = None  # force re-resolve below
        if qs_lid:
            request.active_location_id = _coerce_int(qs_lid)
            request.active_location = None

        sess = getattr(request, "session", {}) or {}

        # 2) Seed from session if still missing.
        if not getattr(request, "business", None):
            bid = _first_non_none(*(sess.get(k) for k in LEGACY_BIZ_IDS))
            if bid is not None:
                request.business_id = bid
        if not getattr(request, "active_location", None):
            lid = _first_non_none(*(sess.get(k) for k in LEGACY_LOC_IDS))
            if lid is not None:
                request.active_location_id = lid

        # 3) Resolve actual objects.
        if not getattr(request, "business", None):
            b = default_business_for_request(request)
            if b is not None:
                request.business = b
                request.business_id = getattr(b, "id", getattr(b, "pk", None))
        if not getattr(request, "active_location", None):
            loc = default_location_for_request(request)
            if loc is not None:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", getattr(loc, "pk", None))

        # 4) Derive business from location if necessary.
        if getattr(request, "active_location", None) and not getattr(request, "business", None):
            loc = request.active_location
            b = getattr(loc, "business", None) or getattr(loc, "tenant", None)
            if b is not None:
                request.business = b
                request.business_id = getattr(b, "id", getattr(b, "pk", None))

        # 5) Mirror to legacy session keys so old code/template chips align.
        try:
            changed = False
            b = getattr(request, "business", None)
            if b is not None:
                bid = getattr(b, "id", getattr(b, "pk", None))
                bname = getattr(b, "name", None) or getattr(b, "title", None)
                if bid is not None:
                    for k in LEGACY_BIZ_IDS:
                        if sess.get(k) != bid:
                            sess[k] = bid; changed = True
                if bname:
                    for k in LEGACY_BIZ_NAMES:
                        if sess.get(k) != bname:
                            sess[k] = bname; changed = True

            loc = getattr(request, "active_location", None)
            if loc is not None:
                lid = getattr(loc, "id", getattr(loc, "pk", None))
                lname = getattr(loc, "name", None) or getattr(loc, "title", None)
                if lid is not None:
                    for k in LEGACY_LOC_IDS:
                        if sess.get(k) != lid:
                            sess[k] = lid; changed = True
                if lname:
                    for k in LEGACY_LOC_NAMES:
                        if sess.get(k) != lname:
                            sess[k] = lname; changed = True
            if changed and hasattr(sess, "modified"):
                sess.modified = True
        except Exception:
            pass

    def _maybe_redirect_with_qs(self, request):
        """
        Only for HTML pages under /inventory/ or /dashboard/:
        if ?biz/loc are missing but we know them, redirect to add them.
        """
        path = (request.path or "").rstrip("/")
        if not (path.startswith("/inventory") or path == "/dashboard"):
            return None
        # Donâ€™t redirect API calls or POSTs
        if path.startswith("/inventory/api") or request.method != "GET":
            return None

        need = {}
        if "biz" not in request.GET and getattr(request, "business_id", None) is not None:
            need["biz"] = request.business_id
        if "loc" not in request.GET and getattr(request, "active_location_id", None) is not None:
            need["loc"] = request.active_location_id
        if not need:
            return None

        qs = request.GET.copy()
        for k, v in need.items():
            qs[k] = v
        return redirect(f"{request.path}?{qs.urlencode()}")


