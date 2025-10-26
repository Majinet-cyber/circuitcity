# timelogs/urls.py
from django.urls import path
from . import views
app_name = "timelogs"
urlpatterns = [
    path("start/", views.start_shift, name="start"),
    path("<int:timelog_id>/stop/", views.stop_shift, name="stop"),
    path("<int:timelog_id>/ping/", views.gps_ping, name="ping"),
]


