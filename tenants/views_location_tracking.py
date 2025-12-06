# tenants/views_location_tracking.py
"""
Endpoint for enabling location tracking for agents.
"""
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .utils import get_active_business
from .scope import get_membership


@csrf_exempt
@require_POST
@login_required
def enable_location_tracking(request):
    """
    POST /accounts/enable-location-tracking/
    
    Called when agent grants location permission during signup or settings.
    
    Request body (JSON):
    {
        "latitude": 12.345678,
        "longitude": 34.567890
    }
    
    Response:
    {
        "ok": true,
        "message": "Location tracking enabled"
    }
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    # Get agent's membership
    membership = get_membership(user, business)
    if not membership:
        return JsonResponse({"ok": False, "error": "No membership found"}, status=400)
    
    # Parse coordinates (optional for first enable)
    latitude = None
    longitude = None
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        if "latitude" in data or "lat" in data:
            latitude = Decimal(str(data.get("latitude") or data.get("lat")))
        if "longitude" in data or "lng" in data or "lon" in data:
            longitude = Decimal(str(data.get("longitude") or data.get("lng") or data.get("lon")))
    except (ValueError, TypeError, json.JSONDecodeError):
        # Coordinates are optional for initial enable
        pass
    
    # Enable location tracking
    membership.location_tracking_enabled = True
    
    if latitude and longitude:
        membership.last_known_latitude = latitude
        membership.last_known_longitude = longitude
        membership.last_location_update = timezone.now()
        membership.save(update_fields=[
            "location_tracking_enabled",
            "last_known_latitude",
            "last_known_longitude",
            "last_location_update"
        ])
    else:
        membership.save(update_fields=["location_tracking_enabled"])
    
    return JsonResponse({
        "ok": True,
        "message": "Location tracking enabled successfully",
        "tracking_enabled": True,
    })


@csrf_exempt
@require_POST
@login_required
def disable_location_tracking(request):
    """
    POST /accounts/disable-location-tracking/
    
    Disable location tracking for the agent.
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    membership = get_membership(user, business)
    if not membership:
        return JsonResponse({"ok": False, "error": "No membership found"}, status=400)
    
    membership.location_tracking_enabled = False
    membership.save(update_fields=["location_tracking_enabled"])
    
    return JsonResponse({
        "ok": True,
        "message": "Location tracking disabled",
        "tracking_enabled": False,
    })


@login_required
def location_tracking_status(request):
    """
    GET /accounts/location-tracking-status/
    
    Get the current location tracking status for the agent.
    """
    user = request.user
    business = get_active_business(request)
    
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)
    
    membership = get_membership(user, business)
    if not membership:
        return JsonResponse({"ok": False, "error": "No membership found"}, status=400)
    
    return JsonResponse({
        "ok": True,
        "tracking_enabled": membership.location_tracking_enabled,
        "last_update": membership.last_location_update.isoformat() if membership.last_location_update else None,
        "last_latitude": str(membership.last_known_latitude) if membership.last_known_latitude else None,
        "last_longitude": str(membership.last_known_longitude) if membership.last_known_longitude else None,
    })

