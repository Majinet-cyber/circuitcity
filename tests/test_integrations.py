# tests/test_integrations.py
"""
Integration tests for the Developers & Integrations feature.

Covers:
- Landing page Developers section
- IoT webhook endpoint
- Credit webhook endpoint
- Generic webhook endpoint
- Token authentication
- Malformed payload handling
- No regression to existing landing page content
"""
from __future__ import annotations

import json

import pytest
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Landing page — Developers section
# ---------------------------------------------------------------------------

def test_landing_page_renders(client):
    """Landing page returns 200."""
    url = reverse("staticpages:home")
    response = client.get(url)
    assert response.status_code == 200


def test_landing_page_contains_developers_heading(client):
    """Landing page must mention Developers and infrastructure/integrations concepts."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert "Developers" in content, "Landing page must contain 'Developers'"
    # 'integrations' concept is present in the credibility strip and Trusted Infrastructure section
    assert "integrations" in content.lower() or "Infrastructure" in content, (
        "Landing page must reference integrations or infrastructure"
    )


def test_landing_page_contains_iot_text(client):
    """Landing page Developers section must mention IoT."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert "IoT" in content, "Landing page must contain 'IoT' in Developers section"


def test_landing_page_contains_webhooks_text(client):
    """Landing page Developers section must mention Webhooks."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert "Webhook" in content, "Landing page must contain 'Webhook' in Developers section"


def test_landing_page_contains_credit_intelligence_text(client):
    """Landing page Developers section must mention Credit Intelligence."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert "Credit" in content, "Landing page must contain 'Credit' in Developers section"


def test_landing_page_has_explore_developer_tools_cta(client):
    """Landing page must have a 'Explore Developer Tools' CTA linking to /developers/."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert "Explore Developer Tools" in content, "'Explore Developer Tools' CTA must be on landing page"
    developers_url = reverse("staticpages:developers")
    assert developers_url in content, f"CTA must link to {developers_url}"


def test_landing_page_navbar_has_developers_link(client):
    """Navbar must contain a Developers link."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    developers_url = reverse("staticpages:developers")
    assert developers_url in content, "Navbar must include the /developers/ URL"


def test_landing_page_developers_section_id_present(client):
    """Landing page must have #developers section anchor."""
    url = reverse("staticpages:home")
    response = client.get(url)
    content = response.content.decode()
    assert 'id="developers"' in content, "Developers section must have id='developers'"


def test_landing_page_no_regression_existing_sections(client):
    """Existing landing page sections must still be present after new additions."""
    url = reverse("staticpages:home")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "How It Works" in content
    assert "Get Started" in content
    assert "Emajinet" in content


def test_developers_page_renders(client):
    """The /developers/ page must render successfully."""
    url = reverse("staticpages:developers")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "IoT" in content or "Webhook" in content or "Developer" in content


# ---------------------------------------------------------------------------
# IoT Webhook
# ---------------------------------------------------------------------------

IOT_PAYLOAD = {
    "device_id": "ESP32-TEST-001",
    "device_type": "esp32",
    "source": "test_gateway",
    "recorded_at": "2026-04-28T10:30:00Z",
    "readings": [
        {"type": "temperature", "value": 28.5, "unit": "C"},
        {"type": "humidity", "value": 62, "unit": "%"},
        {"type": "soil_moisture", "value": 41, "unit": "%"},
        {"type": "battery_voltage", "value": 3.9, "unit": "V"},
    ],
    "metadata": {"farm": "Test Farm", "location": "Lilongwe"},
}

