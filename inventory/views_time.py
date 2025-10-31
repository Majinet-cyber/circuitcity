# inventory/views_time.py
from __future__ import annotations

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
    _, biz_id = get_active_business(request)
    return biz_id

def _wants_json(request: HttpRequest) -> bool:
    h = request.headers
    if h.get("X-Requested-With") == "XMLHttpRequest":
        return True
    ct = (h.get("Content-Type") or "")
    accept = (h.get("Accept") or "")
    return "application/json" in ct or "application/json" in accept

def _agent_default_location(request: HttpRequest) -> Optional[Location]:
    biz_id = _active_biz_id(request)
    if not biz_id:
        return None
    mem = (
        Membership.objects
        .filter(user=request.user, business_id=biz_id)
        .select_related("location")
        .first()
    )
    if mem and getattr(mem, "location_id", None):
        return mem.location
    qs = Location.objects.filter(business_id=biz_id).order_by("id")
    return qs.filter(name__icontains="store").first() or qs.first()

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
        end = (to_d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        return start, end

    return _day_bounds()

def _serialize_log(row: TimeLog) -> Dict[str, object]:
    u = getattr(row, "user", None)
    loc = getattr(row, "location", None)
    return {
        "id": getattr(row, "id", None),
        "ts": timezone.localtime(getattr(row, "ts")).isoformat() if getattr(row, "ts", None) else None,
        "kind": getattr(row, "kind", None),
        "user": (getattr(u, "get_full_name", lambda: "")() or getattr(u, "username", None) or getattr(u, "email", None)),
        "user_id": getattr(u, "id", None),
        "location": getattr(loc, "name", None),
        "lat": getattr(row, "lat", None),
        "lon": getattr(row, "lon", None),
        "accuracy_m": getattr(row, "accuracy_m", None),
        "distance_m": getattr(row, "distance_m", None),
        "geofence": getattr(row, "geofence_status", None) or getattr(row, "geo_status", None),
        "note": getattr(row, "note", None),
    }

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
        return JsonResponse({
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
                if net > 0 else
                (f"-MWK {abs(net):,} late deduction applied." if net < 0 else "Recorded.")
            ),
        })

    if net > 0:
        messages.success(request, f"+MWK {net:,} attendance bonus applied.")
    elif net < 0:
        messages.warning(request, f"-MWK {abs(net):,} late deduction applied.")
    messages.info(request, f"{kind.title()} recorded.")
    return redirect("inventory:my_time_logs")

@login_required
def my_time_logs(request: HttpRequest) -> HttpResponse:
    gate = require_business(request)
    if gate:
        return gate

    biz_id = _active_biz_id(request)
    logs = (
        TimeLog.objects
        .filter(business_id=biz_id, user=request.user)
        .select_related("location")
        .order_by("-ts")[:200]
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

def _collect_manager_overview(biz_id: int, start: timezone.datetime, end: timezone.datetime, expected_shift_seconds: int) -> Dict[str, object]:
    """
    Build a per-agent summary for the window [start, end), with a 'battery'.
    Also include the latest event details per user for convenience.
    """
    now_local = timezone.localtime()
    horizon_seconds = int((min(now_local, end) - start).total_seconds())
    horizon_seconds = max(horizon_seconds, 0)

    members = (
        Membership.objects
        .filter(business_id=biz_id)
        .select_related("user", "location")
    )

    events = (
        TimeLog.objects
        .filter(business_id=biz_id, ts__gte=start, ts__lt=end)
        .select_related("user", "location")
        .order_by("user_id", "ts")
    )

    by_user: Dict[int, List[TimeLog]] = defaultdict(list)
    last_event: Dict[int, TimeLog] = {}

    for ev in events:
        by_user[ev.user_id].append(ev)
        last_event[ev.user_id] = ev

    agents: List[Dict[str, object]] = []
    for m in members:
        u = m.user
        u_events = by_user.get(u.id, [])
        work_secs, on_shift, last_ts_iso = _pair_work_seconds(u_events, now_local)
        idle_secs = max(horizon_seconds - work_secs, 0)

        pct_of_expected = 0 if expected_shift_seconds <= 0 else min(
            int(round((work_secs / expected_shift_seconds) * 100)), 100
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

        agents.append({
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
            "latest_geofence": getattr(ev, "geofence_status", None) or getattr(ev, "geo_status", None) if ev else None,
            "latest_note": getattr(ev, "note", None) if ev else None,
        })

    agents.sort(key=lambda a: (not a["on_shift"], a["pct"], a["name"]))

    return {
        "now": now_local.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "expected_shift_seconds": expected_shift_seconds,
        "agents": agents,
    }

# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def time_logs_page(request: HttpRequest) -> HttpResponse:
    """
    Managers see ALL agent rows + batteries. Page renders even when empty.
    """
    gate = require_business(request)
    if gate:
        return gate

    bid = _active_biz_id(request)
    start, end = _range_bounds(request)
    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600

    data = _collect_manager_overview(bid, start, end, expected)
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
    """
    gate = require_business(request)
    if gate:
        return JsonResponse({"ok": False, "error": "no_active_business"}, status=400)

    bid = _active_biz_id(request)
    start, end = _range_bounds(request)

    user_id = request.GET.get("user_id")
    if user_id:
        qs = (
            TimeLog.objects
            .filter(business_id=bid, user_id=user_id, ts__gte=start, ts__lt=end)
            .select_related("user", "location")
            .order_by("-ts")[:30]
        )
        return JsonResponse({"ok": True, "count": qs.count(), "logs": [_serialize_log(r) for r in qs]})

    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    data = _collect_manager_overview(bid, start, end, expected)
    return JsonResponse({"ok": True, **data})

@login_required
@require_http_methods(["GET"])
def manager_time_overview_page(request: HttpRequest) -> HttpResponse:
    gate = require_business(request)
    if gate:
        return gate

    biz_id = _active_biz_id(request)
    start, end = _range_bounds(request)
    shift_h = int(request.GET.get("shift_hours", "8") or 8)
    expected = max(0, shift_h) * 3600
    data = _collect_manager_overview(biz_id, start, end, expected)
    return render(request, "inventory/time_overview.html", data)

@login_required
@require_http_methods(["GET"])
def manager_time_overview_api(request: HttpRequest) -> JsonResponse:
    gate = require_business(request)
    if gate:
        return JsonResponse({"ok": False, "error": "no-business"}, status=403)

    biz_id = _active_biz_id(request)
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
    gate = require_business(request)
    if gate:
        return gate  # let auth redirect happen

    bid = _active_biz_id(request)
    start, end = _range_bounds(request)

    rows = (
        TimeLog.objects
        .filter(business_id=bid, ts__gte=start, ts__lt=end)
        .select_related("user", "location")
        .order_by("-ts")
    )

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
                (r.geofence_status or r.geo_status or ""),
                (r.note or "").replace("\r", " ").replace("\n", " ").replace(",", ";"),
            ]
            yield ",".join(out) + "\r\n"

    resp = StreamingHttpResponse(_iter(), content_type="text/csv")
    filename = f"time_logs_{start.date()}_{(end - timedelta(days=1)).date()}.csv"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

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

# Optional: a friendlier alias for personal logs page
my_time_logs_page = my_time_logs
