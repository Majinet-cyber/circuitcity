# inventory/views_time.py
from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from datetime import timedelta, datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseBadRequest,
    StreamingHttpResponse,
)
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from tenants.models import Membership
from tenants.utils import get_active_business, require_business
from .models import Location
from .models_attendance import TimeLog, compute_attendance_outcome

User = get_user_model()

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _active_biz_id(request: HttpRequest) -> Optional[int]:
    """Get the active business ID from request."""
    biz = get_active_business(request)
    return biz.id if biz else None


def _wants_json(request: HttpRequest) -> bool:
    h = request.headers
    if h.get("X-Requested-With") == "XMLHttpRequest":
        return True
    ct = h.get("Content-Type") or ""
    accept = h.get("Accept") or ""
    return "application/json" in ct or "application/json" in accept


def _agent_default_location(request: HttpRequest) -> Optional[Location]:
    biz_id = _active_biz_id(request)
    if not biz_id:
        return None
    mem = Membership.objects.filter(user=request.user, business_id=biz_id).select_related("location").first()
    if mem and getattr(mem, "location_id", None):
        return mem.location
    qs = Location.objects.filter(business_id=biz_id).order_by("id")
    return qs.filter(name__icontains="store").first() or qs.first()


def _can_manage_time_logs(user, biz_id: Optional[int]) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if not biz_id:
        return False
    role = (
        Membership.objects.filter(user=user, business_id=biz_id, status="ACTIVE")
        .values_list("role", flat=True)
        .first()
    )
    return str(role or "").strip().upper() in {"OWNER", "ADMIN", "MANAGER", "SUPERVISOR", "FINANCE"}


