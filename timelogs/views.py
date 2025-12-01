# timelogs/views.py
"""
Agent presence tracking endpoints.
These endpoints are called by the front-end periodically when an agent
allows location access.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import csv

from tenants.utils import get_active_business
from tenants.scope import get_membership, resolve_location_for_user

from .models import AgentWorkLog, LocationPing, WorkingHours, TimeLog, TimeLogSegment
from .utils import haversine_m


def _get_location_model():
    """Lazy import to avoid circular dependencies."""
    try:
        from inventory.models import Location
        return Location
    except ImportError:
        return None


def _is_inside_geofence(location, lat: float, lng: float) -> bool:
    """
    Check if the given coordinates are within the location's geofence radius.
    """
    if not location:
        return False
    loc_lat = getattr(location, "latitude", None) or getattr(location, "lat", None)
    loc_lng = getattr(location, "longitude", None) or getattr(location, "lng", None)
    radius = getattr(location, "geofence_radius_m", None) or getattr(location, "radius_m", 150)
    
    if loc_lat is None or loc_lng is None:
        return False
    
    distance = haversine_m(float(lat), float(lng), float(loc_lat), float(loc_lng))
    return distance <= radius


def _find_nearest_location(business, lat: float, lng: float):
    """
    Find the nearest location within geofence for this business.
    Returns the location if found within any geofence, else None.
    """
    Location = _get_location_model()
    if not Location:
        return None
    
    for loc in Location.objects.filter(business=business):
        if _is_inside_geofence(loc, lat, lng):
            return loc
    return None


def _get_or_create_work_log(user, business, location=None) -> AgentWorkLog:
    """
    Get or create today's AgentWorkLog for the user.
    """
    today = timezone.localdate()
    work_log, created = AgentWorkLog.objects.get_or_create(
        agent=user,
        business=business,
        work_date=today,
        defaults={
            "location": location,
        }
    )
    if created and location and not work_log.location:
        work_log.location = location
        work_log.save(update_fields=["location"])
    return work_log


@csrf_exempt
@require_POST
@login_required
def ping_location(request):
    """
    POST /api/agent/ping-location/
    
    Called periodically by the front-end when agent allows location access.
    Receives lat/lng, updates AgentWorkLog for today.
    
    Request body (JSON or form data):
    {
        "lat": 12.345678,
        "lng": 34.567890
    }
    
    Response:
    {
        "ok": true,
        "is_inside": true/false,
        "work_log_id": 123,
        "on_site_minutes": 45,
        "idle_minutes": 5
    }
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    # Parse coordinates
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST
        lat = float(data.get("lat") or data.get("latitude"))
        lng = float(data.get("lng") or data.get("longitude"))
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        return JsonResponse({"ok": False, "error": f"Invalid coordinates: {e}"}, status=400)
    
    # Determine the agent's assigned location (from membership or session)
    membership = get_membership(user, business)
    assigned_location = getattr(membership, "location", None) if membership else None
    
    if not assigned_location:
        # Fall back to nearest location or session location
        lid = resolve_location_for_user(request)
        Location = _get_location_model()
        if lid and Location:
            assigned_location = Location.objects.filter(pk=lid).first()
    
    # Check if inside geofence
    is_inside = False
    detected_location = None
    
    if assigned_location:
        is_inside = _is_inside_geofence(assigned_location, lat, lng)
        detected_location = assigned_location
    else:
        # Try to find any location for this business
        detected_location = _find_nearest_location(business, lat, lng)
        is_inside = detected_location is not None
    
    # Get or create today's work log
    work_log = _get_or_create_work_log(user, business, detected_location)
    
    # Record the ping
    now = timezone.now()
    LocationPing.objects.create(
        work_log=work_log,
        timestamp=now,
        latitude=Decimal(str(lat)),
        longitude=Decimal(str(lng)),
        is_inside_geofence=is_inside,
    )
    
    # Update work log timestamps
    if is_inside:
        if not work_log.first_seen_at:
            work_log.first_seen_at = now
        work_log.last_seen_at = now
    
    # Recompute on-site and idle minutes from pings
    _recompute_work_log_totals(work_log)
    
    work_log.save()
    
    return JsonResponse({
        "ok": True,
        "is_inside": is_inside,
        "work_log_id": work_log.id,
        "on_site_minutes": work_log.total_on_site_minutes,
        "idle_minutes": work_log.total_idle_minutes,
        "first_seen": work_log.first_seen_at.isoformat() if work_log.first_seen_at else None,
        "last_seen": work_log.last_seen_at.isoformat() if work_log.last_seen_at else None,
    })


