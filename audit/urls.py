# audit/urls.py
from django.urls import path
from . import views

app_name = "audit"

urlpatterns = [
    path("logs/", views.audit_log_list, name="log_list"),
    path("stats/", views.audit_log_stats, name="log_stats"),
]