def _decimal_or_none(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _int_or_none(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return max(int(round(float(value))), 0)
    except (TypeError, ValueError):
        return None


def _distance_m(lat1, lon1, lat2, lon2) -> int:
    radius_m = 6371000
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


def _attendance_location(biz_id: int) -> Optional[Location]:
    qs = Location.objects.filter(business_id=biz_id).order_by("id")
    return qs.filter(is_default=True).first() or qs.first()


def _active_shift_start(user, biz_id: int, start, end) -> Optional[TimeLog]:
    latest = (
        TimeLog.objects.filter(business_id=biz_id, user=user, ts__gte=start, ts__lt=end)
        .order_by("-ts", "-id")
        .first()
    )
    if latest and latest.kind == "ARRIVAL":
        return latest
    return None


def _attendance_status_context(user, biz_id: Optional[int], start, end) -> Dict[str, object]:
    if not biz_id:
        return {
            "is_checked_in": False,
            "checked_in_since": None,
            "active_work_seconds": 0,
            "server_now": timezone.localtime().isoformat(),
            "status_text": "No active business selected",
        }
    active_log = _active_shift_start(user, biz_id, start, end)
    events = list(
        TimeLog.objects.filter(business_id=biz_id, user=user, ts__gte=start, ts__lt=end).order_by("ts", "id")
    )
    total_work_seconds, _, _ = _pair_work_seconds(events, timezone.now())
    if active_log:
        checked_in = timezone.localtime(active_log.ts)
        return {
            "is_checked_in": True,
            "checked_in_since": checked_in.isoformat(),
            "active_work_seconds": total_work_seconds,
            "server_now": timezone.localtime().isoformat(),
            "status_text": f"You are checked in since {checked_in:%H:%M}",
        }
    return {
        "is_checked_in": False,
        "checked_in_since": None,
        "active_work_seconds": total_work_seconds,
        "server_now": timezone.localtime().isoformat(),
        "status_text": "You are not checked in yet",
    }


def _geo_for_location(location: Optional[Location], lat: Optional[Decimal], lon: Optional[Decimal]) -> Dict[str, object]:
    if lat is None or lon is None:
        return {"status": "No GPS", "distance_m": None}
    if not location or location.latitude is None or location.longitude is None:
        return {"status": "No Location Configured", "distance_m": None}
    distance = _distance_m(lat, lon, location.latitude, location.longitude)
    radius = int(getattr(location, "geofence_radius_m", None) or 150)
    return {"status": "Inside Zone" if distance <= radius else "Outside Zone", "distance_m": distance}


def _location_payload(location: Optional[Location]) -> Dict[str, object]:
    return {
        "name": getattr(location, "name", None),
        "radius_m": getattr(location, "geofence_radius_m", None),
        "latitude": str(location.latitude) if location and location.latitude is not None else None,
        "longitude": str(location.longitude) if location and location.longitude is not None else None,
    }


def _parse_local_date(s: str | None) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Treat as local date (no tz); convert to aware at local midnight
        y, m, d = [int(x) for x in s.split("-")]
        dt = datetime(y, m, d, 0, 0, 0)
        # localize to current timezone
        return timezone.make_aware(dt, timezone.get_current_timezone())
    except Exception:
        return None


def _day_bounds(now=None) -> Tuple[timezone.datetime, timezone.datetime]:
    """Start/end for 'today' in local tz."""
    now = now or timezone.localtime()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _range_bounds(request: HttpRequest) -> Tuple[timezone.datetime, timezone.datetime]:
    """
    Choose a time window:
      - `day=YYYY-MM-DD` → that calendar day
      - or `from=YYYY-MM-DD` & `to=YYYY-MM-DD` (inclusive of 'to' day)
      - else → today
    """
    day = _parse_local_date(request.GET.get("day"))
    if day:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    from_d = _parse_local_date(request.GET.get("from"))
    to_d = _parse_local_date(request.GET.get("to"))
    if from_d and to_d:
        start = from_d.replace(hour=0, minute=0, second=0, microsecond=0)
        end = to_d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return start, end

    return _day_bounds()


def _serialize_log(row: TimeLog) -> Dict[str, object]:
    u = getattr(row, "user", None)
    loc = getattr(row, "location", None)
    return {
        "id": getattr(row, "id", None),
        "ts": timezone.localtime(getattr(row, "ts")).isoformat() if getattr(row, "ts", None) else None,
        "kind": getattr(row, "kind", None),
        "user": (
            getattr(u, "get_full_name", lambda: "")() or getattr(u, "username", None) or getattr(u, "email", None)
        ),
        "user_id": getattr(u, "id", None),
        "location": getattr(loc, "name", None),
        "lat": getattr(row, "lat", None),
        "lon": getattr(row, "lon", None),
        "accuracy_m": getattr(row, "accuracy_m", None),
        "distance_m": getattr(row, "distance_m", None),
        "geofence": getattr(row, "geofence_status", None) or getattr(row, "geo_status", None),
        "note": getattr(row, "note", None),
    }


def _format_seconds(seconds: int) -> str:
    seconds = max(int(seconds or 0), 0)
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _geo_label(ev: Optional[TimeLog]) -> Tuple[str, str]:
    if not ev or (getattr(ev, "lat", None) in (None, "") and getattr(ev, "lon", None) in (None, "")):
        return "No GPS", "muted"
    raw = getattr(ev, "geofence_status", None) or getattr(ev, "geo_status", None)
    raw_s = str(raw or "").strip().lower()
    if raw_s in {"inside", "inside zone", "in", "true", "1", "ok", "within"}:
        return "Inside Zone", "ok"
    if raw_s in {"outside", "outside zone", "out", "false", "0"}:
        return "Outside Zone", "warn"
    if raw_s in {"no gps", "no location configured"}:
        return str(raw or "No GPS"), "muted"
    return "Unknown Zone", "info"


# ---------------------------------------------------------------------
# Agent check-in page (session flags drive client clocks)
# ---------------------------------------------------------------------


@login_required
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def time_checkin(request: HttpRequest) -> HttpResponse:
    gate = require_business(request)
    if gate:
        return gate

    biz_id = _active_biz_id(request)
    location = _agent_default_location(request)

    if request.method == "GET":
        ctx = {
            "location": location,
            "shift_on": bool(request.session.get("shift_on", False)),
            "shift_started_at": request.session.get("shift_started_at", None),
        }
        return render(request, "inventory/time_checkin.html", ctx)

    # POST (form or JSON)
    kind: str = "ARRIVAL"
    lat: Optional[str] = None
    lon: Optional[str] = None

    if (request.headers.get("Content-Type") or "").startswith("application/json"):
        try:
            import json

            payload = json.loads((request.body or b"").decode("utf-8") or "{}")
        except Exception:
            if _wants_json(request):
                return HttpResponseBadRequest("Invalid JSON payload")
            messages.error(request, "Check-in failed: invalid data.")
            return redirect("inventory:time_checkin")

        kind = (payload.get("type") or payload.get("kind") or "ARRIVAL").upper()
        lat = payload.get("lat")
        lon = payload.get("lon")
        location_id = payload.get("location_id")
        if location_id:
            try:
                location = Location.objects.get(id=location_id, business_id=biz_id)
            except Location.DoesNotExist:
                pass
    else:
        kind = (request.POST.get("type") or request.POST.get("kind") or "ARRIVAL").upper()
        lat = request.POST.get("lat") or None
        lon = request.POST.get("lon") or None
        loc_id = request.POST.get("location_id")
        if loc_id:
            try:
                location = Location.objects.get(id=loc_id, business_id=biz_id)
            except Location.DoesNotExist:
                pass

    if kind not in {"ARRIVAL", "DEPARTURE"}:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Invalid check-in type."}, status=400)
        messages.error(request, "Invalid check-in type.")
        return redirect("inventory:time_checkin")

    tl = TimeLog.objects.create(
        business_id=biz_id,
        user=request.user,
        location=location,
        kind=kind,
        lat=lat,
        lon=lon,
    )

    # session flags to drive client clocks
    if kind == "ARRIVAL":
        if not request.session.get("shift_on", False):
            request.session["shift_on"] = True
            request.session["shift_started_at"] = timezone.now().isoformat()
    else:  # DEPARTURE
        request.session["shift_on"] = False
        request.session.pop("shift_started_at", None)

    outcome = compute_attendance_outcome(tl.ts, kind)
    net = outcome.net_adjustment or 0

    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "log": {
                    "id": tl.id,
                    "ts": timezone.localtime(tl.ts).isoformat(),
                    "kind": tl.kind,
                    "location": getattr(location, "name", None),
                    "lat": tl.lat,
                    "lon": tl.lon,
                },
                "adjustment": {
                    "bonus": (getattr(outcome, "early_bonus", 0) or 0) + (getattr(outcome, "weekend_bonus", 0) or 0),
                    "deduction": getattr(outcome, "late_deduction", 0) or 0,
                    "net": net,
                },
                "shift_on": bool(request.session.get("shift_on", False)),
                "shift_started_at": request.session.get("shift_started_at"),
                "message": (
                    f"+MWK {net:,} attendance bonus applied."
                    if net > 0
                    else (f"-MWK {abs(net):,} late deduction applied." if net < 0 else "Recorded.")
                ),
            }
        )

    if net > 0:
        messages.success(request, f"+MWK {net:,} attendance bonus applied.")
    elif net < 0:
        messages.warning(request, f"-MWK {abs(net):,} late deduction applied.")
    messages.info(request, f"{kind.title()} recorded.")
    return redirect("inventory:my_time_logs")


