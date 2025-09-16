# wallet/urls.py
from __future__ import annotations

from types import SimpleNamespace
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

# ----------------------------------------------------------------------
# Optional guards (fallback to no-ops if not available)
# ----------------------------------------------------------------------
try:
    from core.decorators import manager_required  # "manager/staff only"
except Exception:  # pragma: no cover
    def manager_required(view_func):
        return view_func

try:
    from accounts.decorators import otp_required  # 2FA gate
except Exception:  # pragma: no cover
    def otp_required(view_func):
        return view_func

# ----------------------------------------------------------------------
# Import views defensively; don't let missing imports break urlconf
# ----------------------------------------------------------------------
try:
    from . import views as _views
except Exception:  # pragma: no cover
    _views = SimpleNamespace()

# Namespacing for {% url 'wallet:...' %} to work everywhere
app_name = "wallet"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _stub_json(msg: str, status: int = 501):
    """Return a tiny JSON stub view (used when a view isn't implemented yet)."""
    @never_cache
    @require_GET
    def _view(_request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=status)
    return _view


def _get(name: str, msg: str | None = None):
    """Safely fetch a callable/class from views; return a JSON stub if missing."""
    fn = getattr(_views, name, None)
    if callable(fn):
        return fn
    return _stub_json(msg or f"{name} not implemented")


def _viewish(v):
    """Accept either a function view or a CBV, and return a function view."""
    # Class-based views expose .as_view(); functions don't.
    return v.as_view() if hasattr(v, "as_view") else v


# ----------------------------------------------------------------------
# Resolve views (functions or CBVs), falling back to stubs when absent
# ----------------------------------------------------------------------
# JSON APIs
api_txn_types = _get("api_txn_types", "api_txn_types not implemented")
api_summary   = _get("api_summary",   "api_summary not implemented")
api_add_txn   = _get("api_add_txn",   "api_add_txn not implemented")
api_ranking   = _get("api_ranking",   "api_ranking not implemented")

# Agent pages
AgentWalletView  = _get("AgentWalletView",  "AgentWalletView not implemented")
AgentTxnListView = _get("AgentTxnListView", "AgentTxnListView not implemented")

# (Optional) Agent budgets
AgentBudgetListView    = _get("AgentBudgetListView",    "AgentBudgetListView not implemented")
AgentBudgetCreateView  = _get("AgentBudgetCreateView",  "AgentBudgetCreateView not implemented")
AgentBudgetDetailView  = _get("AgentBudgetDetailView",  "AgentBudgetDetailView not implemented")

# Admin / Manager pages
AdminWalletHome           = _get("AdminWalletHome",           "AdminWalletHome not implemented")
AdminAgentWallet          = _get("AdminAgentWallet",          "AdminAgentWallet not implemented")
AdminIssueTxnView         = _get("AdminIssueTxnView",         "AdminIssueTxnView not implemented")
AdminBudgetsView          = _get("AdminBudgetsView",          "AdminBudgetsView not implemented")
AdminIssuePayslipView     = _get("AdminIssuePayslipView",     "AdminIssuePayslipView not implemented")
issue_payslip             = _get("issue_payslip",             "issue_payslip not implemented")
AdminPayslipBulkView      = _get("AdminPayslipBulkView",      "AdminPayslipBulkView not implemented")
AdminPayoutSchedulesView  = _get("AdminPayoutSchedulesView",  "AdminPayoutSchedulesView not implemented")
run_payout_schedule       = _get("run_payout_schedule",       "run_payout_schedule not implemented")
AdminPOListView           = _get("AdminPOListView",           "AdminPOListView not implemented")
admin_po_new              = _get("admin_po_new",              "admin_po_new not implemented")
admin_po_detail           = _get("admin_po_detail",           "admin_po_detail not implemented")


# ----------------------------------------------------------------------
# URL patterns
# ----------------------------------------------------------------------
urlpatterns = [
    # ------------------------------
    # JSON APIs (GET; never cached)
    # ------------------------------
    path("api/txn-types/", never_cache(require_GET(_viewish(api_txn_types))), name="api_txn_types"),
    path("api/summary/",   never_cache(require_GET(_viewish(api_summary))),   name="api_summary"),
    path("api/add-txn/",   never_cache(require_GET(_viewish(api_add_txn))),   name="api_add_txn"),

    # Keep historical name but offer a proper /api/ alias too
    path("ranking/",       never_cache(require_GET(_viewish(api_ranking))),   name="api_ranking"),
    path("api/ranking/",   never_cache(require_GET(_viewish(api_ranking))),   name="api_ranking_api"),

    # ------------------------------
    # Agent (self-service)
    # ------------------------------
    path("",              _viewish(AgentWalletView),  name="agent_wallet"),
    path("transactions/", _viewish(AgentTxnListView), name="agent_txns"),

    # (Uncomment when budgets are implemented)
    # path("budgets/",             _viewish(AgentBudgetListView),   name="agent_budgets"),
    # path("budgets/new/",         _viewish(AgentBudgetCreateView), name="agent_budget_new"),
    # path("budgets/<int:pk>/",    _viewish(AgentBudgetDetailView), name="agent_budget_detail"),

    # ------------------------------
    # Admin / Manager (OTP + role-gated)
    # ------------------------------
    path(
        "admin/",
        manager_required(otp_required(_viewish(AdminWalletHome))),
        name="admin_home",
    ),
    path(
        "admin/agent/<int:agent_id>/",
        manager_required(otp_required(_viewish(AdminAgentWallet))),
        name="admin_agent",
    ),
    path(
        "admin/issue/",
        manager_required(otp_required(_viewish(AdminIssueTxnView))),
        name="admin_issue",
    ),
    path(
        "admin/budgets/",
        manager_required(otp_required(_viewish(AdminBudgetsView))),
        name="admin_budgets",
    ),
    # Payslips (single + bulk)
    path(
        "admin/payslip/issue/",
        manager_required(otp_required(_viewish(AdminIssuePayslipView))),
        name="admin_issue_payslip",
    ),
    path(
        "admin/payslip/issue/<int:agent_id>/<int:year>/<int:month>/",
        manager_required(otp_required(_viewish(issue_payslip))),
        name="issue_payslip",
    ),
    path(
        "admin/payslips/",
        manager_required(otp_required(_viewish(AdminPayslipBulkView))),
        name="admin_payslips",
    ),
    # Payout schedules
    path(
        "admin/schedules/",
        manager_required(otp_required(_viewish(AdminPayoutSchedulesView))),
        name="admin_schedules",
    ),
    path(
        "admin/schedules/<int:schedule_id>/run/",
        manager_required(otp_required(_viewish(run_payout_schedule))),
        name="run_schedule",
    ),
    # Admin Purchase Orders (Place Order flow)
    path(
        "admin/po/",
        manager_required(otp_required(_viewish(AdminPOListView))),
        name="admin_po_list",
    ),
    path(
        "admin/po/new/",
        manager_required(otp_required(_viewish(admin_po_new))),
        name="admin_po_new",
    ),
    path(
        "admin/po/<int:po_id>/",
        manager_required(otp_required(_viewish(admin_po_detail))),
        name="admin_po_detail",
    ),

    # ------------------------------
    # Healthz (simple probe)
    # ------------------------------
    path("healthz/", never_cache(lambda _req: JsonResponse({"ok": True})), name="healthz"),
]
