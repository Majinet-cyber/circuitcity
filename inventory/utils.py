# inventory/utils.py
from __future__ import annotations

import math
from datetime import datetime
from functools import wraps
from typing import Optional, Callable

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest


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
      - status: "in"/"in_stock" -> exclude SOLD, "sold" -> only SOLD, "all" -> no status filter,
                otherwise matched verbatim (uppercased)
      - location: numeric id or location name (matches current_location)
      - product: numeric product_id or text (matches product code/name/brand/model/variant)
      - date_from / date_to: filter by received_at date
      - q: text search across IMEI, product name/brand/model/code, and current location name
    """
    # ---- status
    status = (request.GET.get("status") or "").strip().lower()
    if status:
        if status in ("in", "in_stock"):
            qs = qs.exclude(status="SOLD")
        elif status == "sold":
            qs = qs.filter(status="SOLD")
        elif status == "all":
            pass
        else:
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
]