@login_required
@require_http_methods(["POST"])
def time_attendance_action(request: HttpRequest) -> JsonResponse:
    biz_id = _active_biz_id(request)
    if not biz_id:
        return JsonResponse({"ok": False, "error": "no_active_business"}, status=400)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except ValueError:
        payload = request.POST

    action = str(payload.get("action") or payload.get("kind") or "").strip().upper()
    if action in {"CHECK_IN", "CHECKIN", "ARRIVAL", "START"}:
        kind = "ARRIVAL"
    elif action in {"CHECK_OUT", "CHECKOUT", "DEPARTURE", "END"}:
        kind = "DEPARTURE"
    elif action in {"GPS_CHECK", "GEO_PING", "GEOFENCE_CHECK"}:
        kind = "GPS_CHECK"
    else:
        return JsonResponse({"ok": False, "error": "invalid_action"}, status=400)

    start, end = _day_bounds()
    location = _attendance_location(biz_id)
    lat = _decimal_or_none(payload.get("latitude") or payload.get("lat"))
    lon = _decimal_or_none(payload.get("longitude") or payload.get("lon") or payload.get("lng"))
    accuracy_m = _int_or_none(payload.get("accuracy") or payload.get("accuracy_m"))
    geo = _geo_for_location(location, lat, lon)

    with transaction.atomic():
        active_log = (
            TimeLog.objects.select_for_update()
            .filter(business_id=biz_id, user=request.user, ts__gte=start, ts__lt=end)
            .order_by("-ts", "-id")
            .first()
        )
        has_active_shift = bool(active_log and active_log.kind == "ARRIVAL")
        if kind == "GPS_CHECK":
            if not has_active_shift:
                return JsonResponse(
                    {
                        "ok": True,
                        "auto_checked_out": False,
                        "message": "No active shift.",
                        "status": _attendance_status_context(request.user, biz_id, start, end),
                        "location": _location_payload(location),
                        "geofence": geo,
                    }
                )
            if geo["status"] == "No GPS":
                return JsonResponse(
                    {
                        "ok": True,
                        "auto_checked_out": False,
                        "warning": "Enable location to verify attendance zone.",
                        "status": _attendance_status_context(request.user, biz_id, start, end),
                        "location": _location_payload(location),
                        "geofence": geo,
                    }
                )
            if geo["status"] != "Outside Zone":
                return JsonResponse(
                    {
                        "ok": True,
                        "auto_checked_out": False,
                        "status": _attendance_status_context(request.user, biz_id, start, end),
                        "location": _location_payload(location),
                        "geofence": geo,
                    }
                )

            log = TimeLog.objects.create(
                business_id=biz_id,
                user=request.user,
                location=location,
                kind="DEPARTURE",
                lat=lat,
                lon=lon,
                accuracy_m=accuracy_m,
                distance_m=geo["distance_m"],
                geofence_status=geo["status"],
                note="Auto checkout: outside geofence",
            )
            request.session["shift_on"] = False
            request.session.pop("shift_started_at", None)
            return JsonResponse(
                {
                    "ok": True,
                    "auto_checked_out": True,
                    "log": _serialize_log(log),
                    "status": _attendance_status_context(request.user, biz_id, start, end),
                    "location": _location_payload(location),
                    "geofence": geo,
                    "message": "Auto checkout: outside geofence",
                }
            )

        if kind == "ARRIVAL" and has_active_shift:
            return JsonResponse({"ok": False, "error": "already_checked_in"}, status=409)
        if kind == "DEPARTURE" and not has_active_shift:
            return JsonResponse({"ok": False, "error": "not_checked_in"}, status=409)

        note_parts = []
        client_note = str(payload.get("note") or "").strip()
        if client_note:
            note_parts.append(client_note)
        if not location:
            note_parts.append("No attendance location configured.")
        elif location.latitude is None or location.longitude is None:
            note_parts.append("Attendance location has no coordinates.")

        log = TimeLog.objects.create(
            business_id=biz_id,
            user=request.user,
            location=location,
            kind=kind,
            lat=lat,
            lon=lon,
            accuracy_m=accuracy_m,
            distance_m=geo["distance_m"],
            geofence_status=geo["status"],
            note=" ".join(note_parts),
        )

    request.session["shift_on"] = kind == "ARRIVAL"
    if kind == "ARRIVAL":
        request.session["shift_started_at"] = timezone.now().isoformat()
    else:
        request.session.pop("shift_started_at", None)

    return JsonResponse(
        {
            "ok": True,
            "log": _serialize_log(log),
            "status": _attendance_status_context(request.user, biz_id, start, end),
            "location": _location_payload(location),
            "geofence": geo,
        }
    )


