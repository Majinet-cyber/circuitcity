# circuitcity/tenants/api_view.py
from __future__ import annotations

from typing import Any, Dict

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from .utils import (
    get_active_business,
    set_active_business,
    user_is_manager,
    user_is_admin,
    _has_active_membership,
    scoped,  # role-aware queryset scoping
)
from .models import Business, Membership

# Optional imports – these may not exist during early wiring; we stay defensive.
try:
    from inventory.models import InventoryItem, Location  # type: ignore
except Exception:  # pragma: no cover
    InventoryItem = None  # type: ignore
    Location = None  # type: ignore


# -----------------------------
# Helpers
# -----------------------------
def _err(msg: str, code: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=code)


def _biz_payload(b) -> Dict[str, Any]:
    if not b:
        return {"id": None, "name": None, "slug": None, "status": None}
    return {
        "id": b.id,
        "name": getattr(b, "name", None),
        "slug": getattr(b, "slug", None),
        "status": getattr(b, "status", None),
    }


def _role_payload(user, business) -> Dict[str, Any]:
    role = None
    status = None
    try:
        m = Membership.objects.filter(user=user, business=business).first()
        if m:
            role = getattr(m, "role", None)
            status = getattr(m, "status", None)
    except Exception:
        pass
    return {
        "role": role,
        "status": status,
        "is_manager": bool(user_is_manager(user)),
        "is_admin": bool(user_is_admin(user)),
    }


# -----------------------------
# Endpoints
# -----------------------------

@login_required
@require_GET
def api_current_business(request: HttpRequest) -> JsonResponse:
    """
    GET /tenants/api/current
    -> { ok, business:{id,name,slug,status}, role:{...} }
    """
    b = get_active_business(request)
    return JsonResponse(
        {"ok": True, "business": _biz_payload(b), "role": _role_payload(request.user, b)}
    )


@login_required
@require_POST
def api_switch_business(request: HttpRequest) -> JsonResponse:
    """
    POST /tenants/api/switch  body: { "business_id": <int> }
    Switch active tenant if the user has an ACTIVE membership there.
    """
    try:
        bid = int((request.POST.get("business_id") or request.GET.get("business_id") or "").strip())
    except Exception:
        return _err("Provide a valid business_id.", 400)

    try:
        b = Business.objects.get(pk=bid)
    except Business.DoesNotExist:
        return _err("Business not found.", 404)

    if not _has_active_membership(request.user, b):
        return _err("You are not a member of that business.", 403)

    set_active_business(request, b)
    return JsonResponse({"ok": True, "business": _biz_payload(b)})


@login_required
@require_GET
def api_my_memberships(request: HttpRequest) -> JsonResponse:
    """
    GET /tenants/api/memberships
    -> { ok, items:[{business:{...}, role, status}] }
    """
    items = []
    try:
        qs = (
            Membership.objects.select_related("business")
            .filter(user=request.user)
            .order_by("business__name")
        )
        for m in qs:
            items.append(
                {
                    "business": _biz_payload(getattr(m, "business", None)),
                    "role": getattr(m, "role", None),
                    "status": getattr(m, "status", None),
                }
            )
    except Exception:
        pass
    return JsonResponse({"ok": True, "items": items})


# -----------------------------
# Optional: quick scoping sanity checks
# -----------------------------
@login_required
@require_GET
def api_scope_preview(request: HttpRequest) -> JsonResponse:
    """
    GET /tenants/api/scope-preview
    Returns quick counts showing what the current user sees after role-aware scoping.
    This helps verify that agents do NOT see global stock.

    If Inventory models aren't wired, it will still return ok:true with zeroes.
    """
    b = get_active_business(request)
    data: Dict[str, Any] = {
        "business": _biz_payload(b),
        "role": _role_payload(request.user, b),
        "inventory": {"in_stock": 0, "sold": 0, "total": 0},
        "locations": [],
    }

    # Locations visible to user (if Location exists)
    try:
        if Location is not None:
            loc_qs = Location.objects.filter(business=b)
            # If your Location has memberships relation, filter by that for agents
            try:
                if not user_is_manager(request.user):
                    loc_qs = loc_qs.filter(memberships__user=request.user)
            except Exception:
                pass
            data["locations"] = [
                {"id": x.id, "name": getattr(x, "name", None)} for x in loc_qs[:50]
            ]
    except Exception:
        pass

    # Inventory counts via role-aware scoping
    try:
        if InventoryItem is not None:
            base = scoped(InventoryItem.objects.all(), request)  # role-aware + tenant-aware
            data["inventory"]["total"] = base.count()

            if hasattr(InventoryItem, "status"):
                data["inventory"]["in_stock"] = base.exclude(status="SOLD").count()
                data["inventory"]["sold"] = base.filter(status="SOLD").count()
    except Exception:
        pass

    return JsonResponse({"ok": True, "data": data})
