# core/utils.py
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional, Tuple, Any

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import QuerySet

User = get_user_model()


# -----------------------------------------------------------------------------
# Generic Helpers (safe conversions, formatting, math)
# -----------------------------------------------------------------------------
def safe_int(val: Any, default: int = 0) -> int:
    """Safely cast to int without raising ValueError."""
    try:
        return int(val)
    except Exception:
        return default


def human_timedelta(td: timedelta) -> str:
    """Convert timedelta â†’ '2h 15m' or '45m' human-friendly string."""
    total_minutes = int(td.total_seconds() // 60)
    hours, mins = divmod(total_minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    elif hours:
        return f"{hours}h"
    else:
        return f"{mins}m"


def days_between(start: datetime, end: datetime) -> int:
    """Inclusive day span between two datetimes."""
    return max(0, (end.date() - start.date()).days)


# -----------------------------------------------------------------------------
# Geo helpers (used for location/time tracking)
# -----------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance (in meters) between two lat/lon pairs."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def in_geofence(lat: float, lng: float, center: Tuple[float, float], radius_m: int) -> bool:
    """Return True if (lat,lng) is within radius_m of center."""
    if not all(center):
        return True  # No coordinates defined â€” treat as inside
    dist = haversine_m(lat, lng, center[0], center[1])
    return dist <= radius_m


# -----------------------------------------------------------------------------
# Gamification + Greetings
# -----------------------------------------------------------------------------
def should_show_greeting(profile) -> bool:
    """
    Decide if we should greet the user again (after 24h).
    """
    now = timezone.now()
    if not profile.greeting_last_at:
        return True
    return (now - profile.greeting_last_at) >= timedelta(hours=24)


def make_greeting(user: User) -> str:
    """Return personalized greeting message depending on time of day."""
    now = timezone.localtime()
    hour = now.hour
    name = user.first_name or user.username or "there"

    if hour < 12:
        return f"Good morning, {name} â˜€ï¸"
    elif 12 <= hour < 17:
        return f"Good afternoon, {name} ðŸŒ¤ï¸"
    else:
        return f"Good evening, {name} ðŸŒ™"


def generate_did_you_know(profile) -> list[str]:
    """
    Return motivational or performance-based â€œDid you know...â€ messages.
    """
    tips = []
    if profile.last_month_sales:
        tips.append(f"Did you know you made MWK {profile.last_month_sales:,.0f} in sales last month?")
    if profile.last_month_profit:
        tips.append(f"Did you know your profit last month was MWK {profile.last_month_profit:,.0f}?")
    tips.append("Did you know consistent logging improves team trust? ðŸ’ª")
    tips.append("Keep pushing â€” excellence becomes habit when tracked daily.")
    return tips


# -----------------------------------------------------------------------------
# Query helpers
# -----------------------------------------------------------------------------
def get_active_agents(qs: QuerySet, business_id: Optional[int] = None) -> QuerySet:
    """Filter active agents for a given business (if applicable)."""
    if business_id:
        qs = qs.filter(business_id=business_id)
    return qs.filter(is_active=True).order_by("first_name", "last_name")


# -----------------------------------------------------------------------------
# Time / session helpers
# -----------------------------------------------------------------------------
def time_diff_minutes(start: datetime, end: datetime) -> int:
    """Return minutes between two datetimes (rounded down)."""
    return int(max(0, (end - start).total_seconds() // 60))


def round_to_nearest_minute(dt: datetime) -> datetime:
    """Drop seconds and microseconds for cleaner session metrics."""
    return dt.replace(second=0, microsecond=0)


def format_money(amount: float, currency: str = "MWK") -> str:
    """Return formatted currency string."""
    try:
        return f"{currency} {float(amount):,.0f}"
    except Exception:
        return f"{currency} 0"


# -----------------------------------------------------------------------------
# Notifications
# -----------------------------------------------------------------------------
def push_notification(user: User, title: str, message: str, *, kind: str = "INFO", business=None) -> None:
    """
    Create a Notification object (if model is loaded).
    Best-effort; fails silently if model import fails (during setup).
    """
    try:
        from core.models import Notification  # type: ignore
        Notification.objects.create(
            user=user,
            kind=kind,
            title=title[:140],
            message=message,
            business=business,
        )
    except Exception:
        pass


