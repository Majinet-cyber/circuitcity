# notifications/urls.py
from django.urls import path
from . import views, views_whatsapp

app_name = "notifications"

urlpatterns = [
    # Notification views
    path("", views.notification_list, name="list"),
    path("dropdown/", views.notification_dropdown, name="dropdown"),
    path("<int:pk>/read/", views.mark_as_read, name="mark_read"),
    path("<int:pk>/read-redirect/", views.mark_read_and_redirect, name="mark_read_and_redirect"),
    path("read-all/", views.mark_all_as_read, name="mark_all_read"),
    # WhatsApp settings
    path("whatsapp/settings/", views_whatsapp.whatsapp_settings, name="whatsapp_settings"),
    path("whatsapp/test/", views_whatsapp.whatsapp_test, name="whatsapp_test"),
]
