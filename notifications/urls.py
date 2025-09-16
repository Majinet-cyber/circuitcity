# circuitcity/notifications/urls.py
from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    # Frontend polling endpoint (AJAX): returns latest notifications
    path("inbox.json", views.feed, name="inbox_json"),

    # Alternate feed URL (kept for compatibility if referenced elsewhere)
    path("feed/", views.feed, name="feed"),

    # Mark notifications as read (single or bulk)
    path("read/", views.mark_read, name="mark_read"),
    path("mark-read/", views.mark_read, name="mark_read_alt"),
]
