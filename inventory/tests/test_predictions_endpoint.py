# inventory/tests/test_predictions_endpoint.py
from django.test import Client

def test_predictions_endpoint_is_resilient():
    c = Client()
    r = c.get("/inventory/api/predictions/")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "predictions" in body
