# inventory/helpers_timeclock.py
from __future__ import annotations
from dataclasses import dataclass
from math import cos, radians, sqrt
from typing import Optional, Tuple
from django.utils import timezone
from .models_timeclock import TimeGeofence, TimeSession, TimeEvent

def _haversine_approx_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fast flat-earth approximation (accurate enough for <1km)."""
    k = 111_320.0  # meters per degree latitude
    x = (lon2 - lon1) * k * cos(radians((lat1 + lat2) / 2.0))
    y = (lat2 - lat1) * k
    return sqrt(x * x + y * y)

@dataclass
class GeoEval:
    inside: bool
    geofence: Optional[TimeGeofence]
    distance_m: Optional[float]

def pick_matching_geofence(biz, lat: float, lon: float) -> GeoEval:
    fences = TimeGeofence.objects.filter(business=biz, is_active=True)
    best: Tuple[Optional[TimeGeofence], float] = (None, 9e9)
    for f in fences:
        d = _haversine_approx_m(lat, lon, f.lat, f.lon)
        if d < best[1]:
            best = (f, d)
    gf, d = best
    if gf and d <= float(gf.radius_m):
        return GeoEval(True, gf, d)
    return GeoEval(False, gf, d if gf else None)

def _tenant_today():
    # OK to use server date; if you have per-tenant TZ, inject here
    return timezone.localdate()

def get_or_create_session(biz, user, gf: TimeGeofence) -> TimeSession:
    day = _tenant_today()
    sess, _ = TimeSession.objects.get_or_create(
        business=biz, user=user, geofence=gf, day=day,
        defaults={"state": TimeSession.State.OFFSITE, "state_since": timezone.now()},
    )
    return sess

def close_if_idle(sess: TimeSession, now=None):
    now = now or timezone.now()
    # Close past midnight or after explicit depart already set
    if sess.state != TimeSession.State.CLOSED and sess.departure_at:
        sess.accumulate_until(now)
        sess.state = TimeSession.State.CLOSED
        sess.save(update_fields=["state", "work_s", "offsite_s", "state_since", "updated_at"])
        TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.CLOSE, at=now)

def process_geo_ping(*, biz, user, lat: float, lon: float, accuracy_m: float, now=None):
    """
    Core state machine:
      - First ping inside -> ARRIVE (start onsite)
      - Stay inside -> accumulate ONSITE
      - Move outside -> DEPART (or OFFSITE if will come back); accumulate OFFSITE
      - End-of-day close handled separately
    """
    now = now or timezone.now()
    eval = pick_matching_geofence(biz, lat, lon)

    # No active fences â€” nothing to do
    if not eval.geofence:
        return None, {"inside": False, "geofence": None, "distance_m": None}

    sess = get_or_create_session(biz, user, eval.geofence)
    sess.accumulate_until(now)

    # Transition rules
    if eval.inside:
        if sess.arrival_at is None:
            sess.arrival_at = now
            TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.ARRIVE, at=now,
                                     lat=lat, lon=lon, accuracy_m=accuracy_m)
        if sess.state != TimeSession.State.ONSITE:
            TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.ONSITE, at=now,
                                     lat=lat, lon=lon, accuracy_m=accuracy_m)
        sess.state = TimeSession.State.ONSITE
    else:
        # Leaving site
        if sess.arrival_at and not sess.departure_at:
            sess.departure_at = now  # latest known depart time
            TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.DEPART, at=now,
                                     lat=lat, lon=lon, accuracy_m=accuracy_m)
        if sess.state != TimeSession.State.OFFSITE:
            TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.OFFSITE, at=now,
                                     lat=lat, lon=lon, accuracy_m=accuracy_m)
        sess.state = TimeSession.State.OFFSITE

    # Always log the ping
    TimeEvent.objects.create(session=sess, kind=TimeEvent.Kind.PING, at=now,
                             lat=lat, lon=lon, accuracy_m=accuracy_m)

    sess.save(update_fields=[
        "arrival_at", "departure_at", "work_s", "offsite_s", "state", "state_since", "updated_at"
    ])

    payload = {
        "inside": eval.inside,
        "geofence": {
            "id": sess.geofence_id,
            "name": sess.geofence.name,
            "lat": sess.geofence.lat,
            "lon": sess.geofence.lon,
            "radius_m": sess.geofence.radius_m,
        },
        "distance_m": round(eval.distance_m or 0, 1),
        "session": {
            "id": sess.id,
            "state": sess.state,
            "arrival_at": sess.arrival_at,
            "departure_at": sess.departure_at,
            "work_s": sess.work_s,
            "offsite_s": sess.offsite_s,
        },
        "now": now,
    }
    return sess, payload


