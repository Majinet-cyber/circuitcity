# dashboard/urls.py
from django.urls import path
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from . import views

app_name = "dashboard"  # namespace for URL reversing


# -------- helpers: safe stub maker --------
def _stub(payload, status=200):
    @require_GET
    def _view(request, *args, **kwargs):
        return JsonResponse(payload, status=status)
    return _view


# -------- choose recommendation view (prefer v2, then v1, then stub) --------
_recs_view = getattr(views, "v2_recommendations_proxy", None) \
    or getattr(views, "recommendations_api", None) \
    or getattr(views, "recommendations_stub", None) \
    or _stub({"items": [], "model": None, "message": "dev stub"})


# -------- v2 proxy endpoints with safe fallbacks (so imports never crash) --------
sales_trend_v2   = getattr(views, "v2_sales_trend_data_proxy", None) or _stub({"labels": [], "values": []})
top_models_v2    = getattr(views, "v2_top_models_data_proxy", None)    or _stub({"labels": [], "values": []})
profit_bar_v2    = getattr(views, "v2_profit_data_proxy", None)        or _stub({"labels": [], "data": []})
agent_trend_v2   = getattr(views, "v2_agent_trend_data_proxy", None)   or _stub({"labels": [], "data": []})
cash_overview_v2 = getattr(views, "v2_cash_overview_proxy", None)      or _stub(
    {"orders": 0, "revenue": 0, "paid_out": 0, "expenses": 0, "period_label": ""}
)
recs_v2          = getattr(views, "v2_recommendations_proxy", None)    or _stub({"items": [], "model": None, "message": "dev stub"})

# optional soft redirect/healthz (fallbacks won’t crash)
admin_dash_proxy = getattr(views, "admin_dashboard_proxy", None) or getattr(views, "admin_dashboard", None)
healthz_view     = getattr(views, "dashboard_healthz_proxy", None) or _stub({"ok": True})


urlpatterns = [
    # Default landing page for the dashboard namespace
    path("", views.admin_dashboard, name="dashboard"),

    # Admin/staff dashboard
    path("admin/", views.admin_dashboard, name="admin_dashboard"),

    # Agent self dashboard
    path("agent/", views.agent_dashboard, name="agent_dashboard"),

    # Clickable agent detail
    path("agents/<int:pk>/", views.agent_detail, name="admin_agent_detail"),

    # Existing JSON endpoints
    path("api/profit-data/", views.profit_data, name="profit_data"),
    path("api/agent-trend/", views.agent_trend_data, name="agent_trend_data"),

    # AI recommendations (v2/v1/stub)
    path("api/recommendations/", _recs_view, name="recommendations_api"),

    # ---- v2 proxies to inventory APIs (safe fallbacks) ----
    path("api/sales-trend/", sales_trend_v2, name="sales_trend"),
    path("api/top-models/", top_models_v2, name="top_models"),
    path("api/profit-bar/", profit_bar_v2, name="profit_bar"),
    path("api/agent-trend/v2/", agent_trend_v2, name="agent_trend_v2"),
    path("api/cash-overview/", cash_overview_v2, name="cash_overview"),
    path("api/recommendations/v2/", recs_v2, name="recommendations_v2"),

    # Optional soft redirect endpoint + app health
    path("inventory/", admin_dash_proxy, name="inventory_dashboard_redirect"),
    path("healthz/", healthz_view, name="healthz"),
]
