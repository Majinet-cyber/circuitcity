# dashboard/urls.py
from django.urls import path
from . import views

app_name = "dashboard"  # namespace for URL reversing

urlpatterns = [
    # Default landing page for the dashboard namespace
    # This will redirect to admin_dashboard or agent_dashboard depending on the user type
    path("", views.admin_dashboard, name="dashboard"),  # could later be a redirect view

    # Admin/staff dashboard
    path("admin/", views.admin_dashboard, name="admin_dashboard"),

    # Agent self dashboard (used for LOGIN_REDIRECT_URL)
    path("agent/", views.agent_dashboard, name="agent_dashboard"),

    # Clickable agent detail (from the admin dashboard cards)
    path("agents/<int:pk>/", views.agent_detail, name="admin_agent_detail"),

    # JSON endpoints for charts and trends
    path("api/profit-data/", views.profit_data, name="profit_data"),
    path("api/agent-trend/", views.agent_trend_data, name="agent_trend_data"),
]
