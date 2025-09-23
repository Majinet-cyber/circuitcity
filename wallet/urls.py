# wallet/urls.py
from django.urls import path
from django.views.generic import RedirectView
from django.http import JsonResponse
from . import views

app_name = "wallet"

urlpatterns = [
    # ------------------------------------------------------------------
    # JSON API Endpoints
    # ------------------------------------------------------------------
    path("api/txn-types/", views.api_txn_types, name="api_txn_types"),
    path("api/summary/",   views.api_summary,   name="api_summary"),
    path("api/add-txn/",   views.api_add_txn,   name="api_add_txn"),
    path("api/ranking/",   views.api_ranking,   name="api_ranking"),

    # ------------------------------------------------------------------
    # Agent Pages (default landing for non-staff)
    # ------------------------------------------------------------------
    path("",              views.AgentWalletView.as_view(),  name="agent_wallet"),
    path("transactions/", views.AgentTxnListView.as_view(), name="agent_txns"),

    # ------------------------------------------------------------------
    # Wallet Admin Pages (canonical: /wallet/admin/...)
    # ------------------------------------------------------------------
    path("admin/", views.AdminWalletHome.as_view(), name="admin_home"),
    path("admin/agent/<int:agent_id>/", views.AdminAgentWallet.as_view(), name="admin_agent"),
    path("admin/issue/", views.AdminIssueTxnView.as_view(), name="admin_issue"),
    path("admin/budgets/", views.AdminBudgetsView.as_view(), name="admin_budgets"),

    # Payslips
    path("admin/payslips/", views.AdminPayslipBulkView.as_view(), name="admin_payslips"),
    path("admin/payslips/single/", views.AdminIssuePayslipView.as_view(), name="admin_issue_payslip"),
    path("admin/payslip/<int:agent_id>/<int:year>/<int:month>/", views.issue_payslip, name="issue_payslip"),

    # Payout Schedules
    path("admin/schedules/", views.AdminPayoutSchedulesView.as_view(), name="admin_schedules"),
    path("admin/schedules/<int:schedule_id>/run/", views.run_payout_schedule, name="run_schedule"),

    # Purchase Orders
    path("admin/pos/", views.AdminPOListView.as_view(), name="admin_pos"),
    path("admin/pos/new/", views.admin_po_new, name="admin_po_new"),
    path("admin/pos/<int:po_id>/", views.admin_po_detail, name="admin_po_detail"),

    # ------------------------------------------------------------------
    # Legacy dashed-path compatibility → redirect to new canonical routes
    # ------------------------------------------------------------------
    path("admin-home/", RedirectView.as_view(pattern_name="wallet:admin_home", permanent=False)),
    path("admin-agent/<int:agent_id>/", RedirectView.as_view(pattern_name="wallet:admin_agent", permanent=False)),
    path("admin-issue/", RedirectView.as_view(pattern_name="wallet:admin_issue", permanent=False)),
    path("admin-budgets/", RedirectView.as_view(pattern_name="wallet:admin_budgets", permanent=False)),
    path("admin-payslips/", RedirectView.as_view(pattern_name="wallet:admin_payslips", permanent=False)),
    path("admin-payslip/issue/", RedirectView.as_view(pattern_name="wallet:admin_issue_payslip", permanent=False)),
    path("admin-schedules/", RedirectView.as_view(pattern_name="wallet:admin_schedules", permanent=False)),
    path("admin-pos/", RedirectView.as_view(pattern_name="wallet:admin_pos", permanent=False)),
    path("admin-pos/new/", RedirectView.as_view(pattern_name="wallet:admin_po_new", permanent=False)),
    path("admin-pos/<int:po_id>/", RedirectView.as_view(pattern_name="wallet:admin_po_detail", permanent=False)),

    # Convenience alias (without trailing slash → redirects to admin_home)
    path("admin", RedirectView.as_view(pattern_name="wallet:admin_home", permanent=False)),

    # ------------------------------------------------------------------
    # Healthcheck
    # ------------------------------------------------------------------
    path("healthz/", lambda r: JsonResponse({"ok": True}), name="healthz"),
]
