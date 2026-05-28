"""
Sales / Underwriter app views.

Provides the clean /sales/ routing layer on top of existing approvals logic.
All review-step business logic lives in approvals.views; this module adds the
clean URL surface and enriched context for the polished sales UI.
"""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import underwriter_required
from applications.models import FinancingApplication
from approvals.models import UnderwriterReview
from approvals.views import (
    MAX_ACTIVE,
    bool_from_post,
    cancel_application_commissions,
    correction_context,
    get_review,
    process_application_approval,
    review_guard,
    sync_legacy_corrections,
)
from commissions.models import Commission
from contracts.models import Contract
from core.models import AuditLog, QueueRule
from earnings.models import ManagerPayout, MerchantPayout, Wallet, WalletTransaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _queue_rule():
    return QueueRule.for_country("MW")


def _cooldown_state(user):
    """Return (cooldown_remaining_seconds, can_claim_now) for the given user."""
    rule = _queue_rule()
    active_count = FinancingApplication.objects.filter(
        claimed_by=user, status="under_review"
    ).count()

    if active_count >= rule.max_active_applications:
        return 0, False

    last_claim = (
        FinancingApplication.objects.filter(claimed_by=user)
        .exclude(claimed_at=None)
        .order_by("-claimed_at")
        .first()
    )
    if last_claim and last_claim.claimed_at:
        elapsed = (timezone.now() - last_claim.claimed_at).total_seconds()
        cooldown_seconds = rule.cooldown_minutes * 60
        remaining = max(0, cooldown_seconds - elapsed)
        if remaining > 0:
            return remaining, False

    return 0, True


def _audit(user, action, obj_type="", obj_id="", detail=None, request=None):
    ip = None
    if request:
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(
        user=user,
        action=action,
        object_type=obj_type,
        object_id=str(obj_id),
        detail=detail or {},
        ip_address=ip,
    )


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@underwriter_required
def sales_home(request):
    rule = _queue_rule()
    active_apps = FinancingApplication.objects.filter(
        claimed_by=request.user, status="under_review"
    ).select_related("deal", "created_by").order_by("-claimed_at")
    active_count = active_apps.count()

    pending_count = FinancingApplication.objects.filter(
        status="pending_review", claimed_by__isnull=True
    ).count()

    completed_count = FinancingApplication.objects.filter(
        reviewed_by=request.user,
        status__in=["approved", "completed", "contract_complete"],
    ).count()
    rejected_count = FinancingApplication.objects.filter(
        reviewed_by=request.user, status="rejected"
    ).count()
    reviewed_count = completed_count + rejected_count

    cooldown_remaining, can_claim = _cooldown_state(request.user)

    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    return render(request, "sales/home.html", {
        "page_heading": "Home",
        "active_apps": active_apps[:5],
        "active_count": active_count,
        "max_active": rule.max_active_applications,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "reviewed_count": reviewed_count,
        "cooldown_remaining": int(cooldown_remaining),
        "can_claim": can_claim and pending_count > 0,
        "queue_rule": rule,
        "wallet": wallet,
    })


@underwriter_required
def sales_queue_status(request):
    """JSON polling endpoint — used by Alpine.js every N seconds."""
    rule = _queue_rule()
    active_count = FinancingApplication.objects.filter(
        claimed_by=request.user, status="under_review"
    ).count()
    pending_count = FinancingApplication.objects.filter(
        status="pending_review", claimed_by__isnull=True
    ).count()
    cooldown_remaining, can_claim = _cooldown_state(request.user)
    return JsonResponse({
        "active_count": active_count,
        "max_active": rule.max_active_applications,
        "pending_count": pending_count,
        "cooldown_remaining": int(cooldown_remaining),
        "can_claim": can_claim and pending_count > 0,
    })


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@underwriter_required
@require_POST
def sales_claim_next(request):
    rule = _queue_rule()
    active_count = FinancingApplication.objects.filter(
        claimed_by=request.user, status="under_review"
    ).count()

    if active_count >= rule.max_active_applications:
        messages.error(request, f"You already have {active_count} active applications. Complete one before claiming more.")
        return redirect("sales_home")

    _, can_claim = _cooldown_state(request.user)
    if not can_claim:
        messages.error(request, "Please wait before claiming another application.")
        return redirect("sales_home")

    with transaction.atomic():
        app = (
            FinancingApplication.objects.select_for_update()
            .filter(status="pending_review", claimed_by__isnull=True)
            .order_by("submitted_at", "id")
            .first()
        )
        if not app:
            messages.info(request, "No applications pending in the queue.")
            return redirect("sales_home")
        app.claimed_by = request.user
        app.claimed_at = timezone.now()
        app.status = "under_review"
        app.review_status = "under_review"
        app.save(update_fields=["claimed_by", "claimed_at", "status", "review_status"])

    _audit(request.user, AuditLog.ACTION_CLAIM, "FinancingApplication", app.id,
           {"application_number": app.application_number}, request)
    messages.success(request, f"Application {app.application_number} claimed.")
    return redirect("sales_review_summary", app_id=app.id)


