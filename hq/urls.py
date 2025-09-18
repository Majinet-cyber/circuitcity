from django.urls import path
from . import views

app_name = "hq"

urlpatterns = [
    # Dashboard (root)
    path("", views.dashboard, name="dashboard"),
    # Optional alias so older code can still reverse 'hq:home'
    path("home/", views.dashboard, name="home"),

    # Lists
    path("businesses/", views.businesses, name="businesses"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("invoices/", views.invoices, name="invoices"),
    path("agents/", views.agents, name="agents"),
    path("stock-trends/", views.stock_trends, name="stock_trends"),

    # Details
    path("businesses/<int:pk>/", views.business_detail, name="business_detail"),

    # Wallet
    path("wallet/", views.wallet_home, name="wallet"),

    # Admin actions (superuser tools used by UI buttons)
    path("subscriptions/<int:pk>/adjust-trial/", views.sub_adjust_trial, name="sub_adjust_trial"),
    path("subscriptions/<int:pk>/cancel/", views.sub_cancel, name="sub_cancel"),
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),

    # Lightweight JSON APIs used by the dashboard UI
    path("api/wallet/income", views.api_wallet_income, name="api_wallet_income"),
    path("api/subscriptions/mrr", views.api_mrr_timeseries, name="api_mrr_timeseries"),
    path("api/search/suggest", views.api_search_suggest, name="api_search_suggest"),
    path("api/notifications", views.api_notifications, name="api_notifications"),
]
