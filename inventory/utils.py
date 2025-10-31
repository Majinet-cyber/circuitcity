# inventory/utils.py
from __future__ import annotations

import math
import re
from datetime import datetime
from functools import wraps
from typing import Optional, Callable

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.urls import reverse  # for invite URL helper

# 🔗 single-source predicates
try:
    from .constants import IN_STOCK_Q, SOLD_Q  # predicates are Q(...) trees
except Exception:
    # very defensive fallback; if constants.py isn't available for any reason
    def SOLD_Q():  # type: ignore
        return Q(status="SOLD") | Q(sold_at__isnull=False) | Q(is_sold=True)
    def IN_STOCK_Q():  # type: ignore
        return ~SOLD_Q() & (Q(in_stock=True) | Q(available=True) | Q(availability=True))


# -----------------------
# Roles / access helpers
# -----------------------
ADMIN = "Admin"
AGENT = "Agent"
AUDITOR = "Auditor"


def user_in_group(user, group_name: str) -> bool:
    """
    True if the authenticated user is superuser or in the named group.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or user.groups.filter(name=group_name).exists())


def require_groups(*group_names: str) -> Callable:
    """
    Decorator to allow only specific groups (or superuser).
    Usage:
        @require_groups(ADMIN, AUDITOR)
        def my_view(request): ...
    """
    def deco(view_func: Callable):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            if not any(user_in_group(request.user, g) for g in group_names):
                raise PermissionDenied("You do not have access to this resource.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return deco


def forbid_auditor_on_write(request: HttpRequest) -> None:
    """
    Call this at the start of a request (e.g., in middleware) to block any
    non-GET methods for Auditor users (read-only).
    """
    unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
    if unsafe and user_in_group(request.user, AUDITOR):
        raise PermissionDenied("Auditors are read-only.")


# -----------------------
# Geo helpers
# -----------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Distance in meters between two lat/lon points.
    """
    R = 6371000.0  # meters
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(round(R * c))


def nearest_location(lat: float, lon: float, *, max_radius_m: Optional[int] = None):
    """
    Return (Location, distance_m) for the nearest Location with (latitude, longitude) fields.
    If no locations (or none within max_radius_m when provided), returns (None, None).
    """
    from .models import Location  # local import to avoid circulars

    best_loc, best_d = None, None
    qs = Location.objects.all().only("id", "name", "latitude", "longitude")
    for loc in qs.iterator():
        lt = getattr(loc, "latitude", None)
        lg = getattr(loc, "longitude", None)
        if lt is None or lg is None:
            continue
        d = haversine_m(lat, lon, lt, lg)
        if (max_radius_m is not None) and d > max_radius_m:
            continue
        if best_d is None or d < best_d:
            best_loc, best_d = loc, d
    return best_loc, best_d


# -----------------------
# Query / filtering utils
# -----------------------
def _parse_date(value: str):
    """
    Best-effort parse of a date string; returns a date when possible,
    otherwise returns the original string (Django will still try to coerce).
    """
    if not value:
        return value
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except Exception:
                pass
    return value


def apply_inventory_filters(request: HttpRequest, qs: QuerySet) -> QuerySet:
    """
    Apply common GET-based filters to an InventoryItem queryset.

    Supported params:
      - status:
          "in"/"in_stock"  -> IN_STOCK_Q()
          "sold"           -> SOLD_Q()
          "all"            -> no status filter
          other string     -> filter(status=<UPPER>)
      - location: numeric id or location name (matches current_location)
      - product: numeric product_id or text (matches product code/name/brand/model/variant)
      - date_from / date_to: filter by received_at date
      - q: text search across IMEI, product name/brand/model/code, and current location name
    """
    # ---- status
    status = (request.GET.get("status") or "").strip().lower()
    if status:
        if status in ("in", "in_stock"):
            qs = qs.filter(IN_STOCK_Q())
        elif status == "sold":
            qs = qs.filter(SOLD_Q())
        elif status == "all":
            pass
        else:
            # verbatim / custom pipeline (upper) for edge schemas
            qs = qs.filter(status=status.upper())

    # ---- location
    loc = (request.GET.get("location") or "").strip()
    if loc:
        try:
            qs = qs.filter(current_location_id=int(loc))
        except ValueError:
            qs = qs.filter(current_location__name__iexact=loc)

    # ---- product
    prod = (request.GET.get("product") or "").strip()
    if prod:
        try:
            qs = qs.filter(product_id=int(prod))
        except ValueError:
            qs = qs.filter(
                Q(product__code__iexact=prod)
                | Q(product__name__icontains=prod)
                | Q(product__brand__icontains=prod)
                | Q(product__model__icontains=prod)
                | Q(product__variant__icontains=prod)
            )

    # ---- date range (by received_at date)
    df = (request.GET.get("date_from") or "").strip()
    if df:
        qs = qs.filter(received_at__date__gte=_parse_date(df))

    dt = (request.GET.get("date_to") or "").strip()
    if dt:
        qs = qs.filter(received_at__date__lte=_parse_date(dt))

    # ---- text search
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__name__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__code__icontains=q)
            | Q(current_location__name__icontains=q)
        )

    return qs