# ---------------------------------------------------------------------------
# Applications list
# ---------------------------------------------------------------------------

@underwriter_required
def sales_applications(request):
    tab = request.GET.get("tab", "active")
    if tab == "completed":
        apps = FinancingApplication.objects.filter(
            reviewed_by=request.user,
            status__in=["approved", "completed", "contract_complete"],
        ).order_by("-reviewed_at")
    elif tab == "rejected":
        apps = FinancingApplication.objects.filter(
            reviewed_by=request.user, status="rejected"
        ).order_by("-reviewed_at")
    elif tab == "queue":
        apps = FinancingApplication.objects.filter(
            status="pending_review", claimed_by__isnull=True
        ).order_by("submitted_at", "id")
    else:
        apps = FinancingApplication.objects.filter(
            claimed_by=request.user, status="under_review"
        ).order_by("-claimed_at")
        tab = "active"

    return render(request, "sales/applications_list.html", {
        "page_heading": "Applications",
        "apps": apps.select_related("deal", "created_by")[:50],
        "tab": tab,
    })


# ---------------------------------------------------------------------------
# Review steps (new templates, same business logic as approvals.views)
# ---------------------------------------------------------------------------

@underwriter_required
def sales_review_summary(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)
    if request.method == "POST":
        review.summary_clear = bool_from_post(request, "summary_clear")
        review.save(update_fields=["summary_clear", "updated_at"])
        return redirect("sales_identity_check", app_id=app.id)
    return render(request, "sales/review_summary.html", {
        "page_heading": "Review Application",
        "app": app, "review": review, "step": 1, "total_steps": 6,
        **correction_context(app),
    })


@underwriter_required
def sales_identity_check(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)
    if request.method == "POST":
        review.identity_signature_matches = bool_from_post(request, "identity_signature_matches")
        review.identity_info_matches = bool_from_post(request, "identity_info_matches")
        review.save(update_fields=["identity_signature_matches", "identity_info_matches", "updated_at"])
        return redirect("sales_address_check", app_id=app.id)
    return render(request, "sales/identity_check.html", {
        "page_heading": "Identity Check",
        "app": app, "review": review, "step": 2, "total_steps": 6,
        **correction_context(app),
    })


@underwriter_required
def sales_address_check(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)
    fields = ["location_neighbour_spoken", "location_confirmed", "location_traceable"]
    if request.method == "POST":
        for field in fields:
            setattr(review, field, bool_from_post(request, field))
        review.save(update_fields=[*fields, "updated_at"])
        app.address_check_answers = {
            "spoke_to_neighbour": review.location_neighbour_spoken,
            "neighbour_confirmed_location": review.location_confirmed,
            "can_locate_if_defaulted": review.location_traceable,
        }
        app.save(update_fields=["address_check_answers"])
        return redirect("sales_customer_call", app_id=app.id)
    return render(request, "sales/address_check.html", {
        "page_heading": "Address Check",
        "app": app, "review": review, "step": 3, "total_steps": 6,
        **correction_context(app),
    })


@underwriter_required
def sales_customer_call(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)
    call_fields = [
        "customer_spoken",
        "customer_intro_done",
        "customer_confirmed_application",
        "customer_confirmed_device",
        "customer_confirmed_deposit",
        "customer_confirmed_repayment",
        "customer_understands_direct_payment",
        "customer_understands_nonpayment",
    ]
    if request.method == "POST":
        for field in call_fields:
            setattr(review, field, bool_from_post(request, field))
        review.save(update_fields=[*call_fields, "updated_at"])
        return redirect("sales_income_check", app_id=app.id)
    return render(request, "sales/customer_call.html", {
        "page_heading": "Customer Call",
        "app": app, "review": review, "step": 4, "total_steps": 6,
        **correction_context(app),
    })


@underwriter_required
def sales_income_check(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)
    income_fields = [
        "income_understood",
        "income_contact_spoken",
        "income_confirmed",
        "income_source_dependable",
        "income_contact_confident",
    ]
    monthly_income = Decimal(app.exact_monthly_income or app.monthly_income or 0)
    monthly_payment = Decimal(app.calculated_monthly_payment or 0)
    recommended_income = monthly_payment * Decimal("10")
    income_multiple = (monthly_income / monthly_payment).quantize(Decimal("0.1")) if monthly_payment else Decimal("0")
    if request.method == "POST":
        for field in income_fields:
            setattr(review, field, bool_from_post(request, field))
        review.save(update_fields=[*income_fields, "updated_at"])
        return redirect("sales_final_review", app_id=app.id)
    return render(request, "sales/income_check.html", {
        "page_heading": "Income Check",
        "app": app,
        "review": review,
        "step": 5,
        "total_steps": 6,
        "monthly_income": monthly_income,
        "monthly_payment": monthly_payment,
        "recommended_income": recommended_income,
        "income_multiple": income_multiple,
        **correction_context(app),
    })


