# wallet/urls.py
from django.urls import path
from django.views.generic import RedirectView
from django.http import JsonResponse
from . import views
from . import views_export
from . import views_admin
from . import views_costs
from . import views_cashbank

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
    path("earnings/",     views.agent_earnings,             name="agent_earnings"),
    path("transactions/", views.AgentTxnListView.as_view(), name="agent_txns"),

    # Agent extras (additive)
    path("tx/<int:pk>/", views.entry_detail, name="entry_detail"),  # transaction drill-down
    path("payslip/<int:year>-<int:month>/download/", views.payslip_download, name="payslip_download"),
    path("budget/new/", views.budget_new, name="budget_new"),
    path("export/activity/", views_export.agent_export_activity, name="agent_export_activity"),  # Agent data export

    # ------------------------------------------------------------------
    # Wallet Admin Pages (canonical: /wallet/admin/...)
    # ------------------------------------------------------------------
    path("admin/", views.AdminWalletHome.as_view(), name="admin_home"),
    path("cash-bank/", views_cashbank.cash_statement, name="cash_statement"),
    path("cash-bank/export.csv", views_cashbank.cash_statement_csv, name="cash_statement_csv"),
    path("cash-bank/export.pdf", views_cashbank.cash_statement_pdf, name="cash_statement_pdf"),
    path("admin/agent/<int:agent_id>/", views.AdminAgentWallet.as_view(), name="admin_agent"),
    path("admin/issue/", views.AdminIssueTxnView.as_view(), name="admin_issue"),
    path("admin/budgets/", views.AdminBudgetsView.as_view(), name="admin_budgets"),

    # Payslips
    path("admin/payslips/", views.AdminPayslipBulkView.as_view(), name="admin_payslips"),
    path("admin/payslips/single/", views.AdminIssuePayslipView.as_view(), name="admin_issue_payslip"),
    path("admin/payslips/<int:pk>/download/", views.payslip_download_by_id, name="payslip_download_by_id"),
    path("admin/payslips/<int:pk>/<str:action>/", views.payslip_set_status, name="payslip_set_status"),
    path("admin/payslip/<int:agent_id>/<int:year>/<int:month>/", views.issue_payslip, name="issue_payslip"),

    # Payout Schedules
    path("admin/schedules/", views.AdminPayoutSchedulesView.as_view(), name="admin_schedules"),
    path("admin/schedules/<int:schedule_id>/run/", views.run_payout_schedule, name="run_schedule"),

    # Purchase Orders
    path("admin/pos/", views.AdminPOListView.as_view(), name="admin_pos"),
    path("admin/pos/new/", views.admin_po_new, name="admin_po_new"),
    path("admin/pos/<int:po_id>/", views.admin_po_detail, name="admin_po_detail"),
    path("admin/pos/<int:po_id>/pdf/", views.admin_po_pdf, name="admin_po_pdf"),

    # Cost Management (NEW)
    path("admin/costs/", views_costs.admin_cost_list, name="admin_cost_list"),
    path("admin/costs/", views_costs.admin_cost_list, name="admin_costs"),
    path("admin/costs/", views_costs.admin_cost_list, name="admin_costs_list"),
    path("admin/costs/new/", views_costs.admin_cost_create, name="admin_costs_create"),
    path("admin/costs/<int:cost_id>/edit/", views_costs.admin_cost_edit, name="admin_cost_edit"),
    path("admin/costs/<int:cost_id>/delete/", views_costs.admin_cost_delete, name="admin_costs_delete"),
    path("admin/costs/<int:pk>/update/", views_admin.admin_costs_update, name="admin_costs_update"),
    
    # Agent Wallet Adjustment
    path("admin/agent/<int:membership_id>/adjust/", views.wallet_adjust_agent, name="wallet_adjust_agent"),
    
    # Commission Management
    path("admin/commission/update/", views_admin.update_commission_config, name="update_commission_config"),

    # Admin extras (additive, non-breaking)
    path("admin/requests/", views.admin_budget_list, name="admin_budget_list"),
    path("admin/requests/<int:pk>/set/<str:action>/", views.admin_budget_set_status, name="admin_budget_set_status"),
    path("admin/entries/export.csv", views.admin_entries_export_csv, name="admin_entries_export_csv"),

    # ------------------------------------------------------------------
    # Legacy dashed-path compatibility â†’ redirect to new canonical routes
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

    # Convenience alias (without trailing slash â†’ redirects to admin_home)
    path("admin", RedirectView.as_view(pattern_name="wallet:admin_home", permanent=False)),

    # ------------------------------------------------------------------
    # Healthcheck
    # ------------------------------------------------------------------
    path("healthz/", lambda r: JsonResponse({"ok": True}), name="healthz"),
]


