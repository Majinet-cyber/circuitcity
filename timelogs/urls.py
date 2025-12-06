# timelogs/urls.py
from django.urls import path
from . import views, views_geo

app_name = "timelogs"

urlpatterns = [
    # Enhanced geo-based presence tracking endpoints
    path("ping-location/", views_geo.ping_location, name="ping_location"),
    
    # Agent presence endpoints (using original views)
    path("api/agent/presence-today/", views.agent_presence_today, name="presence_today"),
    path("api/manager/presence-dashboard/", views.manager_presence_dashboard, name="manager_presence"),
    
    # Time Logs UI
    path("dashboard/", views.time_logs_dashboard, name="dashboard"),
    path("export-csv/", views.export_time_logs_csv, name="export_csv"),
    
    # Legacy shift-based endpoints (kept for backwards compatibility)
    path("start/", views.start_shift, name="start"),
    path("<int:timelog_id>/stop/", views.stop_shift, name="stop"),
    path("<int:timelog_id>/ping/", views.gps_ping, name="ping"),
]
