# timelogs/views_geo.py
"""
Enhanced geo-based attendance endpoint with bonus/penalty logic.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tenants.utils import get_active_business
from tenants.scope import get_membership

from .models import AgentWorkLog, LocationPing, WorkingHours
from .utils_geo import is_within_geofence
from .constants import WORK_START, WORK_END, EARLY_BONUS_PER_30, LATE_PENALTY_PER_30


def _get_location_model():
    """Lazy import to avoid circular dependencies."""
    try:
        from inventory.models import Location
        return Location
    except ImportError:
        return None


@csrf_exempt
@require_POST
@login_required
def ping_location(request):
    """
    POST /timelogs/ping-location/
    
    Enhanced location ping endpoint with bonus/penalty logic.
    
    Request body (JSON):
    {
        "latitude": 12.345678,
        "longitude": 34.567890,
        "timestamp": "2025-12-06T10:30:00Z"  // optional
    }
    
    Response:
    {
        "ok": true,
        "is_inside": true/false,
        "work_log_id": 123,
        "on_site_minutes": 45,
        "idle_minutes": 5,
        "bonus_amount": "5000.00",
        "penalty_amount": "0.00"
    }
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    # Check if location tracking is enabled for this agent
    membership = get_membership(user, business)
    if not membership:
        return JsonResponse({"ok": False, "error": "No membership found"}, status=400)
    
    if not membership.location_tracking_enabled:
        return JsonResponse({"ok": False, "error": "Location tracking not enabled"}, status=403)
    
    # Parse request body
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        latitude = Decimal(str(data.get("latitude") or data.get("lat")))
        longitude = Decimal(str(data.get("longitude") or data.get("lng") or data.get("lon")))
        
        # Optional timestamp (defaults to now)
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            ping_timestamp = timezone.make_aware(datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")))
        else:
            ping_timestamp = timezone.now()
    except (ValueError, TypeError, json.JSONDecodeError, KeyError) as e:
        return JsonResponse({"ok": False, "error": f"Invalid request data: {e}"}, status=400)
    
    # Get agent's assigned location
    assigned_location = membership.location
    if not assigned_location:
        return JsonResponse({"ok": False, "error": "No location assigned to agent"}, status=400)
    
    # Check if location has GPS coordinates
    if not assigned_location.latitude or not assigned_location.longitude:
        return JsonResponse({"ok": False, "error": "Location has no GPS coordinates configured"}, status=400)
    
    # Check if within geofence
    is_inside, distance = is_within_geofence(
        latitude,
        longitude,
        assigned_location.latitude,
        assigned_location.longitude,
        assigned_location.geofence_radius_m
    )
    
    # Get or create today's work log
    today = timezone.localdate()
    work_log, created = AgentWorkLog.objects.get_or_create(
        agent=user,
        business=business,
        work_date=today,
        defaults={
            "location": assigned_location,
        }
    )
    
    # Record the ping
    LocationPing.objects.create(
        work_log=work_log,
        timestamp=ping_timestamp,
        latitude=latitude,
        longitude=longitude,
        is_inside_geofence=is_inside,
    )
    
    # Update work log timestamps
    if is_inside:
        if not work_log.first_seen_at:
            work_log.first_seen_at = ping_timestamp
        work_log.last_seen_at = ping_timestamp
    
    # Recompute on-site and idle minutes from all pings
    _recompute_work_log_totals(work_log)
    
    # Apply bonus/penalty logic based on work hours
    _apply_bonus_penalty_logic(work_log, ping_timestamp)
    
    work_log.save()
    
    # Update membership last known location
    membership.last_known_latitude = latitude
    membership.last_known_longitude = longitude
    membership.last_location_update = ping_timestamp
    membership.save(update_fields=[
        "last_known_latitude",
        "last_known_longitude",
        "last_location_update"
    ])
    
    return JsonResponse({
        "ok": True,
        "is_inside": is_inside,
        "distance_m": round(distance, 2),
        "work_log_id": work_log.id,
        "on_site_minutes": work_log.total_on_site_minutes,
        "idle_minutes": work_log.total_idle_minutes,
        "first_seen": work_log.first_seen_at.isoformat() if work_log.first_seen_at else None,
        "last_seen": work_log.last_seen_at.isoformat() if work_log.last_seen_at else None,
        "bonus_amount": str(work_log.bonus_amount),
        "penalty_amount": str(work_log.penalty_amount),
        "arrived_early_minutes": work_log.arrived_early_minutes,
        "arrived_late_minutes": work_log.arrived_late_minutes,
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
            # Cap delta at 15 minutes (900s) to avoid counting long gaps
            delta_seconds = min(delta_seconds, 900)
            
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
        # Use default work hours from constants
        work_log.scheduled_start = WORK_START
        work_log.scheduled_end = WORK_END
    
    time_only = dt.time() if hasattr(dt, "time") else dt
    return work_log.scheduled_start <= time_only <= work_log.scheduled_end


def _apply_bonus_penalty_logic(work_log: AgentWorkLog, current_time) -> None:
    """
    Apply bonus/penalty logic based on work hours and arrival time.
    
    Rules:
    - Early arrival (before 08:00 while at store): +5,000 per 30 minutes
    - Late arrival (after 08:00 until first seen): -7,000 per 30 minutes
    - After 17:30: no changes
    """
    # Ensure scheduled hours are set
    if not work_log.scheduled_start or not work_log.scheduled_end:
        work_log.scheduled_start = WORK_START
        work_log.scheduled_end = WORK_END
    
    # Get business commission config for bonus/penalty amounts
    try:
        from sales.models import CommissionConfig
        config = CommissionConfig.get_active(work_log.business)
        if config:
            early_bonus_per_30 = config.early_bonus_per_30min
            late_penalty_per_30 = config.late_penalty_per_30min
            early_enabled = config.early_bonus_enabled
            late_enabled = config.lateness_penalties_enabled
        else:
            early_bonus_per_30 = EARLY_BONUS_PER_30
            late_penalty_per_30 = LATE_PENALTY_PER_30
            early_enabled = True
            late_enabled = True
    except Exception:
        early_bonus_per_30 = EARLY_BONUS_PER_30
        late_penalty_per_30 = LATE_PENALTY_PER_30
        early_enabled = True
        late_enabled = True
    
    # Don't process if after work hours
    current_time_only = current_time.time() if hasattr(current_time, "time") else current_time
    if current_time_only > work_log.scheduled_end:
        return
    
    # Calculate bonuses for early arrival
    if work_log.first_seen_at and early_enabled:
        # Compute how early the agent arrived
        scheduled_start_dt = timezone.make_aware(
            datetime.combine(work_log.work_date, work_log.scheduled_start)
        )
        
        if work_log.first_seen_at < scheduled_start_dt:
            # Agent arrived early
            early_minutes = int((scheduled_start_dt - work_log.first_seen_at).total_seconds() / 60)
            work_log.arrived_early_minutes = early_minutes
            work_log.arrived_late_minutes = 0
            
            # Calculate bonus (per 30-minute slot)
            early_slots = early_minutes // 30
            work_log.bonus_amount = early_bonus_per_30 * early_slots
        else:
            # Agent arrived late
            late_minutes = int((work_log.first_seen_at - scheduled_start_dt).total_seconds() / 60)
            work_log.arrived_late_minutes = late_minutes
            work_log.arrived_early_minutes = 0
            
            # Calculate penalty (per 30-minute slot) if enabled
            if late_enabled:
                late_slots = late_minutes // 30
                work_log.penalty_amount = late_penalty_per_30 * late_slots
            else:
                work_log.penalty_amount = Decimal("0.00")
    else:
        # If no first_seen yet and we're past work start time, calculate potential penalty
        if not work_log.first_seen_at:
            scheduled_start_dt = timezone.make_aware(
                datetime.combine(work_log.work_date, work_log.scheduled_start)
            )
            
            if current_time > scheduled_start_dt and late_enabled:
                # Agent hasn't arrived yet and it's past start time
                late_minutes = int((current_time - scheduled_start_dt).total_seconds() / 60)
                work_log.arrived_late_minutes = late_minutes
                
                late_slots = late_minutes // 30
                work_log.penalty_amount = late_penalty_per_30 * late_slots

