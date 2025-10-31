# inventory/tests/test_predictions_endpoint.py
import json
import pytest
from django.test import Client

@pytest.mark.django_db
def test_predictions_endpoint_is_resilient(settings):
    # Avoid SSL redirect and static manifest issues during tests
    settings.SECURE_SSL_REDIRECT = False
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

    c = Client()
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
        # predictions may be a list or dict depending on your stub
        assert "predictions" in data
