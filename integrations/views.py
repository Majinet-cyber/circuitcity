# integrations/views.py
"""
Webhook endpoints:
  POST /api/webhooks/iot/      — IoT sensor data
  POST /api/webhooks/credit/   — Credit signal events
  POST /api/webhooks/generic/  — Generic partner payloads

Authentication: Authorization: Bearer <token>
             or X-Emajinet-Webhook-Token: <token>
Token is compared against settings.EMAJINET_WEBHOOK_SECRET.
If the secret is not configured, dev mode allows requests (with a warning).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import CreditSignal, CreditSignalType, WebhookEvent, WebhookStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _extract_token(request) -> Optional[str]:
    """Extract bearer token from Authorization header or X-Emajinet-Webhook-Token."""
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    custom = request.headers.get("X-Emajinet-Webhook-Token", "").strip()
    if custom:
        return custom
    return None


def _check_token(request) -> Optional[JsonResponse]:
    """
    Validate the webhook secret. Returns a 403 JsonResponse on failure, None on success.

    Dev mode (secret not configured): warn and allow.
    Production (DEBUG=False): fail closed.
    """
    secret = getattr(settings, "EMAJINET_WEBHOOK_SECRET", "") or ""
    if not secret:
        if not getattr(settings, "DEBUG", True):
            logger.error("webhook: EMAJINET_WEBHOOK_SECRET not configured in production — rejecting")
            return JsonResponse({"error": "Webhook authentication not configured"}, status=403)
        logger.warning("webhook: EMAJINET_WEBHOOK_SECRET not set — allowing in dev mode")
        return None

    provided = _extract_token(request)
    if not provided:
        logger.warning("webhook: missing token in request")
        return JsonResponse({"error": "Missing webhook token"}, status=403)

    import hmac
    if not hmac.compare_digest(provided, secret):
        logger.warning("webhook: invalid token provided")
        return JsonResponse({"error": "Invalid webhook token"}, status=403)

    return None


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _parse_body(request) -> tuple[Optional[dict], Optional[JsonResponse]]:
    """Parse JSON body. Returns (data, None) on success or (None, error_response)."""
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return None, JsonResponse({"error": "Payload must be a JSON object"}, status=400)
        return data, None
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("webhook: invalid JSON — %s", exc)
        return None, JsonResponse({"error": "Invalid JSON payload"}, status=400)


def _parse_ts(ts_str: str):
    """Parse an ISO datetime string; fall back to timezone.now()."""
    if ts_str:
        try:
            parsed = parse_datetime(ts_str)
            if parsed:
                if parsed.tzinfo is None:
                    from django.utils.timezone import make_aware
                    parsed = make_aware(parsed)
                return parsed
        except Exception:
            pass
    return timezone.now()


# ---------------------------------------------------------------------------
# IoT Webhook
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def iot_webhook(request):
    """
    POST /api/webhooks/iot/

    Accepts ESP32-style payloads with a `readings` list.
    Stores WebhookEvent + (optionally) IoTDevice + IoTReading records.

    Sample payload::

        {
          "device_id": "ESP32-FARM-001",
          "device_type": "esp32",
          "source": "farm_sensor_gateway",
          "recorded_at": "2026-04-28T10:30:00Z",
          "readings": [
            {"type": "temperature", "value": 28.5, "unit": "C"},
            {"type": "humidity", "value": 62, "unit": "%"}
          ],
          "metadata": {"farm": "Demo Farm", "location": "Lilongwe"}
        }
    """
    auth_err = _check_token(request)
    if auth_err:
        return auth_err

    data, err = _parse_body(request)
    if err:
        return err

    device_id = (data.get("device_id") or "").strip()
    if not device_id:
        return JsonResponse({"error": "'device_id' is required"}, status=400)

    source = data.get("source") or f"iot:{device_id}"
    recorded_at = _parse_ts(data.get("recorded_at", ""))

    # Store webhook event immediately
    event = WebhookEvent.objects.create(
        source=source,
        event_type="iot.reading",
        payload=data,
        received_at=timezone.now(),
    )

    readings_saved = 0
    try:
        readings = data.get("readings") or []
        if isinstance(readings, dict):
            readings = [{"type": k, "value": v, "unit": ""} for k, v in readings.items()]

        if readings:
            readings_saved = _save_iot_readings(device_id, data, readings, recorded_at)

        event.mark_processed()
        logger.info("iot_webhook: device=%s readings=%d event_id=%d", device_id, readings_saved, event.pk)
    except Exception as exc:
        event.mark_failed(str(exc))
        logger.exception("iot_webhook: processing error for device=%s", device_id)

    return JsonResponse(
        {
            "status": "accepted",
            "device_id": device_id,
            "readings_saved": readings_saved,
            "event_id": event.pk,
            "timestamp": recorded_at.isoformat(),
        },
        status=201,
    )


def _save_iot_readings(device_id: str, payload: dict, readings: list, recorded_at) -> int:
    """
    Try to create/update IoTDevice and IoTReading using the existing inventory models.
    Fails gracefully if models are unavailable.
    """
    try:
        from inventory.models_iot import IoTDevice, IoTDeviceStatus, IoTReading
    except ImportError:
        logger.warning("iot_webhook: inventory.models_iot not available — skipping IoT record creation")
        return 0

    device_type_raw = (payload.get("device_type") or "custom").lower()
    device, _ = IoTDevice.objects.get_or_create(
        device_id=device_id,
        defaults={
            "name": device_id,
            "device_type": _map_device_type(device_type_raw),
            "is_active": True,
        },
    )
    device.status = IoTDeviceStatus.ONLINE
    device.last_seen = timezone.now()
    metadata = payload.get("metadata") or {}
    if metadata:
        device.metadata = {**device.metadata, **metadata}
    device.save(update_fields=["status", "last_seen", "metadata"])

    saved = 0
    for item in readings:
        if not isinstance(item, dict):
            continue
        reading_type = str(item.get("type") or item.get("reading_type") or "").strip()
        raw_value = item.get("value")
        if not reading_type or raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        unit = str(item.get("unit") or "")
        IoTReading.objects.create(
            device=device,
            reading_type=reading_type,
            value=value,
            unit=unit,
            timestamp=recorded_at,
            raw_payload=item,
        )
        saved += 1

    return saved


_DEVICE_TYPE_MAP = {
    "esp32": "custom",
    "arduino": "custom",
    "smart_meter": "energy",
    "inverter": "energy",
    "battery": "energy",
    "pump": "water",
    "fridge": "custom",
    "sensor_gateway": "custom",
    "weather": "weather",
    "motion": "motion",
    "gps": "gps",
    "energy": "energy",
}


def _map_device_type(raw: str) -> str:
    return _DEVICE_TYPE_MAP.get(raw, "custom")


# ---------------------------------------------------------------------------
# Credit Webhook
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def credit_webhook(request):
    """
    POST /api/webhooks/credit/

    Accepts credit-intelligence signal payloads.

    Sample payload::

        {
          "source": "mobile_money_partner",
          "customer_ref": "CUST-001",
          "occurred_at": "2026-04-28T10:30:00Z",
          "signals": [
            {"type": "repayment", "amount": 25000, "currency": "MWK", "days_late": 0}
          ],
          "metadata": {"channel": "mobile_money", "transaction_id": "TXN123"}
        }
    """
    auth_err = _check_token(request)
    if auth_err:
        return auth_err

    data, err = _parse_body(request)
    if err:
        return err

    source = (data.get("source") or "").strip()
    if not source:
        return JsonResponse({"error": "'source' is required"}, status=400)

    signals_data = data.get("signals") or []
    if not isinstance(signals_data, list):
        return JsonResponse({"error": "'signals' must be a list"}, status=400)

    occurred_at = _parse_ts(data.get("occurred_at", ""))
    customer_ref = str(data.get("customer_ref") or "")

    event = WebhookEvent.objects.create(
        source=source,
        event_type="credit.signal",
        payload=data,
        received_at=timezone.now(),
    )

    signals_created = 0
    try:
        for sig in signals_data:
            if not isinstance(sig, dict):
                continue
            sig_type_raw = str(sig.get("type") or "other").lower()
            sig_type = _map_signal_type(sig_type_raw)
            CreditSignal.objects.create(
                customer_ref=customer_ref,
                source=source,
                signal_type=sig_type,
                payload=sig,
                occurred_at=occurred_at,
            )
            signals_created += 1

        event.mark_processed()
        logger.info("credit_webhook: source=%s customer=%s signals=%d", source, customer_ref, signals_created)
    except Exception as exc:
        event.mark_failed(str(exc))
        logger.exception("credit_webhook: processing error source=%s", source)

    return JsonResponse(
        {
            "status": "accepted",
            "source": source,
            "customer_ref": customer_ref,
            "signals_created": signals_created,
            "event_id": event.pk,
        },
        status=201,
    )


def _map_signal_type(raw: str) -> str:
    valid = {c.value for c in CreditSignalType}
    return raw if raw in valid else CreditSignalType.OTHER


# ---------------------------------------------------------------------------
# Generic Webhook
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def generic_webhook(request):
    """
    POST /api/webhooks/generic/

    Accepts any partner payload. Stores it as a WebhookEvent.

    Sample payload::

        {
          "source": "partner_app",
          "event_type": "stock.updated",
          "payload": {"sku": "SUGAR-1KG", "quantity": 20}
        }
    """
    auth_err = _check_token(request)
    if auth_err:
        return auth_err

    data, err = _parse_body(request)
    if err:
        return err

    source = (data.get("source") or "unknown").strip()
    event_type = (data.get("event_type") or "generic").strip()

    event = WebhookEvent.objects.create(
        source=source,
        event_type=event_type,
        payload=data,
        received_at=timezone.now(),
    )
    event.mark_processed()

    logger.info("generic_webhook: source=%s event_type=%s event_id=%d", source, event_type, event.pk)

    return JsonResponse(
        {
            "status": "accepted",
            "source": source,
            "event_type": event_type,
            "event_id": event.pk,
        },
        status=201,
    )
