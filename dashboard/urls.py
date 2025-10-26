# circuitcity/dashboard/urls.py
from django.urls import path
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import RedirectView
from . import views

app_name = "dashboard"  # namespace for URL reversing

# -------- helpers: safe stub maker --------
def _stub(payload, status=200):
    @require_GET
    def _view(request, *args, **kwargs):
        return JsonResponse(payload, status=status)
    return _view

# -------- choose recommendation view (prefer v2, then local api, then stub) --------
_recs_view = getattr(views, "v2_recommendations_proxy", None) \
    or getattr(views, "api_recommendations", None) \
    or _stub({"items": [], "model": None, "message": "dev stub"})

# -------- v2 proxy endpoints with safe fallbacks --------
sales_trend_v2   = getattr(views, "v2_sales_trend_data_proxy", None) or _stub({"labels": [], "values": []})
top_models_v2    = getattr(views, "v2_top_models_data_proxy", None) or _stub({"labels": [], "values": []})
profit_bar_v2    = getattr(views, "v2_profit_data_proxy", None)     or _stub({"labels": [], "data": []})
agent_trend_v2   = getattr(views, "v2_agent_trend_data_proxy", None) or _stub({"labels": [], "data": []})
cash_overview_v2 = getattr(views, "v2_cash_overview_proxy", None)   or _stub(
    {"orders": 0, "revenue": 0, "paid_out": 0, "expenses": 0, "period_label": ""}
)
recs_v2          = getattr(views, "v2_recommendations_proxy", None) or _stub({"items": [], "model": None, "message": "dev stub"})

# optional soft redirects/healthz
admin_dash_proxy = getattr(views, "admin_dashboard_proxy", None) or getattr(views, "admin_dashboard", None)
agent_dash_proxy = getattr(views, "agent_dashboard_proxy", None) or getattr(views, "agent_dashboard", None)
healthz_view     = getattr(views, "dashboard_healthz_proxy", None) or _stub({"ok": True})

urlpatterns = [
    # ==== Primary pages ====
    # Main app dashboard (tenant-aware)
    path("", views.home, name="home"),
    path("home/", views.home, name="dashboard_home"),  # ✅ alias so reverse("dashboard:dashboard_home") works

    # Legacy alias → redirects to home
    path(
        "dashboard/",
        RedirectView.as_view(pattern_name="dashboard:home", permanent=False),
        name="dashboard",
    ),

    # Admin & agent variants
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("agent/", views.agent_dashboard, name="agent_dashboard"),
    path("agents/<int:pk>/", views.agent_detail, name="admin_agent_detail"),

    # ✅ AI-CFO Panel
    path("cfo/", views.cfo_panel, name="dashboard_cfo"),

    # ==== First-party JSON endpoints ====
    path("api/profit-data/", views.profit_data, name="profit_data"),
    path("api/agent-trend/", views.agent_trend_data, name="agent_trend_data"),

    # ==== AI recommendations ====
    path("api/recommendations/", _recs_view, name="recommendations_api"),
    path("api/recommendations/v2/", recs_v2, name="recommendations_v2"),

    # ==== v2 proxies ====
    path("api/sales-trend/", sales_trend_v2, name="sales_trend"),
    path("api/top-models/", top_models_v2, name="top_models"),
    path("api/profit-bar/", profit_bar_v2, name="profit_bar"),
    path("api/agent-trend/v2/", agent_trend_v2, name="agent_trend_v2"),
    path("api/cash-overview/", cash_overview_v2, name="cash_overview"),

    # ==== Soft redirects & health ====
    path("inventory/", admin_dash_proxy, name="inventory_dashboard_redirect"),
    path("proxy/agent/", agent_dash_proxy, name="agent_dashboard_redirect"),
    path("healthz/", healthz_view, name="healthz"),
]