# -----------------------
# User / profile helpers
# -----------------------
def user_home_location(user):
    """
    Preselect the user's home location if they have an AgentProfile with home_location.
    Returns a Location instance or None.
    """
    prof = getattr(user, "agent_profile", None)
    loc_id = getattr(prof, "home_location_id", None) if prof else None
    if not loc_id:
        return None
    from .models import Location  # local import to avoid circulars
    try:
        return Location.objects.get(id=loc_id)
    except Location.DoesNotExist:
        return None


# -----------------------
# Business location helper
# -----------------------
def ensure_default_location(business) -> Optional[object]:
    """
    Return a sensible default location object for the given business.

    Works with either:
      - inventory.models.Location (preferred), or
      - inventory.models.Store   (fallback)

    Behaviour:
      • If an object with is_default=True exists for that business, return it.
      • Else pick the first object.
      • Else create one named "<Business Name> — Main" (or "<Business Name>").
      • If the model supports an 'is_default' field, set it on the chosen object.
      • If the model supports 'is_active', set True on create.
      • If the Store model supports 'kind' or 'type', set to "STORE" on create.

    Never raises; returns the chosen/created object or None.
    """
    if business is None:
        return None

    Loc = Sto = None
    try:
        from .models import Location as Loc  # type: ignore
    except Exception:
        Loc = None
    try:
        from .models import Store as Sto  # type: ignore
    except Exception:
        Sto = None

    def _mark_default(qs, obj, field="is_default"):
        try:
            if hasattr(obj, field):
                try:
                    qs.update(**{field: False})
                except Exception:
                    pass
                if not getattr(obj, field, False):
                    setattr(obj, field, True)
                    try:
                        obj.save(update_fields=[field])
                    except Exception:
                        obj.save()
        except Exception:
            pass

    # Prefer Location first if present
    if Loc is not None:
        try:
            q = Loc.objects.filter(business=business)
            loc = q.filter(is_default=True).first() or q.first()
            if not loc:
                name = getattr(business, "name", "Main")
                defaults = {}
                if hasattr(Loc, "is_active"):
                    defaults["is_active"] = True
                loc = Loc.objects.create(business=business, name=f"{name} — Main", **defaults)
            _mark_default(q, loc, "is_default")
            return loc
        except Exception:
            pass

    # Fallback to Store
    if Sto is not None:
        try:
            q = Sto.objects.filter(business=business)
            loc = q.filter(is_default=True).first() or q.first()
            if not loc:
                name = getattr(business, "name", "Main")
                defaults = {}
                if hasattr(Sto, "is_active"):
                    defaults["is_active"] = True
                if hasattr(Sto, "kind"):
                    defaults["kind"] = "STORE"
                if hasattr(Sto, "type"):
                    defaults["type"] = "STORE"
                loc = Sto.objects.create(business=business, name=f"{name} — Main", **defaults)
            _mark_default(q, loc, "is_default")
            return loc
        except Exception:
            pass

    return None


# -----------------------
# Identifier normalization
# -----------------------
def _normalize_code(raw: str) -> str:
    """
    Keep only digits; useful for generic code/IMEI cleanup before any logic.
    """
    if not raw:
        return ""
    return "".join(ch for ch in str(raw).strip() if ch.isdigit())


