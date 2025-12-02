# notifications/urls.py
from django.urls import path
from . import views_whatsapp

app_name = "notifications"

urlpatterns = [
    path("whatsapp/settings/", views_whatsapp.whatsapp_settings, name="whatsapp_settings"),
    path("whatsapp/test/", views_whatsapp.whatsapp_test, name="whatsapp_test"),
]
