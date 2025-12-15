# hq/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views
from . import views_business_directory as v

# Optional imports with defensive handling
try:
    from . import views_currency_settings
except ImportError:
    views_currency_settings = None

try:
    from . import views_contracts
except ImportError:
    views_contracts = None

try:
    from . import views_business_detail
except ImportError:
    views_business_detail = None

try:
    from . import views_account_support
except ImportError:
    views_account_support = None

# All URLs are namespaced as 'hq:<name>'
app_name = "hq"

urlpatterns = [
    # =========================
    # Canonical HQ Dashboard
    # =========================
    # /hq/ -> /hq/dashboard/
    path("", RedirectView.as_view(pattern_name="hq:dashboard", permanent=False)),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Alias (same view)
    path("home/", views.dashboard, name="home"),

    # =========================
    # Lists
    # =========================
    # Direct view (NO redirect) - prevents redirect loops
    path("businesses/", v.business_directory, name="business_directory"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("invoices/",      views.invoices,      name="invoices"),
    path("agents/",        views.agents,        name="agents"),
    path("stock-trends/",  views.stock_trends,  name="stock_trends"),

    # =========================
    # Details
    # =========================
    path("businesses/<int:pk>/", v.business_detail, name="business_detail"),

    # =========================
    # API Endpoints
    # =========================
    path("api/monthly-drill-down/", views.monthly_drill_down_api, name="monthly_drill_down_api"),
    path("api/wallet/income", views.api_wallet_income, name="hq_wallet_income_api_noslash"),
    path("api/wallet/income/", views.api_wallet_income, name="hq_wallet_income_api"),
    path("api/analytics/data.json", views.api_analytics_data, name="hq_analytics_data"),
    path("analytics/", views.hq_analytics, name="hq_analytics"),

    # =========================
    # Wallet (HQ shell)
    # =========================
    path("wallet/", views.wallet_home, name="wallet"),

    # ==================================================================
    # Subscription Admin Actions (used by HQ Subscriptions table buttons)
    #  - Provide endpoints for both UUID and INT primary keys.
    #  - Provide short aliases so templates can use stable names.
    # ==================================================================

    # ---- Extend trial / dates ----
    path("subscriptions/<uuid:pk>/extend/", views.sub_extend, name="sub_extend"),
    path("subscriptions/<int:pk>/extend/",  views.sub_extend, name="sub_extend_int"),

    # ---- Revoke trial (or pause) ----
    path("subscriptions/<uuid:pk>/revoke/", views.sub_revoke_trial, name="sub_revoke_trial"),
    path("subscriptions/<int:pk>/revoke/",  views.sub_revoke_trial, name="sub_revoke_trial_int"),
    # Friendly alias (same view) for templates that expect 'sub_revoke'
    path("subscriptions/<uuid:pk>/revoke-now/", views.sub_revoke_trial, name="sub_revoke"),
    path("subscriptions/<int:pk>/revoke-now/",  views.sub_revoke_trial, name="sub_revoke_int"),

    # ---- Activate immediately ----
    path("subscriptions/<uuid:pk>/activate-now/", views.sub_activate_now, name="sub_activate_now"),
    path("subscriptions/<int:pk>/activate-now/",  views.sub_activate_now, name="sub_activate_now_int"),
    # Friendly alias
    path("subscriptions/<uuid:pk>/activate/", views.sub_activate_now, name="sub_activate"),
    path("subscriptions/<int:pk>/activate/",  views.sub_activate_now, name="sub_activate_int"),

    # ---- Change / set plan ----
    path("subscriptions/<uuid:pk>/set-plan/", views.sub_set_plan, name="sub_set_plan"),
    path("subscriptions/<int:pk>/set-plan/",  views.sub_set_plan, name="sub_set_plan_int"),

    # =========================
    # Invoice actions
    # =========================
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),

    # =========================
    # Trial adjustment / cancel (INT pk in your codebase)
    # =========================
    path("subscriptions/<int:pk>/adjust-trial/", views.sub_adjust_trial, name="sub_adjust_trial"),
    path("subscriptions/<int:pk>/cancel/",       views.sub_cancel,       name="sub_cancel"),

    # =========================
    # Business Directory API endpoints and actions
    # =========================
    path("api/business-search/", v.business_search_api, name="business_search_api"),
    path("businesses/<int:business_id>/quick-action/", v.quick_action, name="quick_action"),
]

# Conditionally add optional routes
if views_currency_settings is not None:
    urlpatterns.append(
        path("settings/currency/", views_currency_settings.currency_settings, name="currency_settings"),
    )

if views_business_detail is not None:
    urlpatterns.extend([
        path("businesses/<int:business_id>/command-center/", views_business_detail.business_command_center, name="business_command_center"),
        path("businesses/<int:business_id>/add-note/", views_business_detail.add_business_note, name="add_business_note"),
    ])

if views_account_support is not None:
    urlpatterns.extend([
        path("businesses/<int:business_id>/account-support/", views_account_support.account_support_home, name="account_support"),
        path("businesses/<int:business_id>/users/<int:user_id>/force-logout/", views_account_support.force_logout_user, name="force_logout_user"),
        path("businesses/<int:business_id>/users/<int:user_id>/unlock/", views_account_support.unlock_account, name="unlock_account"),
        path("businesses/<int:business_id>/users/<int:user_id>/reset-password/", views_account_support.reset_password_for_user, name="reset_password_for_user"),
        path("businesses/<int:business_id>/users/<int:user_id>/resend-otp/", views_account_support.resend_otp, name="resend_otp"),
        path("businesses/<int:business_id>/users/<int:user_id>/sessions/", views_account_support.user_sessions, name="user_sessions"),
    ])

if views_contracts is not None:
    urlpatterns.extend([
        path("contracts/", views_contracts.contracts_list, name="contracts_list"),
        path("contracts/template/", views_contracts.contract_template, name="contract_template"),
        path("contracts/<int:business_id>/", views_contracts.contracts_detail, name="contracts_detail"),
        path("contracts/<int:contract_id>/download/", views_contracts.contract_download, name="contract_download"),
        path("contracts/<int:contract_id>/delete/", views_contracts.contract_delete, name="contract_delete"),
    ])
