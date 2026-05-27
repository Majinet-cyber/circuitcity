# inventory/urls_iot.py
"""URL routing for IoT monitoring."""
from django.urls import path

from inventory.verticals import iot

app_name = "iot"

urlpatterns = [
    path("dashboard/", iot.dashboard, name="dashboard"),
    path("webhook/", iot.webhook, name="webhook"),
]
