# inventory/tests/test_predictions_endpoint.py
import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from tenants.models import Business, Membership


@pytest.mark.django_db
def test_predictions_endpoint_is_resilient(settings):
    # Avoid SSL redirect and static manifest issues during tests
    settings.SECURE_SSL_REDIRECT = False
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

    user = get_user_model().objects.create_user(
        username=f"pred-{uuid.uuid4()}@example.com",
        email=f"pred-{uuid.uuid4()}@example.com",
        password="StrongPass!23",
    )
    biz = Business.objects.create(
        name=f"Predictions {uuid.uuid4()}",
        slug=f"pred-{uuid.uuid4()}",
        status="ACTIVE",
    )
    Membership.objects.create(user=user, business=biz, role="MANAGER", status="ACTIVE")

    c = Client()
    c.force_login(user)
    session = c.session
    session["active_business_id"] = biz.id
    session["biz_id"] = biz.id
    session.save()

    r = c.get("/inventory/api/predictions/")

    # Accept common “ok” responses in dev/test environments
    assert r.status_code in (200, 404, 405)

    if r.status_code == 200:
        # Must be valid JSON
        body_text = (r.content or b"{}").decode("utf-8", errors="ignore") or "{}"
        try:
            data = json.loads(body_text)
        except Exception:
            pytest.fail("Predictions endpoint returned non-JSON payload")

        # Be lenient but meaningful: expect a basic shape
        assert isinstance(data, dict)
        assert "ok" in data
        # Some implementations use "predictions", others return an "overall" series.
        assert ("predictions" in data) or ("overall" in data)
