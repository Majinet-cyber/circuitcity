from django.urls import path
from . import views
urlpatterns = [
    path("api/forecast/", views.api_forecast, name="api_forecast"),
    path("api/leaderboard/", views.api_leaderboard, name="api_leaderboard"),
    path("api/alerts/", views.api_alerts, name="api_alerts"),
]
