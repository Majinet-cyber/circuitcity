# wallet/urls.py
from django.urls import path
from . import views

app_name = "wallet"

urlpatterns = [
    # ----- Agent -----
    path("", views.AgentWalletView.as_view(), name="agent_wallet"),
    path("transactions/", views.AgentTxnListView.as_view(), name="agent_txns"),
    path("ranking/", views.api_ranking, name="api_ranking"),
    # path("budget/request/", views.agent_create_budget, name="agent_budget_request"),  # optional

    # ----- Admin -----
    path("admin/", views.AdminWalletHome.as_view(), name="admin_home"),
    path("admin/agent/<int:agent_id>/", views.AdminAgentWallet.as_view(), name="admin_agent"),
    path("admin/issue/", views.AdminIssueTxnView.as_view(), name="admin_issue"),
    path("admin/budgets/", views.AdminBudgetsView.as_view(), name="admin_budgets"),

    # Payslips
    path("admin/payslip/issue/", views.AdminIssuePayslipView.as_view(), name="admin_issue_payslip"),  # single helper page
    path(
        "admin/payslip/issue/<int:agent_id>/<int:year>/<int:month>/",
        views.issue_payslip,
        name="issue_payslip",
    ),
    path("admin/payslips/", views.AdminPayslipBulkView.as_view(), name="admin_payslips"),  # bulk

    # Payout schedules (auto-send monthly)
    path("admin/schedules/", views.AdminPayoutSchedulesView.as_view(), name="admin_schedules"),
    path("admin/schedules/<int:schedule_id>/run/", views.run_payout_schedule, name="run_schedule"),

    # ----- Admin Purchase Orders (NEW) -----
    path("admin/po/", views.AdminPOListView.as_view(), name="admin_po_list"),
    path("admin/po/new/", views.admin_po_new, name="admin_po_new"),
    path("admin/po/<int:po_id>/", views.admin_po_detail, name="admin_po_detail"),
]
