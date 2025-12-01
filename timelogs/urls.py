# timelogs/urls.py
from django.urls import path
from . import views

app_name = "timelogs"

urlpatterns = [
    # New presence tracking endpoints
    path("api/agent/ping-location/", views.ping_location, name="ping_location"),
    path("api/agent/presence-today/", views.agent_presence_today, name="presence_today"),
    path("api/manager/presence-dashboard/", views.manager_presence_dashboard, name="manager_presence"),
    
    # Time Logs UI
    path("", views.time_logs_dashboard, name="dashboard"),
    path("export-csv/", views.export_time_logs_csv, name="export_csv"),
    
    # Legacy shift-based endpoints (kept for backwards compatibility)
    path("start/", views.start_shift, name="start"),
    path("<int:timelog_id>/stop/", views.stop_shift, name="stop"),
    path("<int:timelog_id>/ping/", views.gps_ping, name="ping"),
]
