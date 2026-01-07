"""
Debug URLs for internal testing and diagnostics.

All views here should be restricted to staff/superuser only.
"""
from django.urls import path
from . import views_debug

app_name = "debug"

urlpatterns = [
    path("whatsapp-test/", views_debug.whatsapp_test, name="whatsapp_test"),
]
