# inventory/verticals/iot.py
"""
IoT monitoring views: webhook receiver + admin dashboard.
"""
from __future__ import annotations

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from inventory.models_iot import IoTDevice, IoTDeviceStatus, IoTReading

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UNIT MAP for common reading types
# ---------------------------------------------------------------------------
_UNIT_MAP = {
    "voltage": "V",
    "current": "A",
    "power": "W",
    "energy_kwh": "kWh",
    "battery_soc": "%",
    "temperature": "°C",
    "humidity": "%",
    "water_level": "%",
    "motion": "bool",
}


# ---------------------------------------------------------------------------
# WEBHOOK ENDPOINT
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def webhook(request):
    """
    POST /iot/webhook/

    Accepts ESP32-style JSON payloads. Authenticates via Authorization header.

    Example request::

        Authorization: Bearer <api_key>
        Content-Type: application/json

        {
          "device_id": "esp32-energy-001",
          "type": "energy",
          "readings": {
            "voltage": 12.6,
            "current": 4.2,
            "power": 52.9,
            "battery_soc": 78,
            "temperature": 31.5
          },
          "timestamp": "2026-04-28T07:00:00Z"
        }
    """
    # ---- Authenticate ----
    auth_header = request.headers.get("Authorization", "").strip()
    api_key = None
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:].strip()
    elif auth_header.startswith("Token "):
        api_key = auth_header[6:].strip()
    elif auth_header:
        api_key = auth_header

    if not api_key:
        return JsonResponse({"error": "Missing Authorization header"}, status=401)

    try:
        device = IoTDevice.objects.get(api_key=api_key, is_active=True)
    except IoTDevice.DoesNotExist:
        return JsonResponse({"error": "Invalid API key"}, status=403)

    # ---- Parse payload ----
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    readings_data = payload.get("readings")
    if not readings_data or not isinstance(readings_data, dict):
        return JsonResponse({"error": "Missing or invalid 'readings' field"}, status=400)

    # ---- Parse optional timestamp ----
    ts = timezone.now()
    ts_str = payload.get("timestamp", "")
    if ts_str:
        try:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(ts_str)
            if parsed:
                ts = parsed
        except Exception:
            pass  # Fall back to now()

    # ---- Save readings ----
    saved_count = 0
    for reading_type, value in readings_data.items():
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        unit = _UNIT_MAP.get(reading_type, "")
        IoTReading.objects.create(
            device=device,
            reading_type=reading_type,
            value=value,
            unit=unit,
            timestamp=ts,
            raw_payload=payload,
        )
        saved_count += 1

    # ---- Update device last_seen ----
    device.status = IoTDeviceStatus.ONLINE
    device.last_seen = timezone.now()
    device.save(update_fields=["status", "last_seen"])

    logger.info(
        "IoT webhook: device=%s readings=%d", device.device_id, saved_count
    )

    return JsonResponse(
        {
            "status": "ok",
            "device_id": device.device_id,
            "readings_saved": saved_count,
            "timestamp": ts.isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# DASHBOARD (staff / admin)
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    """Simple IoT monitoring dashboard."""
    devices = IoTDevice.objects.prefetch_related("readings").order_by("-last_seen")

    device_data = []
    for dev in devices:
        latest_readings = dev.readings.order_by("-timestamp")[:5]
        minutes_ago = None
        if dev.last_seen:
            delta = timezone.now() - dev.last_seen
            minutes_ago = int(delta.total_seconds() / 60)

        device_data.append(
            {
                "device": dev,
                "latest_readings": latest_readings,
                "minutes_ago": minutes_ago,
            }
        )

    context = {
        "device_data": device_data,
        "total_devices": devices.count(),
        "online_count": devices.filter(status=IoTDeviceStatus.ONLINE).count(),
        "active_tab": "iot",
        "webhook_url": request.build_absolute_uri("/iot/webhook/"),
    }
    return render(request, "verticals/iot/dashboard.html", context)