WEBHOOK_SECRET = "test-secret-abc123"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_accepts_valid_payload(client):
    """IoT webhook must accept a valid payload and return 201."""
    url = reverse("integrations:webhook_iot")
    response = client.post(
        url,
        data=json.dumps(IOT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    assert data["device_id"] == "ESP32-TEST-001"
    assert "event_id" in data


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_creates_webhook_event(client):
    """IoT webhook must create a WebhookEvent record."""
    from integrations.models import WebhookEvent

    before = WebhookEvent.objects.count()
    url = reverse("integrations:webhook_iot")
    client.post(
        url,
        data=json.dumps(IOT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert WebhookEvent.objects.count() == before + 1
    event = WebhookEvent.objects.latest("received_at")
    assert event.event_type == "iot.reading"
    assert event.source == "test_gateway"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_creates_iot_device_and_readings(client):
    """IoT webhook must create IoTDevice and IoTReading records."""
    from inventory.models_iot import IoTDevice, IoTReading

    url = reverse("integrations:webhook_iot")
    payload = {**IOT_PAYLOAD, "device_id": "ESP32-UNIQUE-READS-001"}
    client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    device = IoTDevice.objects.filter(device_id="ESP32-UNIQUE-READS-001").first()
    assert device is not None, "IoTDevice must be created by IoT webhook"

    readings = IoTReading.objects.filter(device=device)
    assert readings.count() == 4, f"Expected 4 readings, got {readings.count()}"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_rejects_missing_device_id(client):
    """IoT webhook must return 400 when device_id is missing."""
    url = reverse("integrations:webhook_iot")
    bad_payload = {**IOT_PAYLOAD}
    del bad_payload["device_id"]
    response = client.post(
        url,
        data=json.dumps(bad_payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 400
    assert "device_id" in response.json().get("error", "")


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_rejects_malformed_json(client):
    """IoT webhook must return 400 for non-JSON body."""
    url = reverse("integrations:webhook_iot")
    response = client.post(
        url,
        data="this is not json }{",
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 400


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_rejects_wrong_token(client):
    """IoT webhook must return 403 when wrong token is provided."""
    url = reverse("integrations:webhook_iot")
    response = client.post(
        url,
        data=json.dumps(IOT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer wrong-token",
    )
    assert response.status_code == 403


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_rejects_missing_token(client):
    """IoT webhook must return 403 when no token is provided."""
    url = reverse("integrations:webhook_iot")
    response = client.post(
        url,
        data=json.dumps(IOT_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == 403


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_iot_webhook_accepts_x_emajinet_token_header(client):
    """IoT webhook must also accept X-Emajinet-Webhook-Token header."""
    url = reverse("integrations:webhook_iot")
    payload = {**IOT_PAYLOAD, "device_id": "ESP32-XHDR-001"}
    response = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_EMAJINET_WEBHOOK_TOKEN=WEBHOOK_SECRET,
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Credit Webhook
# ---------------------------------------------------------------------------

CREDIT_PAYLOAD = {
    "source": "mobile_money_partner",
    "customer_ref": "CUST-TEST-001",
    "occurred_at": "2026-04-28T10:30:00Z",
    "signals": [
        {"type": "repayment", "amount": 25000, "currency": "MWK", "days_late": 0},
    ],
    "metadata": {"channel": "mobile_money", "transaction_id": "TXN-TEST-123"},
}


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_credit_webhook_accepts_valid_payload(client):
    """Credit webhook must accept valid payload and return 201."""
    url = reverse("integrations:webhook_credit")
    response = client.post(
        url,
        data=json.dumps(CREDIT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    assert data["customer_ref"] == "CUST-TEST-001"
    assert data["signals_created"] == 1


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_credit_webhook_creates_webhook_event(client):
    """Credit webhook must create a WebhookEvent record."""
    from integrations.models import WebhookEvent

    before = WebhookEvent.objects.count()
    url = reverse("integrations:webhook_credit")
    client.post(
        url,
        data=json.dumps(CREDIT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert WebhookEvent.objects.count() == before + 1
    event = WebhookEvent.objects.latest("received_at")
    assert event.event_type == "credit.signal"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_credit_webhook_creates_credit_signal(client):
    """Credit webhook must create CreditSignal records."""
    from integrations.models import CreditSignal

    before = CreditSignal.objects.count()
    url = reverse("integrations:webhook_credit")
    client.post(
        url,
        data=json.dumps(CREDIT_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert CreditSignal.objects.count() == before + 1
    sig = CreditSignal.objects.latest("created_at")
    assert sig.signal_type == "repayment"
    assert sig.customer_ref == "CUST-TEST-001"
    assert sig.source == "mobile_money_partner"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_credit_webhook_rejects_missing_source(client):
    """Credit webhook must return 400 when source is missing."""
    url = reverse("integrations:webhook_credit")
    bad = {**CREDIT_PAYLOAD}
    del bad["source"]
    response = client.post(
        url,
        data=json.dumps(bad),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 400


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_credit_webhook_rejects_malformed_json(client):
    """Credit webhook must return 400 for bad JSON."""
    url = reverse("integrations:webhook_credit")
    response = client.post(
        url,
        data="{invalid",
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Generic Webhook
# ---------------------------------------------------------------------------

GENERIC_PAYLOAD = {
    "source": "partner_app",
    "event_type": "stock.updated",
    "payload": {"sku": "SUGAR-1KG", "quantity": 20},
}


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_generic_webhook_accepts_valid_payload(client):
    """Generic webhook must accept any valid JSON payload and return 201."""
    url = reverse("integrations:webhook_generic")
    response = client.post(
        url,
        data=json.dumps(GENERIC_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    assert data["source"] == "partner_app"
    assert data["event_type"] == "stock.updated"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_generic_webhook_creates_webhook_event(client):
    """Generic webhook must create a WebhookEvent record."""
    from integrations.models import WebhookEvent

    before = WebhookEvent.objects.count()
    url = reverse("integrations:webhook_generic")
    client.post(
        url,
        data=json.dumps(GENERIC_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert WebhookEvent.objects.count() == before + 1
    event = WebhookEvent.objects.latest("received_at")
    assert event.source == "partner_app"
    assert event.event_type == "stock.updated"
    assert event.status == "processed"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_generic_webhook_stores_raw_payload(client):
    """Generic webhook must store the full JSON payload."""
    from integrations.models import WebhookEvent

    url = reverse("integrations:webhook_generic")
    client.post(
        url,
        data=json.dumps(GENERIC_PAYLOAD),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    event = WebhookEvent.objects.latest("received_at")
    assert event.payload.get("payload", {}).get("sku") == "SUGAR-1KG"


@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_generic_webhook_rejects_malformed_json(client):
    """Generic webhook must return 400 for bad JSON."""
    url = reverse("integrations:webhook_generic")
    response = client.post(
        url,
        data="not-json-at-all",
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Token authentication — no secret configured (dev mode)
# ---------------------------------------------------------------------------

@override_settings(EMAJINET_WEBHOOK_SECRET="", DEBUG=True)
def test_webhooks_allow_in_dev_without_secret(client):
    """In dev mode with no secret set, webhooks must allow requests (warn only)."""
    url = reverse("integrations:webhook_generic")
    response = client.post(
        url,
        data=json.dumps(GENERIC_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == 201


@override_settings(EMAJINET_WEBHOOK_SECRET="", DEBUG=False)
def test_webhooks_reject_in_production_without_secret(client):
    """In production (DEBUG=False) with no secret, webhooks must fail closed (403)."""
    url = reverse("integrations:webhook_generic")
    response = client.post(
        url,
        data=json.dumps(GENERIC_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Return JSON content-type
# ---------------------------------------------------------------------------

@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_webhook_responses_are_json(client):
    """All webhook responses must have application/json content type."""
    for view_name, payload in [
        ("integrations:webhook_iot", IOT_PAYLOAD),
        ("integrations:webhook_credit", CREDIT_PAYLOAD),
        ("integrations:webhook_generic", GENERIC_PAYLOAD),
    ]:
        url = reverse(view_name)
        response = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {WEBHOOK_SECRET}",
        )
        assert response["Content-Type"].startswith("application/json"), (
            f"{view_name} must return application/json"
        )


# ---------------------------------------------------------------------------
# GET requests must fail (require_POST)
# ---------------------------------------------------------------------------

@override_settings(EMAJINET_WEBHOOK_SECRET=WEBHOOK_SECRET, DEBUG=True)
def test_webhook_rejects_get_requests(client):
    """Webhook endpoints must reject GET requests with 405."""
    for view_name in ["integrations:webhook_iot", "integrations:webhook_credit", "integrations:webhook_generic"]:
        url = reverse(view_name)
        response = client.get(url)
        assert response.status_code == 405, (
            f"{view_name} must return 405 for GET requests"
        )
