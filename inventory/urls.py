# inventory/urls.py
from django.urls import path, re_path
from django.views.generic import RedirectView
from django.http import JsonResponse
from . import views

app_name = "inventory"

# ---- SAFE, LAZY PREDICTIONS PROXY (no import-time lookups) ----------
def _predictions_proxy(request, *args, **kwargs):
    """
    Try inventory.api.predictions_summary (preferred), else views.api_predictions
    (if present). Otherwise return a harmless JSON.
    """
    try:
        from . import api as api_mod
        func = getattr(api_mod, "predictions_summary", None)
        if callable(func):
            return func(request, *args, **kwargs)
    except Exception:
        pass

    func2 = getattr(views, "api_predictions", None)
    if callable(func2):
        return func2(request, *args, **kwargs)

    return JsonResponse({"ok": False, "error": "predictions endpoint not available"}, status=200)

# ---------------------------------------------------------------------

urlpatterns = [
    # ---------- Dashboard ----------
    path("dashboard/", views.inventory_dashboard, name="inventory_dashboard"),
    path("", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False), name="home"),
    path("dash/", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),

    # ---------- Stock scanning ----------
    path("scan-in/",   views.scan_in,   name="scan_in"),
    path("scan-sold/", views.scan_sold, name="scan_sold"),
    path("scan-web/",  views.scan_web,  name="scan_web"),
    path("in/",   RedirectView.as_view(pattern_name="inventory:scan_in",   permanent=False), name="short_in"),
    path("sold/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="short_sold"),
    path("scan/", RedirectView.as_view(pattern_name="inventory:scan_web",  permanent=False), name="short_scan"),

    # ---------- Stock viewing ----------
    path("list/",   views.stock_list, name="stock_list"),
    path("stocks/", RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False)),

    # ---------- CSV export ----------
    path("export/", views.export_csv, name="export_csv"),

    # ---------- Stock management ----------
    path("update/<int:pk>/",  views.update_stock,  name="update_stock"),
    path("delete/<int:pk>/",  views.delete_stock,  name="delete_stock"),
    path("restore/<int:pk>/", views.restore_stock, name="restore_stock"),

    # ---------- Agent-only password reset placeholders ----------
    path("forgot/",             views.agent_forgot_password, name="agent_forgot_password"),
    path("reset/",              views.agent_reset_confirm,   name="agent_reset_confirm"),
    path("reset/<slug:token>/", views.agent_reset_confirm,   name="agent_reset_confirm_token"),

    # ---------- UI: Time & Wallet ----------
    path("time/checkin/", views.time_checkin_page, name="time_checkin_page"),
    path("time/logs/",    views.time_logs,         name="time_logs"),
    path("wallet/",       views.wallet_page,       name="wallet"),
    path("time/",         RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-checkin/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-logs/",    RedirectView.as_view(pattern_name="inventory:time_logs",         permanent=False)),

    # ---------- Health check ----------
    path("healthz/", views.healthz, name="healthz"),
]

# ---------- API: Time, Wallet, Charts ----------
urlpatterns += [
    path("api/mark-sold/",       views.api_mark_sold,        name="api_mark_sold"),
    path("api/sales-trend/",     views.api_sales_trend,      name="api_sales_trend"),
    path("api/top-models/",      views.api_top_models,       name="api_top_models"),
    path("api/profit-bar/",      views.api_profit_bar,       name="api_profit_bar"),
    path("api/agent-trend/",     views.api_agent_trend,      name="api_agent_trend"),
    path("api/time-checkin/",    views.api_time_checkin,     name="api_time_checkin"),
    path("api/wallet-summary/",  views.api_wallet_summary,   name="api_wallet_summary"),
    path("api/wallet-txn/",      views.api_wallet_add_txn,   name="api_wallet_add_txn"),
    re_path(r"^api/cash[-_]overview/?$", views.api_cash_overview, name="api_cash_overview"),
]

# ---------- API: Predictions (robust aliases) ----------
urlpatterns += [
    re_path(r"^api/predictions/?$",      _predictions_proxy, name="api_predictions"),
    re_path(r"^api[-_]?predictions/?$", _predictions_proxy),
    re_path(r"^api_predictions/?$",      _predictions_proxy),
    re_path(r"^api/predictions/v2/?$",   _predictions_proxy, name="api_predictions_v2"),
]

# ---------- API: Legacy chart aliases ----------
urlpatterns += [
    re_path(r"^api[_-]?sales[_-]?trend/?$",  views.api_sales_trend),
    re_path(r"^api[_-]?profit[_-]?bar/?$",   views.api_profit_bar),
    re_path(r"^api[_-]?top[_-]?models/?$",   views.api_top_models),
]