@login_required
def my_time_logs(request: HttpRequest) -> HttpResponse:
    gate = require_business(request)
    if gate:
        return gate

    biz_id = _active_biz_id(request)
    logs = (
        TimeLog.objects.filter(business_id=biz_id, user=request.user).select_related("location").order_by("-ts")[:200]
    )
    return render(request, "inventory/time_logs.html", {"logs": logs})


# ---------------------------------------------------------------------
# Manager view: collect per-agent work/idle + latest log
# ---------------------------------------------------------------------


def _pair_work_seconds(events: List[TimeLog], now_local) -> Tuple[int, bool, Optional[str]]:
    """
    Given ordered TimeLogs for a user in a window, compute total work seconds.
    Returns: (work_secs, on_shift, last_ts_iso)
    """
    work = 0
    on_shift = False
    start = None
    last_ts_iso = None

    for e in events:
        last_ts_iso = timezone.localtime(e.ts).isoformat()
        if e.kind == "ARRIVAL":
            if start is None:
                start = e.ts
            on_shift = True
        elif e.kind == "DEPARTURE":
            if start is not None:
                work += int((e.ts - start).total_seconds())
                start = None
            on_shift = False

    if start is not None:
        work += int((now_local - start).total_seconds())
        on_shift = True

    return max(work, 0), on_shift, last_ts_iso


