"""
Auto-approval engine for TengaSale financing applications.

Rules are evaluated in order; any blocking rule prevents approval.
Non-blocking rules produce warnings only.
"""
from django.utils import timezone


def _check_duplicate_national_id(app):
    """Return active contracts with same National ID (excluding this application)."""
    from portal.models import PaymentContract
    return list(
        PaymentContract.objects.filter(
            customer_national_id=app.national_id,
            status__in=["active", "overdue", "locked"],
        ).exclude(source_application=app)[:5]
    )


def _check_duplicate_phone(app):
    """Return active contracts with same customer phone."""
    from portal.models import PaymentContract
    if not app.customer_phone:
        return []
    return list(
        PaymentContract.objects.filter(
            customer_phone__endswith=app.customer_phone[-6:],
            status__in=["active", "overdue", "locked"],
        ).exclude(source_application=app)[:5]
    )


def _kyc_complete(app):
    """Check that all required KYC images are uploaded."""
    return bool(app.customer_face_image and app.id_front_image and app.id_back_image)


def _required_fields_complete(app):
    """Check minimum required fields."""
    required = [
        app.customer_name,
        app.national_id,
        app.customer_phone,
        app.deal_id,
    ]
    return all(required)


def _affordability_acceptable(app):
    """Basic affordability: monthly payment should not exceed 40% of declared income."""
    if not app.exact_monthly_income or app.exact_monthly_income <= 0:
        return False
    if not app.calculated_monthly_payment or app.calculated_monthly_payment <= 0:
        return True  # no repayment computed yet — not a blocker
    ratio = app.calculated_monthly_payment / app.exact_monthly_income
    return ratio <= 0.40


def _deal_is_active(app):
    if not app.deal_id:
        return False
    return app.deal.is_active


def _no_fraud_flags(app):
    """Check fraud flags from risk app if available."""
    try:
        from risk.models import FraudCheck
        flags = FraudCheck.objects.filter(application=app, is_flagged=True).exists()
        return not flags
    except Exception:
        return True  # if risk app not available, don't block


def evaluate_auto_approval(app):
    """
    Evaluate whether an application is eligible for auto-approval.

    Returns a dict:
        eligible (bool): True if all blocking rules pass
        reasons (list[str]): Why it IS eligible (passed checks)
        blocks (list[str]): Why it is NOT eligible (failed blocking checks)
        warnings (list[str]): Non-blocking concerns
    """
    blocks = []
    reasons = []
    warnings = []

    # ── Blocking rules ──────────────────────────────────────────────────────

    if not _required_fields_complete(app):
        blocks.append("Required fields incomplete (name, national ID, phone, deal).")
    else:
        reasons.append("Required fields complete.")

    if not app.national_id:
        blocks.append("National ID is missing.")
    else:
        dup_id = _check_duplicate_national_id(app)
        if dup_id:
            blocks.append(
                f"National ID {app.national_id} already has {len(dup_id)} active contract(s)."
            )
        else:
            reasons.append("No duplicate national ID with active contracts.")

    dup_phone = _check_duplicate_phone(app)
    if dup_phone:
        blocks.append(
            f"Phone number already linked to {len(dup_phone)} active contract(s)."
        )
    else:
        reasons.append("No duplicate phone with active contracts.")

    if not _kyc_complete(app):
        blocks.append("KYC documents incomplete (face / ID front / ID back).")
    else:
        reasons.append("KYC documents uploaded.")

    if not _deal_is_active(app):
        blocks.append("Selected device deal is not active or not set.")
    else:
        reasons.append("Device deal is active.")

    if not _no_fraud_flags(app):
        blocks.append("Application has active fraud flags.")
    else:
        reasons.append("No fraud flags.")

    # ── Application-level duplicate check ──────────────────────────────────
    try:
        from applications.services.duplicate_check import check_duplicate_customer
        dup = check_duplicate_customer(app)
        if dup["active_contract_risk"]:
            blocks.append("Customer has an existing active/pending financing application.")
        elif dup["has_duplicates"]:
            warnings.append(f"Duplicate signals detected: {', '.join(f['type'] for f in dup['flags'])}")
    except Exception:
        pass

    if not app.agreed_to_terms:
        blocks.append("Customer has not agreed to terms.")
    else:
        reasons.append("Terms agreed.")

    # ── Non-blocking warnings ───────────────────────────────────────────────

    if not _affordability_acceptable(app):
        warnings.append("Monthly repayment may exceed 40% of declared income.")
    else:
        reasons.append("Affordability check passed.")

    if not app.exact_monthly_income:
        warnings.append("No declared monthly income provided.")

    if app.third_party_phone_user_risk_flagged:
        warnings.append("Phone will be used by a third party.")

    eligible = len(blocks) == 0
    return {
        "eligible": eligible,
        "reasons": reasons,
        "blocks": blocks,
        "warnings": warnings,
    }


def get_auto_approval_reasons(app):
    """Convenience wrapper — returns full evaluation dict."""
    return evaluate_auto_approval(app)


def auto_approve_application(app, approved_by=None):
    """
    Auto-approve an application that has passed all eligibility checks.
    Sets status to 'approved', records reviewed_by and reviewed_at.
    Creates an AuditLog entry.
    Does NOT silently approve — caller must evaluate first.
    """
    from core.models import AuditLog

    if app.status not in ("pending_review", "submitted", "resubmitted"):
        raise ValueError(
            f"Cannot auto-approve application in status '{app.status}'."
        )

    app.status = "approved"
    app.review_status = "approved"
    app.reviewed_by = approved_by
    app.reviewed_at = timezone.now()
    app.save(update_fields=["status", "review_status", "reviewed_by", "reviewed_at"])

    AuditLog.objects.create(
        user=approved_by,
        action="hq_auto_approve",
        object_type="FinancingApplication",
        object_id=str(app.pk),
        detail={
            "app": app.application_number,
            "auto": True,
        },
    )
    return app
