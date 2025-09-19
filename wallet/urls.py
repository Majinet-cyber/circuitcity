# wallet/urls.py
from django.urls import path
from django.http import JsonResponse
from . import views

# Namespace for reverse lookups (e.g., {% url 'wallet:agent_wallet' %})
app_name = "wallet"

urlpatterns = [
    # ------------------------------------------------------------------
    # JSON API Endpoints (used by wallet UI, dashboards, and charts)
    # ------------------------------------------------------------------
    path(
        "api/txn-types/",
        views.api_txn_types,
        name="api_txn_types",
    ),
    path(
        "api/summary/",
        views.api_summary,
        name="api_summary",
    ),
    path(
        "api/add-txn/",
        views.api_add_txn,
        name="api_add_txn",
    ),
    path(
        "api/ranking/",
        views.api_ranking,
        name="api_ranking",
    ),

    # ------------------------------------------------------------------
    # Agent Self-Service Pages
    # ------------------------------------------------------------------
    path(
        "",
        views.AgentWalletView.as_view(),
        name="agent_wallet",
    ),
    path(
        "transactions/",
        views.AgentTxnListView.as_view(),
        name="agent_txns",
    ),

    # ------------------------------------------------------------------
    # Admin / Manager Wallet Pages and Budget Management
    # ------------------------------------------------------------------
    path(
        "admin/",
        views.AdminWalletHome.as_view(),
        name="admin_home",
    ),
    path(
        "admin/agent/<int:agent_id>/",
        views.AdminAgentWallet.as_view(),
        name="admin_agent",
    ),
    path(
        "admin/issue/",
        views.AdminIssueTxnView.as_view(),
        name="admin_issue",
    ),
    path(
        "admin/budgets/",
        views.AdminBudgetsView.as_view(),
        name="admin_budgets",
    ),

    # ------------------------------------------------------------------
    # Payslip Management (single issue, bulk issue, and history)
    # ------------------------------------------------------------------
    path(
        "admin/payslip/issue/",
        views.AdminIssuePayslipView.as_view(),
        name="admin_issue_payslip",
    ),
    path(
        "admin/payslip/<int:agent_id>/<int:year>/<int:month>/",
        views.issue_payslip,
        name="issue_payslip",
    ),
    path(
        "admin/payslips/",
        views.AdminPayslipBulkView.as_view(),
        name="admin_payslips",
    ),

    # ------------------------------------------------------------------
    # Payout Schedules (auto or manual runs)
    # ------------------------------------------------------------------
    path(
        "admin/schedules/",
        views.AdminPayoutSchedulesView.as_view(),
        name="admin_schedules",
    ),
    path(
        "admin/schedules/<int:schedule_id>/run/",
        views.run_payout_schedule,
        name="run_schedule",
    ),

    # ------------------------------------------------------------------
    # Admin Purchase Orders (PO management: list, new, detail)
    # ------------------------------------------------------------------
    path(
        "admin/pos/",
        views.AdminPOListView.as_view(),
        name="admin_pos",
    ),
    path(
        "admin/pos/new/",
        views.admin_po_new,
        name="admin_po_new",
    ),
    path(
        "admin/pos/<int:po_id>/",
        views.admin_po_detail,
        name="admin_po_detail",
    ),

    # ------------------------------------------------------------------
    # Healthcheck Endpoint (used by probes/monitoring)
    # ------------------------------------------------------------------
    path(
        "healthz/",
        lambda r: JsonResponse({"ok": True}),
        name="healthz",
    ),
]