def _collect_manager_overview(
    biz_id: int,
    start: timezone.datetime,
    end: timezone.datetime,
    expected_shift_seconds: int,
    *,
    visible_user_id: Optional[int] = None,
) -> Dict[str, object]:
    """
    Build a per-agent summary for the window [start, end), with a 'battery'.
    Also include the latest event details per user for convenience.
    """
    now_local = timezone.localtime()
    horizon_seconds = int((min(now_local, end) - start).total_seconds())
    horizon_seconds = max(horizon_seconds, 0)
    attendance_location = _attendance_location(biz_id)

    members = Membership.objects.filter(business_id=biz_id).select_related("user", "location")
    if visible_user_id:
        members = members.filter(user_id=visible_user_id)

    events = (
        TimeLog.objects.filter(business_id=biz_id, ts__gte=start, ts__lt=end)
        .select_related("user", "location")
        .order_by("user_id", "ts")
    )
    if visible_user_id:
        events = events.filter(user_id=visible_user_id)

    by_user: Dict[int, List[TimeLog]] = defaultdict(list)
    last_event: Dict[int, TimeLog] = {}

    for ev in events:
        by_user[ev.user_id].append(ev)
        last_event[ev.user_id] = ev

    agents: List[Dict[str, object]] = []
    attendance_rows: List[Dict[str, object]] = []
    present = late = active = completed = no_checkout = 0
    total_work_secs = 0
    total_idle_secs = 0
    grace_minutes = 15
    expected_start = start.replace(hour=8, minute=0, second=0, microsecond=0)
    late_cutoff = expected_start + timedelta(minutes=grace_minutes)

    for m in members:
        u = m.user
        u_events = by_user.get(u.id, [])
        work_secs, on_shift, last_ts_iso = _pair_work_seconds(u_events, now_local)
        idle_secs = min(max(horizon_seconds - work_secs, 0), work_secs)
        total_work_secs += work_secs
        total_idle_secs += idle_secs

        arrivals = [e for e in u_events if e.kind == "ARRIVAL"]
        departures = [e for e in u_events if e.kind == "DEPARTURE"]
        check_in = arrivals[0] if arrivals else None
        check_out = departures[-1] if departures else None
        if check_in:
            present += 1
        late_minutes = 0
        if check_in and timezone.localtime(check_in.ts) > late_cutoff:
            late_minutes = int((timezone.localtime(check_in.ts) - late_cutoff).total_seconds() // 60)
            late += 1
        if on_shift:
            active += 1
        if on_shift:
            no_checkout += 1
        if check_out and not on_shift:
            completed += 1

        pct_of_expected = (
            0 if expected_shift_seconds <= 0 else min(int(round((work_secs / expected_shift_seconds) * 100)), 100)
        )

        if pct_of_expected >= 80:
            color = "success"
        elif pct_of_expected >= 50:
            color = "primary"
        elif pct_of_expected >= 25:
            color = "warning"
        else:
            color = "danger"

        ev = last_event.get(u.id)
        loc_name = getattr(getattr(ev, "location", None), "name", None) if ev else None
        geo_label, geo_tone = _geo_label(ev)
        distance_m = getattr(ev, "distance_m", None) if ev else None
        distance_label = f"{distance_m}m" if distance_m is not None else "-"
        if on_shift:
            status_label = "Active"
            status_tone = "ok"
        elif check_out:
            status_label = "Checked Out"
            status_tone = "info"
        elif check_in:
            status_label = "No Checkout"
            status_tone = "warn"
        else:
            status_label = "Absent"
            status_tone = "muted"

        agents.append(
            {
                "user_id": u.id,
                "name": (u.get_full_name() or u.username or u.email or f"User {u.id}"),
                "email": u.email,
                "location": getattr(m.location, "name", None),
                # battery + status
                "work_secs": work_secs,
                "idle_secs": idle_secs,
                "on_shift": on_shift,
                "last_ts": last_ts_iso,
                "pct": pct_of_expected,
                "color": color,
                # latest event details
                "latest_kind": getattr(ev, "kind", None),
                "latest_ts": timezone.localtime(ev.ts).isoformat() if ev else None,
                "latest_location": loc_name,
                "latest_lat": getattr(ev, "lat", None) if ev else None,
                "latest_lon": getattr(ev, "lon", None) if ev else None,
                "latest_accuracy_m": getattr(ev, "accuracy_m", None) if ev else None,
                "latest_distance_m": getattr(ev, "distance_m", None) if ev else None,
                "latest_geofence": getattr(ev, "geofence_status", None) or getattr(ev, "geo_status", None)
                if ev
                else None,
                "latest_note": getattr(ev, "note", None) if ev else None,
            }
        )
        attendance_rows.append(
            {
                "user_id": u.id,
                "staff": (u.get_full_name() or u.username or u.email or f"User {u.id}"),
                "email": u.email,
                "check_in": timezone.localtime(check_in.ts).isoformat() if check_in else None,
                "check_out": timezone.localtime(check_out.ts).isoformat() if check_out else None,
                "worked_seconds": work_secs,
                "worked_label": _format_seconds(work_secs),
                "idle_seconds": idle_secs,
                "idle_label": _format_seconds(idle_secs),
                "late_minutes": late_minutes,
                "late_label": f"{late_minutes}m" if late_minutes else "On Time",
                "late_tone": "warn" if late_minutes else "ok",
                "status": status_label,
                "status_tone": status_tone,
                "gps_zone": geo_label,
                "gps_tone": geo_tone,
                "distance_m": distance_m,
                "distance_label": distance_label,
                "notes": getattr(ev, "note", None) if ev else "",
            }
        )

    agents.sort(key=lambda a: (not a["on_shift"], a["pct"], a["name"]))
    attendance_rows.sort(key=lambda a: (a["status"] == "Absent", a["staff"]))
    raw_qs = TimeLog.objects.filter(business_id=biz_id, ts__gte=start, ts__lt=end)
    if visible_user_id:
        raw_qs = raw_qs.filter(user_id=visible_user_id)
    raw_logs = [
        _serialize_log(row)
        for row in raw_qs.select_related("user", "location").order_by("-ts")[:200]
    ]

    return {
        "now": now_local.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "expected_shift_seconds": expected_shift_seconds,
        "agents": agents,
        "attendance_rows": attendance_rows,
        "raw_logs": raw_logs,
        "attendance_location": {
            "name": getattr(attendance_location, "name", None),
            "radius_m": getattr(attendance_location, "geofence_radius_m", None),
            "latitude": str(attendance_location.latitude)
            if attendance_location and attendance_location.latitude is not None
            else None,
            "longitude": str(attendance_location.longitude)
            if attendance_location and attendance_location.longitude is not None
            else None,
        },
        "kpis": {
            "present_today": present,
            "late_today": late,
            "active_shifts": active,
            "completed_shifts": completed,
            "no_checkout": no_checkout,
            "total_hours_worked": _format_seconds(total_work_secs),
            "total_idle_time": _format_seconds(total_idle_secs),
            "total_work_seconds": total_work_secs,
            "total_idle_seconds": total_idle_secs,
        },
    }


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def time_logs_page(request: HttpRequest) -> HttpResponse:
    """
    Managers see ALL agent rows + batteries. Page renders even when empty.
    Note: @require_business is applied in urls.py, so no need to call it here.
    """
    bid = _active_biz_id(request)
    if not bid:
        # Fallback: render empty page if no business context
        return render(
            request, "inventory/time_logs.html", {"active_tab": "time_logs", "logs": [], "agents": [], "batteries": []}
        )

    start, end = _range_bounds(request)
    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    can_manage = _can_manage_time_logs(request.user, bid)
    visible_user_id = None if can_manage else request.user.id

    try:
        data = _collect_manager_overview(bid, start, end, expected, visible_user_id=visible_user_id)
    except Exception:
        # If TimeLog table doesn't exist or any other error, render empty page
        data = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "expected_shift_seconds": expected,
            "agents": [],
            "attendance_rows": [],
            "raw_logs": [],
            "attendance_location": {"name": None, "radius_m": None, "latitude": None, "longitude": None},
            "kpis": {
                "present_today": 0,
                "late_today": 0,
                "active_shifts": 0,
                "completed_shifts": 0,
                "no_checkout": 0,
                "total_hours_worked": "0m",
                "total_idle_time": "0m",
            },
        }

    data["active_tab"] = "time_logs"  # ✅ For sidebar nav highlighting
    data["can_manage_time_logs"] = can_manage
    data["attendance_status"] = _attendance_status_context(request.user, bid, start, end)
    return render(request, "inventory/time_logs.html", data)