def _recompute_work_log_totals(work_log: AgentWorkLog) -> None:
    """
    Recompute total_on_site_minutes and total_idle_minutes from pings.
    Uses a state machine approach: track transitions between inside/outside.
    """
    pings = list(work_log.pings.order_by("timestamp"))
    if not pings:
        return
    
    on_site_seconds = 0
    idle_seconds = 0
    
    prev_ping = None
    for ping in pings:
        if prev_ping:
            delta_seconds = (ping.timestamp - prev_ping.timestamp).total_seconds()
            # Cap delta at 5 minutes (300s) to avoid counting long gaps
            delta_seconds = min(delta_seconds, 300)
            
            if prev_ping.is_inside_geofence:
                on_site_seconds += delta_seconds
            else:
                # Only count as idle if within working hours
                if _is_within_working_hours(work_log, prev_ping.timestamp):
                    idle_seconds += delta_seconds
        prev_ping = ping
    
    work_log.total_on_site_minutes = int(on_site_seconds / 60)
    work_log.total_idle_minutes = int(idle_seconds / 60)


def _is_within_working_hours(work_log: AgentWorkLog, dt) -> bool:
    """Check if the given datetime is within scheduled working hours."""
    if not work_log.scheduled_start or not work_log.scheduled_end:
        return True  # Assume working hours if not configured
    
    time_only = dt.time() if hasattr(dt, "time") else dt
    return work_log.scheduled_start <= time_only <= work_log.scheduled_end


@login_required
def agent_presence_today(request):
    """
    GET /api/agent/presence-today/
    
    Returns today's presence stats for the current agent.
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    today = timezone.localdate()
    try:
        work_log = AgentWorkLog.objects.get(
            agent=user,
            business=business,
            work_date=today,
        )
    except AgentWorkLog.DoesNotExist:
        return JsonResponse({
            "ok": True,
            "has_logged_in": False,
            "first_seen": None,
            "last_seen": None,
            "on_site_minutes": 0,
            "idle_minutes": 0,
            "scheduled_start": None,
            "scheduled_end": None,
        })
    
    return JsonResponse({
        "ok": True,
        "has_logged_in": work_log.first_seen_at is not None,
        "first_seen": work_log.first_seen_at.isoformat() if work_log.first_seen_at else None,
        "last_seen": work_log.last_seen_at.isoformat() if work_log.last_seen_at else None,
        "on_site_minutes": work_log.total_on_site_minutes,
        "idle_minutes": work_log.total_idle_minutes,
        "scheduled_start": str(work_log.scheduled_start) if work_log.scheduled_start else None,
        "scheduled_end": str(work_log.scheduled_end) if work_log.scheduled_end else None,
        "arrived_early_minutes": work_log.arrived_early_minutes,
        "arrived_late_minutes": work_log.arrived_late_minutes,
        "effective_work_minutes": work_log.effective_work_minutes,
    })


@login_required
def manager_presence_dashboard(request):
    """
    GET /api/manager/presence-dashboard/
    
    Returns today's presence stats for all agents in the business.
    Manager-only endpoint.
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    # Check if user is manager
    membership = get_membership(user, business)
    if not membership or membership.role.upper() != "MANAGER":
        if not user.is_superuser and not user.is_staff:
            return JsonResponse({"ok": False, "error": "Manager access required"}, status=403)
    
    today = timezone.localdate()
    work_logs = AgentWorkLog.objects.filter(
        business=business,
        work_date=today,
    ).select_related("agent", "location").order_by("-first_seen_at")
    
    agents = []
    for wl in work_logs:
        agents.append({
            "agent_id": wl.agent.id,
            "agent_name": wl.agent.get_full_name() or wl.agent.username,
            "location": wl.location.name if wl.location else None,
            "first_seen": wl.first_seen_at.isoformat() if wl.first_seen_at else None,
            "last_seen": wl.last_seen_at.isoformat() if wl.last_seen_at else None,
            "on_site_minutes": wl.total_on_site_minutes,
            "idle_minutes": wl.total_idle_minutes,
            "status": "active" if wl.first_seen_at else "not_seen",
        })
    
    return JsonResponse({
        "ok": True,
        "date": str(today),
        "agents": agents,
        "total_agents": len(agents),
    })


# =========================================================================
# Legacy views for backwards compatibility
# =========================================================================

