# circuitcity/inventory/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views

# Try to import the optional API module.
# Use broad Exception so deploys don't break if api.py imports fail at runtime.
try:
    from . import api  # expects api.predictions_summary(request)
    _HAS_API_MODULE = True
except Exception:
    api = None
    _HAS_API_MODULE = False

# Namespace so {% url 'inventory:...' %} works
app_name = "inventory"

urlpatterns = [
    # ---------- Dashboard ----------
    path("dashboard/", views.inventory_dashboard, name="inventory_dashboard"),

    # App home → dashboard
    path("", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False), name="home"),
    path("dash/", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),

    # Old dashboard links → redirect to main dashboard
    path("dashboard/agent/",  RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),
    path("dashboard/agents/", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),

    # ---------- Stock scanning ----------
    path("scan-in/",   views.scan_in,   name="scan_in"),
    path("scan-sold/", views.scan_sold, name="scan_sold"),
    path("scan-web/",  views.scan_web,  name="scan_web"),  # desktop-first scanner page

    # Short mobile-friendly aliases
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

    # ---------- UI: Time & Wallet ----------
    path("time/checkin/", views.time_checkin_page, name="time_checkin_page"),
    path("time/logs/",    views.time_logs,         name="time_logs"),
    path("wallet/",       views.wallet_page,       name="wallet"),
    path("time/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),

    # ---------- Health check ----------
    path("healthz/", views.healthz, name="healthz"),
]

# ---------- API: Time, Wallet, Charts ----------
urlpatterns += [
    # Mark sold
    path("api/mark-sold/",       views.api_mark_sold,        name="api_mark_sold"),

    # Charts (hyphen style)
    path("api/sales-trend/",     views.api_sales_trend,      name="api_sales_trend"),
    path("api/top-models/",      views.api_top_models,       name="api_top_models"),
    path("api/profit-bar/",      views.api_profit_bar,       name="api_profit_bar"),
    path("api/agent-trend/",     views.api_agent_trend,      name="api_agent_trend"),

    # Wallet + Time APIs
    path("api/time-checkin/",    views.api_time_checkin,     name="api_time_checkin"),
    path("api/wallet-summary/",  views.api_wallet_summary,   name="api_wallet_summary"),
    path("api/wallet-txn/",      views.api_wallet_add_txn,   name="api_wallet_add_txn"),
]

# --- Underscore aliases for front-end that calls /inventory/api_foo ---
urlpatterns += [
    path("api_sales_trend",  views.api_sales_trend),   # e.g. /inventory/api_sales_trend?period=7d&metric=count
    path("api_top_models",   views.api_top_models),    # e.g. /inventory/api_top_models?period=today
    path("api_profit_bar",   views.api_profit_bar),    # e.g. /inventory/api_profit_bar
    path("api_agent_trend",  views.api_agent_trend),   # e.g. /inventory/api_agent_trend?months=6&metric=sales
]

# ---------- API: Predictions ----------
# Prefer inventory/api.py if it exists and exposes predictions_summary;
# otherwise fall back to the views implementation.
if _HAS_API_MODULE and hasattr(api, "predictions_summary"):
    urlpatterns += [
        path("api/predictions/",              api.predictions_summary, name="api_predictions"),
        path("api/predictions/summary/",      api.predictions_summary),  # alias
    ]
else:
    urlpatterns += [
        path("api/predictions/",              views.api_predictions, name="api_predictions"),
        path("api/predictions/summary/",      views.api_predictions),  # alias
    ]

# Also expose a v2 alias (same payload for now)
urlpatterns += [
    path("api/predictions/v2/", views.api_predictions, name="api_predictions_v2"),
]

# ---------- Cash Overview ----------
# Hyphen route (current) and underscore alias (some JS references use underscore)
urlpatterns += [
    path("api/cash-overview/",  views.api_cash_overview,  name="api_cash_overview"),
    path("api_cash_overview",   views.api_cash_overview),  # alias
]