# ---------------------------------------------------------------------
# JSON APIs
# ---------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def time_logs_api(request: HttpRequest) -> JsonResponse:
    """
    Optional drill-down: ?user_id=123 returns last 30 logs for that user in the window.
    Otherwise returns the same overview payload as the page (agents + batteries).
    Note: @require_business is applied in urls.py, so no need to call it here.
    """
    bid = _active_biz_id(request)
    if not bid:
        return JsonResponse({"ok": False, "error": "no_active_business"}, status=400)

    start, end = _range_bounds(request)

    user_id = request.GET.get("user_id")
    if user_id:
        can_manage = _can_manage_time_logs(request.user, bid)
        if not can_manage and str(user_id) != str(request.user.id):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
        qs = (
            TimeLog.objects.filter(business_id=bid, user_id=user_id, ts__gte=start, ts__lt=end)
            .select_related("user", "location")
            .order_by("-ts")[:30]
        )
        return JsonResponse({"ok": True, "count": qs.count(), "logs": [_serialize_log(r) for r in qs]})

    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    can_manage = _can_manage_time_logs(request.user, bid)
    visible_user_id = None if can_manage else request.user.id
    data = _collect_manager_overview(bid, start, end, expected, visible_user_id=visible_user_id)
    data["can_manage_time_logs"] = can_manage
    data["attendance_status"] = _attendance_status_context(request.user, bid, start, end)
    return JsonResponse({"ok": True, **data})