@underwriter_required
def sales_final_review(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    review = get_review(app, request.user)

    if request.method == "POST":
        decision = request.POST.get("decision")
        review.comment = request.POST.get("manager_comment", "")
        review.save(update_fields=["comment", "updated_at"])
        app.manager_comment = review.comment
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()

        if decision == "approve":
            return redirect("sales_confirm_approve", app_id=app.id)

        if decision == "reject":
            reject_reason = request.POST.get("reject_reason", "").strip()
            if not reject_reason:
                messages.error(request, "A rejection reason is required.")
                return redirect("sales_final_review", app_id=app.id)
            app.status = "rejected"
            app.review_status = "rejected"
            app.manager_comment = reject_reason
            cancel_application_commissions(app)
            app.save(update_fields=["status", "review_status", "manager_comment", "reviewed_by", "reviewed_at"])
            _audit(request.user, AuditLog.ACTION_REJECT, "FinancingApplication", app.id,
                   {"reason": reject_reason}, request)
            messages.error(request, "Application rejected.")
            return render(request, "sales/reject_success.html", {"app": app, "page_heading": "Rejected"})

        if decision == "request_correction":
            if not app.corrections.filter(resolved=False).exists() and not review.comment.strip():
                messages.error(request, "Mark at least one correction or add a comment before sending back.")
                return redirect("sales_final_review", app_id=app.id)
            app.status = "sent_back"
            app.review_status = "sent_back"
            sync_legacy_corrections(app)
            app.save(update_fields=["status", "review_status", "manager_comment", "reviewed_by", "reviewed_at"])
            messages.success(request, "Application sent back for corrections.")
            return redirect("sales_home")

    score = review.completeness_score()
    score_class = "score-green" if score >= 80 else "score-orange" if score >= 50 else "score-red"
    return render(request, "sales/final_review.html", {
        "page_heading": "Final Review",
        "app": app,
        "review": review,
        "score": score,
        "score_class": score_class,
        "step": 6,
        "total_steps": 6,
        **correction_context(app),
    })


@underwriter_required
def sales_confirm_approve(request, app_id):
    app, response = review_guard(request, app_id)
    if response:
        return response
    if request.method == "POST":
        app.status = "approved"
        app.review_status = "approved"
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()
        app.correction_fields = []
        app.correction_notes = ""
        app.save(update_fields=[
            "status", "review_status", "reviewed_by", "reviewed_at",
            "correction_fields", "correction_notes",
        ])
        app.corrections.filter(resolved=False).update(resolved=True)
        process_application_approval(app, approved_by=request.user)
        _audit(request.user, AuditLog.ACTION_APPROVE, "FinancingApplication", app.id,
               {"application_number": app.application_number}, request)
        return render(request, "sales/approve_success.html", {"app": app, "page_heading": "Approved"})
    return render(request, "sales/confirm_approve.html", {"app": app, "page_heading": "Confirm Approve"})


# ---------------------------------------------------------------------------
# Queue rules
# ---------------------------------------------------------------------------

@underwriter_required
def sales_queue_rules(request):
    rule = _queue_rule()
    return render(request, "sales/queue_rules.html", {"rule": rule, "page_heading": "Queue Rules"})


# ---------------------------------------------------------------------------
# Wallet / Earnings
# ---------------------------------------------------------------------------

@underwriter_required
def sales_wallet(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()[:50]

    tx_type_labels = {
        "commission_credit": "Commission Credit",
        "commission": "Commission Credit",
        "manual_credit": "Manual Credit",
        "payout": "Payout",
        "wallet_payout": "Payout",
        "payout_debit": "Payout",
        "tax": "WHT Deduction",
        "wht_deduction": "WHT Deduction",
        "arrears_deduction": "Arrears Deduction",
        "adjustment": "Adjustment",
        "bonus": "Manual Credit",
        "spin_reward": "Spin Reward",
    }
    transaction_rows = [
        {
            "created_at": tx.created_at,
            "type_label": tx_type_labels.get(tx.transaction_type, tx.get_transaction_type_display()),
            "contract_number": tx.contract_number,
            "amount": tx.amount,
            "is_credit": tx.amount >= 0,
        }
        for tx in transactions
    ]

    # Monthly payout records with WHT breakdown
    payout_records = list(
        ManagerPayout.objects.filter(wallet=wallet).order_by("-period_end")[:12]
    )

    active_tab = request.GET.get("tab", "earnings")

    return render(request, "sales/wallet.html", {
        "page_heading": "Wallet",
        "wallet": wallet,
        "transaction_rows": transaction_rows,
        "payout_records": payout_records,
        "active_tab": active_tab,
    })