def _luhn15(imei14: str) -> int:
    """
    Compute the Luhn check digit (15th) for a 14-digit IMEI TAC+SNR.
    """
    digits = [int(d) for d in imei14]
    total = 0
    for i, d in enumerate(digits, start=1):
        if i % 2 == 0:
            d *= 2
            total += (d // 10) + (d % 10)
        else:
            total += d
    return (10 - (total % 10)) % 10


def normalize_imei(raw: str) -> str:
    """
    Normalize user input to a 15-digit IMEI:
      • strip all non-digits
      • if 14 digits, append Luhn check digit
      • if 15+ digits, take the first 15 (most scanners put the IMEI first)
      • otherwise return the digits as-is (likely <14 -> won't match)
    """
    digits = _normalize_code(raw)
    if len(digits) == 14:
        return digits + str(_luhn15(digits))
    if len(digits) >= 15:
        return digits[:15]
    return digits


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


# -----------------------
# Business-wide in-stock lookup (UPDATED to use IN_STOCK_Q)
# -----------------------
def get_instock_item_for_business(business, code_or_imei: str, *, for_update: bool = False):
    """
    Return the first UNSOLD inventory item for this business that matches the IMEI/code,
    regardless of location. Designed to be the SINGLE SOURCE OF TRUTH for "is this
    in stock anywhere in the business?"

    Behavior:
      - If model has `imei`, we try normalized 15-digit IMEI first, then the raw digits fallback.
      - Else if model has `code`, match on cleaned digits.
      - Unsold/Sold semantics are delegated to IN_STOCK_Q().
      - If for_update=True, uses select_for_update(skip_locked=True) to prevent race conditions.
    """
    if business is None:
        return None

    from .models import InventoryItem  # adjust to your actual item model

    raw_digits = _normalize_code(code_or_imei)
    imei15 = normalize_imei(raw_digits)

    # Base queryset (business scoped)
    qs = InventoryItem.objects.filter(business=business)

    # Optional archival filter
    if _model_has_field(InventoryItem, "is_archived"):
        qs = qs.filter(is_archived=False)

    # Choose identifier field and apply filters
    if _model_has_field(InventoryItem, "imei"):
        # Prefer exact 15-digit IMEI; keep a lenient fallback to raw_digits to tolerate legacy data
        ident_q = Q(imei=imei15)
        if raw_digits and raw_digits != imei15:
            ident_q |= Q(imei=raw_digits)
        qs = qs.filter(ident_q)
    elif _model_has_field(InventoryItem, "code"):
        qs = qs.filter(code=raw_digits)
    else:
        # No known identifier; nothing we can do
        return None

    # Canonical "in stock" predicate
    qs = qs.filter(IN_STOCK_Q())

    # Helpful for UI display but optional
    if _model_has_field(InventoryItem, "current_location"):
        qs = qs.select_related("current_location")

    if for_update:
        try:
            qs = qs.select_for_update(skip_locked=True)
        except Exception:
            qs = qs.select_for_update()

    return qs.order_by("-id").first()


# -----------------------
# Invite helpers
# -----------------------
def get_invite_token(inv) -> Optional[str]:
    """
    Return the invite's token regardless of field naming differences.
    Tries 'token', then 'code', then 'key'.
    """
    return getattr(inv, "token", None) or getattr(inv, "code", None) or getattr(inv, "key", None)


def invite_join_url(request: HttpRequest, token: str, route_name: str = "join_by_token") -> str:
    """
    Build a tenant-aware absolute URL for an invite token.

    Args:
        request: current HttpRequest (used for host/tenant domain).
        token: the invitation token string.
        route_name: your urlpattern name for joining by token (default 'join_by_token').

    Returns:
        Absolute URL string, e.g. https://your-tenant.example.com/tenants/join/<token>/
    """
    path = reverse(route_name, args=[token])
    return request.build_absolute_uri(path)


__all__ = [
    # roles / access
    "ADMIN",
    "AGENT",
    "AUDITOR",
    "user_in_group",
    "require_groups",
    "forbid_auditor_on_write",
    # geo
    "haversine_m",
    "nearest_location",
    # filters
    "apply_inventory_filters",
    # users
    "user_home_location",
    # business location helper
    "ensure_default_location",
    # normalization + business-wide stock helpers
    "_normalize_code",
    "normalize_imei",
    "get_instock_item_for_business",
    # invites
    "get_invite_token",
    "invite_join_url",
]