@login_required
def start_shift(request):
    """Legacy: start a shift (creates TimeLog)."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    
    user = request.user
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    lat = request.POST.get("lat")
    lng = request.POST.get("lng")
    
    tl = TimeLog.objects.create(agent=user, business=business)
    
    in_range = False
    if lat and lng:
        loc = _find_nearest_location(business, float(lat), float(lng))
        in_range = loc is not None
    
    TimeLogSegment.objects.create(timelog=tl, in_range=in_range)
    
    return JsonResponse({"ok": True, "timelog_id": tl.id, "in_range": in_range})


@login_required
def stop_shift(request, timelog_id):
    """Legacy: stop a shift."""
    tl = get_object_or_404(TimeLog, id=timelog_id, agent=request.user, is_active=True)
    seg = tl.segments.order_by("-id").first()
    if seg and not seg.ended_at:
        seg.ended_at = timezone.now()
        seg.save()
    tl.ended_at = timezone.now()
    tl.is_active = False
    tl.save()
    return JsonResponse({"ok": True, "work_min": tl.work_minutes, "out_min": tl.out_minutes})


@login_required
def gps_ping(request, timelog_id):
    """Legacy: GPS ping for TimeLog."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    
    tl = get_object_or_404(TimeLog, id=timelog_id, agent=request.user, is_active=True)
    lat = float(request.POST["lat"])
    lng = float(request.POST["lng"])
    
    in_range = _find_nearest_location(tl.business, lat, lng) is not None
    
    last = tl.segments.order_by("-id").first()
    now = timezone.now()
    
    if last and last.in_range == in_range and not last.ended_at:
        return JsonResponse({"ok": True, "in_range": in_range})
    
    if last and not last.ended_at:
        last.ended_at = now
        last.save()
    
    TimeLogSegment.objects.create(timelog=tl, in_range=in_range, started_at=now)
    return JsonResponse({"ok": True, "in_range": in_range})


# =========================================================================
# Time Logs UI Dashboard
# =========================================================================

@login_required
def time_logs_dashboard(request):
    """
    Rich Time Logs UI showing work vs idle time for the selected day.
    """
    business = get_active_business(request)
    if not business:
        return render(request, "timelogs/no_business.html")
    
    # Get date from query param or default to today
    date_str = request.GET.get("date")
    if date_str:
        try:
            from datetime import datetime
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()
    
    # Get work log for the selected date
    try:
        work_log = AgentWorkLog.objects.get(
            agent=request.user,
            business=business,
            work_date=selected_date,
        )
        pings = work_log.pings.order_by("timestamp")
    except AgentWorkLog.DoesNotExist:
        work_log = None
        pings = []
    
    # Calculate battery segments for visualization
    battery_segments = []
    if work_log:
        total_minutes = work_log.total_on_site_minutes + work_log.total_idle_minutes
        if total_minutes > 0:
            work_percent = (work_log.total_on_site_minutes / total_minutes) * 100
            idle_percent = (work_log.total_idle_minutes / total_minutes) * 100
            battery_segments = [
                {"type": "work", "percent": work_percent, "label": f"{work_log.total_on_site_minutes} min"},
                {"type": "idle", "percent": idle_percent, "label": f"{work_log.total_idle_minutes} min"},
            ]
    
    context = {
        "selected_date": selected_date,
        "today": timezone.localdate(),
        "work_log": work_log,
        "pings": pings,
        "battery_segments": battery_segments,
        "total_pings": pings.count() if work_log else 0,
    }
    
    return render(request, "timelogs/dashboard.html", context)


@login_required
def export_time_logs_csv(request):
    """
    Export time logs as CSV for the selected date range.
    """
    business = get_active_business(request)
    if not business:
        return HttpResponseBadRequest("No active business")
    
    # Get date range from query params
    from_date = request.GET.get("from_date", timezone.localdate())
    to_date = request.GET.get("to_date", timezone.localdate())
    
    if isinstance(from_date, str):
        from datetime import datetime
        from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
    if isinstance(to_date, str):
        from datetime import datetime
        to_date = datetime.strptime(to_date, "%Y-%m-%d").date()
    
    # Query work logs
    work_logs = AgentWorkLog.objects.filter(
        agent=request.user,
        business=business,
        work_date__gte=from_date,
        work_date__lte=to_date,
    ).order_by("work_date")
    
    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="timelogs_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "First Seen",
        "Last Seen",
        "On-Site Minutes",
        "Idle Minutes",
        "Effective Work Minutes",
        "Arrived Early (min)",
        "Arrived Late (min)",
        "Location",
    ])
    
    for wl in work_logs:
        writer.writerow([
            wl.work_date.strftime("%Y-%m-%d"),
            wl.first_seen_at.strftime("%H:%M:%S") if wl.first_seen_at else "-",
            wl.last_seen_at.strftime("%H:%M:%S") if wl.last_seen_at else "-",
            wl.total_on_site_minutes,
            wl.total_idle_minutes,
            wl.effective_work_minutes,
            wl.arrived_early_minutes,
            wl.arrived_late_minutes,
            wl.location.name if wl.location else "-",
        ])
    
    return response
