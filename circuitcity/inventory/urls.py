# inventory/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "inventory"

urlpatterns = [
    # Dashboard
    path("dashboard/", views.inventory_dashboard, name="inventory_dashboard"),
    path("", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),
    # Back-compat alias so reverse('inventory:dashboard') still works
    path("dash/", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False), name="dashboard"),

    # Stock scanning
    path("scan-in/",   views.scan_in,   name="scan_in"),
    path("scan-sold/", views.scan_sold, name="scan_sold"),
    path("scan-web/",  views.scan_web,  name="scan_web"),  # desktop-first scanner page

    # Short mobile-friendly aliases (optional)
    path("in/",   RedirectView.as_view(pattern_name="inventory:scan_in",   permanent=False), name="short_in"),
    path("sold/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="short_sold"),
    path("scan/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="short_scan"),

    # Stock viewing
    path("list/",   views.stock_list, name="stock_list"),
    path("stocks/", RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False)),

    # CSV export
    path("export/", views.export_csv, name="export_csv"),

    # Stock management (edit / delete / restore)
    path("update/<int:pk>/",  views.update_stock,  name="update_stock"),
    path("delete/<int:pk>/",  views.delete_stock,  name="delete_stock"),
    path("restore/<int:pk>/", views.restore_stock, name="restore_stock"),

    # Agent-only password reset placeholders
    path("forgot/",             views.agent_forgot_password, name="agent_forgot_password"),
    path("reset/",              views.agent_reset_confirm,   name="agent_reset_confirm"),
    path("reset/<slug:token>/", views.agent_reset_confirm,   name="agent_reset_confirm_token"),

    # ---------- UI: Time & Wallet ----------
    path("time/checkin/", views.time_checkin_page, name="time_checkin_page"),
    path("time/logs/",    views.time_logs,         name="time_logs"),
    path("wallet/",       views.wallet_page,       name="wallet"),
    path("time/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
]

# ---------- API: Time, Wallet, Charts ----------
urlpatterns += [
    path("api/mark-sold/",       views.api_mark_sold,       name="api_mark_sold"),
    path("api/sales-trend/",     views.api_sales_trend,     name="api_sales_trend"),
    path("api/top-models/",      views.api_top_models,      name="api_top_models"),
    path("api/profit-bar/",      views.api_profit_bar,      name="api_profit_bar"),
    path("api/agent-trend/",     views.api_agent_trend,     name="api_agent_trend"),
    path("api/time-checkin/",    views.api_time_checkin,    name="api_time_checkin"),
    path("api/wallet-summary/",  views.api_wallet_balance,  name="api_wallet_summary"),
    path("api/wallet-txn/",      views.api_wallet_txn,      name="api_wallet_add_txn"),
]
