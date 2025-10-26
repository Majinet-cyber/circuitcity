# inventory/services/timeclock.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Iterable, Tuple, Dict, Any
from django.utils import timezone

ARR, DEP = "ARRIVAL", "DEPARTURE"

def summarize_day(logs: Iterable) -> Dict[str, Any]:
    """
    logs: iterable of TimeLog-like rows for ONE user/day ordered by time.
    Returns working_seconds, offsite_seconds, arrival_at, departure_at.
    """
    working = 0
    offsite = 0
    arrival_at = None
    departure_at = None
    last_in: datetime | None = None
    last_ts: datetime | None = None
    for l in logs:
        ts = getattr(l, "logged_at", None) or timezone.now()
        typ = getattr(l, "checkin_type", "")
        inside = bool(getattr(l, "within_geofence", False))
        if typ == ARR and inside:
            if last_in is None:
                last_in = ts
                if arrival_at is None:
                    arrival_at = ts
        elif typ == DEP or (typ == ARR and not inside):
            # treat as leaving
            if last_in is not None:
                working += int((ts - last_in).total_seconds())
                last_in = None
                departure_at = ts
        last_ts = ts

    # if still inside at end-of-day snapshot, carry to now (or cutoff)
    if last_in is not None and last_ts:
        working += int((last_ts - last_in).total_seconds())

    # Offsite = total span between first and last â€œeventâ€ minus working
    if arrival_at and departure_at and departure_at > arrival_at:
        span = int((departure_at - arrival_at).total_seconds())
        offsite = max(0, span - working)

    return {
        "working_seconds": working,
        "offsite_seconds": offsite,
        "arrival_at": arrival_at,
        "departure_at": departure_at,
    }


