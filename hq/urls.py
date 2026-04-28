# hq/urls.py
from django.urls import path
from django.views.generic import RedirectView

from . import views
from . import views_business_directory as v

# Bug Monitor and Accounts views (always available)
try:
    from . import views_bugmonitor
except ImportError:
    views_bugmonitor = None

try:
    from . import views_accounts
except ImportError:
    views_accounts = None

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
    path("invoices/", views.invoices, name="invoices"),
    path("agents/", views.agents, name="agents"),
    path("stock-trends/", views.stock_trends, name="stock_trends"),
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
    # Notifications API (support both slash and no-slash)
    path("api/notifications", views.hq_notifications_api, name="hq_notifications_api_noslash"),
    path("api/notifications/", views.hq_notifications_api, name="hq_notifications_api"),
    # =========================
    # Wallet (HQ shell)
    # =========================
    path("wallet/", views.wallet_home, name="wallet"),
    path("wallet/mark-paid/", views.wallet_mark_paid, name="wallet_mark_paid"),
    # ==================================================================
    # Subscription Admin Actions (used by HQ Subscriptions table buttons)
    #  - Provide endpoints for both UUID and INT primary keys.
    #  - Provide short aliases so templates can use stable names.
    # ==================================================================
    # ---- Extend trial / dates ----
    path("subscriptions/<uuid:pk>/extend/", views.sub_extend, name="sub_extend"),
    path("subscriptions/<int:pk>/extend/", views.sub_extend, name="sub_extend_int"),
    # ---- Revoke trial (or pause) ----
    path("subscriptions/<uuid:pk>/revoke/", views.sub_revoke_trial, name="sub_revoke_trial"),
    path("subscriptions/<int:pk>/revoke/", views.sub_revoke_trial, name="sub_revoke_trial_int"),
    # Friendly alias (same view) for templates that expect 'sub_revoke'
    path("subscriptions/<uuid:pk>/revoke-now/", views.sub_revoke_trial, name="sub_revoke"),
    path("subscriptions/<int:pk>/revoke-now/", views.sub_revoke_trial, name="sub_revoke_int"),
    # ---- Activate immediately ----
    path("subscriptions/<uuid:pk>/activate-now/", views.sub_activate_now, name="sub_activate_now"),
    path("subscriptions/<int:pk>/activate-now/", views.sub_activate_now, name="sub_activate_now_int"),
    # Friendly alias
    path("subscriptions/<uuid:pk>/activate/", views.sub_activate_now, name="sub_activate"),
    path("subscriptions/<int:pk>/activate/", views.sub_activate_now, name="sub_activate_int"),
    # ---- Change / set plan ----
    path("subscriptions/<uuid:pk>/set-plan/", views.sub_set_plan, name="sub_set_plan"),
    path("subscriptions/<int:pk>/set-plan/", views.sub_set_plan, name="sub_set_plan_int"),
    # =========================
    # Invoice actions
    # =========================
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),
    path("invoices/create/", views.invoice_create, name="invoice_create"),
    # =========================
    # Trial adjustment / cancel (INT pk in your codebase)
    # =========================
    path("subscriptions/<int:pk>/adjust-trial/", views.sub_adjust_trial, name="sub_adjust_trial"),
    path("subscriptions/<int:pk>/cancel/", views.sub_cancel, name="sub_cancel"),
    # =========================
    # Business Directory API endpoints and actions
    # =========================
    path("api/business-search/", v.business_search_api, name="business_search_api"),
    path("businesses/<int:business_id>/quick-action/", v.quick_action, name="quick_action"),
]

# =========================
# Bug Monitor routes
# =========================
if views_bugmonitor is not None:
    urlpatterns.extend([
        path("bugs/",                  views_bugmonitor.bugs_list,    name="bugs_list"),
        path("bugs/<uuid:pk>/",        views_bugmonitor.bug_detail,   name="bug_detail"),
        path("bugs/<uuid:pk>/action/", views_bugmonitor.bug_action,   name="bug_action"),
        path("bugs/bulk-action/",      views_bugmonitor.bug_bulk_action, name="bug_bulk_action"),
        path("audit/",                 views_bugmonitor.audit_log,    name="audit_log"),
    ])

# =========================
# Accounts management routes
# =========================
if views_accounts is not None:
    urlpatterns.extend([
        path("accounts/",                       views_accounts.accounts_list,          name="accounts_list"),
        path("accounts/<int:user_id>/",         views_accounts.account_detail,         name="account_detail"),
        path("accounts/<int:user_id>/groups/",  views_accounts.account_assign_groups,  name="account_assign_groups"),
        path("accounts/<int:user_id>/toggle/",  views_accounts.account_toggle_active,  name="account_toggle_active"),
    ])

# Conditionally add optional routes
if views_currency_settings is not None:
    urlpatterns.append(
        path("settings/currency/", views_currency_settings.currency_settings, name="currency_settings"),
    )

if views_business_detail is not None:
    urlpatterns.extend(
        [
            path(
                "businesses/<int:business_id>/command-center/",
                views_business_detail.business_command_center,
                name="business_command_center",
            ),
            path(
                "businesses/<int:business_id>/add-note/",
                views_business_detail.add_business_note,
                name="add_business_note",
            ),
        ]
    )

if views_account_support is not None:
    urlpatterns.extend(
        [
            path(
                "businesses/<int:business_id>/account-support/",
                views_account_support.account_support_home,
                name="account_support",
            ),
            path(
                "businesses/<int:business_id>/users/<int:user_id>/force-logout/",
                views_account_support.force_logout_user,
                name="force_logout_user",
            ),
            path(
                "businesses/<int:business_id>/users/<int:user_id>/unlock/",
                views_account_support.unlock_account,
                name="unlock_account",
            ),
            path(
                "businesses/<int:business_id>/users/<int:user_id>/reset-password/",
                views_account_support.reset_password_for_user,
                name="reset_password_for_user",
            ),
            path(
                "businesses/<int:business_id>/users/<int:user_id>/resend-otp/",
                views_account_support.resend_otp,
                name="resend_otp",
            ),
            path(
                "businesses/<int:business_id>/users/<int:user_id>/sessions/",
                views_account_support.user_sessions,
                name="user_sessions",
            ),
        ]
    )

if views_contracts is not None:
    urlpatterns.extend(
        [
            path("contracts/", views_contracts.contracts_list, name="contracts_list"),
            path("contracts/template/", views_contracts.contract_template, name="contract_template"),
            path("contracts/<int:business_id>/", views_contracts.contracts_detail, name="contracts_detail"),
            path("contracts/<int:contract_id>/download/", views_contracts.contract_download, name="contract_download"),
            path("contracts/<int:contract_id>/delete/", views_contracts.contract_delete, name="contract_delete"),
            # HQ Staff Tour Guide
            path("staff/tour-guide/", views_contracts.staff_tour_guide, name="staff_tour_guide"),
            path("staff/tour-guide.pdf", views_contracts.staff_tour_guide_pdf, name="staff_tour_guide_pdf"),
        ]
    )

# ======================================================================================
# URL COMPATIBILITY ALIASES (SSOT)
# Import compatibility URL patterns from cc.urls_compat to ensure consistent naming
# across all URLConfs. This allows tests using reverse('stock'), reverse('sell'), etc.
# to work correctly when HQ URLConf is loaded in test context.
# ======================================================================================
try:
    from cc.urls_compat import get_compat_urlpatterns
    urlpatterns += get_compat_urlpatterns()
except ImportError:
    pass  # If cc.urls_compat not available, skip (shouldn't happen in normal operation)