@login_required
@require_http_methods(["GET"])
def manager_time_overview_page(request: HttpRequest) -> HttpResponse:
    biz_id = _active_biz_id(request)
    if not biz_id:
        return render(request, "inventory/time_overview.html", {"agents": []})
    start, end = _range_bounds(request)
    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    data = _collect_manager_overview(biz_id, start, end, expected)
    return render(request, "inventory/time_overview.html", data)


@login_required
@require_http_methods(["GET"])
def manager_time_overview_api(request: HttpRequest) -> JsonResponse:
    biz_id = _active_biz_id(request)
    if not biz_id:
        return JsonResponse({"ok": False, "error": "no-business"}, status=403)
    start, end = _range_bounds(request)
    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    return JsonResponse({"ok": True, **_collect_manager_overview(biz_id, start, end, expected)})


# ---------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def time_logs_export_csv(request: HttpRequest) -> HttpResponse:
    """
    Export logs in the selected window as CSV. GET only.
    Query: day=YYYY-MM-DD  or from=...&to=...
    """
    bid = _active_biz_id(request)
    if not bid:
        return HttpResponse("No active business", status=400)
    start, end = _range_bounds(request)

    rows = (
        TimeLog.objects.filter(business_id=bid, ts__gte=start, ts__lt=end)
        .select_related("user", "location")
        .order_by("-ts")
    )
    if not _can_manage_time_logs(request.user, bid):
        rows = rows.filter(user=request.user)

    def _iter():
        yield "user,email,ts,kind,location,lat,lon,accuracy_m,distance_m,geofence,note\r\n"
        for r in rows:
            u = r.user
            loc = r.location.name if r.location_id else ""
            out = [
                (u.get_full_name() or u.username or u.email or "").replace(",", " "),
                (u.email or ""),
                timezone.localtime(r.ts).strftime("%Y-%m-%d %H:%M:%S"),
                (r.kind or ""),
                loc.replace(",", " "),
                str(r.lat or ""),
                str(r.lon or ""),
                str(r.accuracy_m or ""),
                str(r.distance_m or ""),
                (getattr(r, "geofence_status", "") or getattr(r, "geo_status", "") or ""),
                (r.note or "").replace("\r", " ").replace("\n", " ").replace(",", ";"),
            ]
            yield ",".join(out) + "\r\n"

    resp = StreamingHttpResponse(_iter(), content_type="text/csv")
    filename = f"time_logs_{start.date()}_{(end - timedelta(days=1)).date()}.csv"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@require_http_methods(["POST"])
def time_log_correct(request: HttpRequest, log_id: int) -> HttpResponse:
    biz_id = _active_biz_id(request)
    if not biz_id or not _can_manage_time_logs(request.user, biz_id):
        return HttpResponse("Not allowed", status=403)
    try:
        log = TimeLog.objects.get(pk=log_id, business_id=biz_id)
    except TimeLog.DoesNotExist:
        return HttpResponse("Time log not found", status=404)

    reason = str(request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "Correction reason is required.")
        return redirect("inventory:time_logs")

    date_raw = request.POST.get("date") or timezone.localtime(log.ts).date().isoformat()
    time_raw = request.POST.get("time") or timezone.localtime(log.ts).strftime("%H:%M")
    kind = str(request.POST.get("kind") or log.kind).upper()
    if kind not in {"ARRIVAL", "DEPARTURE"}:
        messages.error(request, "Choose a valid correction type.")
        return redirect("inventory:time_logs")
    try:
        corrected_naive = datetime.strptime(f"{date_raw} {time_raw}", "%Y-%m-%d %H:%M")
        corrected_ts = timezone.make_aware(corrected_naive, timezone.get_current_timezone())
    except ValueError:
        messages.error(request, "Enter a valid correction date and time.")
        return redirect("inventory:time_logs")

    note = log.note or ""
    stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    correction_note = f"Corrected by {request.user.get_username()} at {stamp}: {reason}"
    log.ts = corrected_ts
    log.kind = kind
    log.note = f"{note}\n{correction_note}".strip()
    log.save(update_fields=["ts", "kind", "note"])
    messages.success(request, "Time log corrected.")
    return redirect("inventory:time_logs")


# ---------------------------------------------------------------------
# Export underscore aliases expected by urls.py (no calls here!)
# ---------------------------------------------------------------------

# Pages
_time_checkin_page = time_checkin
_time_logs_page = time_logs_page
_mgr_time_overview_page = manager_time_overview_page

# APIs
_time_logs_api = time_logs_api
_mgr_time_overview_api = manager_time_overview_api
_time_logs_export_csv = time_logs_export_csv
_time_log_correct = time_log_correct

# Optional: a friendlier alias for personal logs page
my_time_logs_page = my_time_logs
