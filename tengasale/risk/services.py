"""
risk/services.py

Fraud detection and customer exposure service for TengaSale.

Detects duplicate customers by National ID and phone number before
application approval. Returns structured risk results and creates
FraudCheck records.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _hash_national_id(national_id: str) -> str:
    return hashlib.sha256(national_id.strip().upper().encode()).hexdigest()


def _hash_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return hashlib.sha256(digits.encode()).hexdigest()


def find_existing_customer_exposure(
    national_id: Optional[str] = None,
    phone: Optional[str] = None,
    exclude_application_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Search TengaSale data for existing contracts and applications
    matching the given National ID or phone number.

    Returns structured dict with risk assessment and match details.

    Parameters:
        national_id:             Customer National ID (raw string)
        phone:                   Primary phone number
        exclude_application_id:  Exclude this application ID from match results
                                 (so the current application doesn't match itself)
    """
    from applications.models import FinancingApplication
    from portal.models import PaymentContract

    active_contracts: List[Dict] = []
    overdue_contracts: List[Dict] = []
    locked_contracts: List[Dict] = []
    completed_contracts: List[Dict] = []
    pending_applications: List[Dict] = []
    approved_applications: List[Dict] = []
    rejected_applications: List[Dict] = []
    same_id_matches: List[str] = []
    same_phone_matches: List[str] = []

    nid_clean = (national_id or "").strip().upper()
    phone_digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if phone_digits.startswith("265"):
        phone_digits = phone_digits[3:]
    if phone_digits.startswith("0"):
        phone_digits = phone_digits[1:]

    # ── Search PaymentContracts ──────────────────────────────────────────────
    contract_qs = PaymentContract.objects.all()
    if exclude_application_id:
        contract_qs = contract_qs.exclude(source_application_id=exclude_application_id)

    if nid_clean:
        for contract in contract_qs.filter(customer_national_id__iexact=nid_clean):
            entry = _contract_summary(contract, matched_by="national_id")
            same_id_matches.append(contract.contract_number)
            _bucket_contract(entry, contract.status, active_contracts, overdue_contracts,
                             locked_contracts, completed_contracts)

    if phone_digits:
        for contract in contract_qs.filter(customer_phone__endswith=phone_digits):
            # avoid double-counting
            if contract.contract_number not in same_id_matches:
                entry = _contract_summary(contract, matched_by="phone")
                same_phone_matches.append(contract.contract_number)
                _bucket_contract(entry, contract.status, active_contracts, overdue_contracts,
                                 locked_contracts, completed_contracts)

    # ── Search FinancingApplications ─────────────────────────────────────────
    app_qs = FinancingApplication.objects.all()
    if exclude_application_id:
        app_qs = app_qs.exclude(pk=exclude_application_id)

    if nid_clean:
        for app in app_qs.filter(national_id__iexact=nid_clean):
            entry = _app_summary(app, matched_by="national_id")
            _bucket_application(entry, app.status, pending_applications,
                                approved_applications, rejected_applications)

    if phone_digits:
        for app in app_qs.filter(customer_phone__endswith=phone_digits):
            if app.application_number not in [a["application_number"] for a in
                                              pending_applications + approved_applications + rejected_applications]:
                entry = _app_summary(app, matched_by="phone")
                _bucket_application(entry, app.status, pending_applications,
                                    approved_applications, rejected_applications)

    # ── Risk assessment ──────────────────────────────────────────────────────
    risk_level, recommended_action = _assess_risk(
        active_contracts=active_contracts,
        overdue_contracts=overdue_contracts,
        locked_contracts=locked_contracts,
        completed_contracts=completed_contracts,
        rejected_applications=rejected_applications,
    )

    return {
        "active_contracts": active_contracts,
        "overdue_contracts": overdue_contracts,
        "locked_contracts": locked_contracts,
        "completed_contracts": completed_contracts,
        "pending_applications": pending_applications,
        "approved_applications": approved_applications,
        "rejected_applications": rejected_applications,
        "same_id_matches": same_id_matches,
        "same_phone_matches": same_phone_matches,
        "risk_level": risk_level,
        "recommended_action": recommended_action,
        "has_exposure": bool(
            active_contracts or overdue_contracts or locked_contracts
            or pending_applications or approved_applications
        ),
        "total_matches": (
            len(active_contracts) + len(overdue_contracts) + len(locked_contracts)
            + len(completed_contracts) + len(pending_applications)
            + len(approved_applications) + len(rejected_applications)
        ),
    }


def run_fraud_check(application, checked_by=None) -> "risk.models.FraudCheck":
    """
    Run a full fraud/exposure check for the given application and
    save a FraudCheck record. Returns the FraudCheck instance.
    """
    from risk.models import FraudCheck
    from core.models import AuditLog

    result = find_existing_customer_exposure(
        national_id=application.national_id,
        phone=application.customer_phone,
        exclude_application_id=application.pk,
    )

    check = FraudCheck.objects.create(
        application=application,
        national_id_hash=_hash_national_id(application.national_id or ""),
        phone_hash=_hash_phone(application.customer_phone or ""),
        result=result,
        risk_level=result["risk_level"],
        recommended_action=result["recommended_action"],
        checked_by=checked_by,
        resolution_status=FraudCheck.RESOLUTION_OPEN,
    )

    if result["has_exposure"]:
        try:
            AuditLog.objects.create(
                user=checked_by,
                action="hq_fraud_check",
                object_type="FinancingApplication",
                object_id=str(application.pk),
                detail={
                    "risk_level": result["risk_level"],
                    "recommended_action": result["recommended_action"],
                    "total_matches": result["total_matches"],
                    "app": application.application_number,
                },
            )
        except Exception:
            pass

    return check


def can_approve_application(application, requesting_user=None) -> Dict[str, Any]:
    """
    Check whether an application can be approved.

    Returns dict:
        can_approve:     bool
        blocked_reason:  str or None
        fraud_check:     FraudCheck instance or None
        requires_hq:     bool
    """
    from risk.models import FraudCheck

    latest_check = (
        FraudCheck.objects.filter(application=application)
        .order_by("-created_at")
        .first()
    )

    if latest_check is None:
        return {"can_approve": True, "blocked_reason": None, "fraud_check": None, "requires_hq": False}

    if latest_check.resolution_status == FraudCheck.RESOLUTION_HQ_OVERRIDE:
        return {"can_approve": True, "blocked_reason": None, "fraud_check": latest_check, "requires_hq": False}

    if latest_check.resolution_status == FraudCheck.RESOLUTION_BLOCKED:
        return {
            "can_approve": False,
            "blocked_reason": "Application has been blocked by HQ due to fraud/duplicate risk.",
            "fraud_check": latest_check,
            "requires_hq": False,
        }

    if latest_check.risk_level == FraudCheck.RISK_BLOCK:
        return {
            "can_approve": False,
            "blocked_reason": (
                "Approval blocked: customer has an existing active or locked contract. "
                "HQ override is required."
            ),
            "fraud_check": latest_check,
            "requires_hq": True,
        }

    if latest_check.risk_level == FraudCheck.RISK_HIGH:
        return {
            "can_approve": False,
            "blocked_reason": (
                "Approval requires HQ review: high-risk duplicate customer detected. "
                "Please request HQ approval before proceeding."
            ),
            "fraud_check": latest_check,
            "requires_hq": True,
        }

    return {"can_approve": True, "blocked_reason": None, "fraud_check": latest_check, "requires_hq": False}


# ── Private helpers ──────────────────────────────────────────────────────────


def _contract_summary(contract, matched_by: str) -> Dict:
    amount_remaining = float(contract.total_amount - contract.amount_paid)
    phone_raw = contract.customer_phone or ""
    masked_phone = phone_raw[:3] + "***" + phone_raw[-2:] if len(phone_raw) >= 5 else "***"
    return {
        "contract_number": contract.contract_number,
        "status": contract.status,
        "device_model": contract.device_model,
        "total_amount": float(contract.total_amount),
        "amount_paid": float(contract.amount_paid),
        "amount_remaining": amount_remaining,
        "start_date": str(contract.start_date),
        "matched_by": matched_by,
        "customer_phone_masked": masked_phone,
    }


def _app_summary(app, matched_by: str) -> Dict:
    return {
        "application_number": app.application_number,
        "status": app.status,
        "device": str(app.deal) if app.deal else "N/A",
        "matched_by": matched_by,
        "submitted_at": str(app.submitted_at or app.created_at),
    }


def _bucket_contract(entry, status, active, overdue, locked, completed):
    if status in ("active",):
        active.append(entry)
    elif status in ("overdue",):
        overdue.append(entry)
    elif status in ("locked",):
        locked.append(entry)
    elif status in ("completed",):
        completed.append(entry)
    else:
        active.append(entry)


def _bucket_application(entry, status, pending, approved, rejected):
    if status in ("approved", "contract_complete", "completed"):
        approved.append(entry)
    elif status in ("rejected",):
        rejected.append(entry)
    else:
        pending.append(entry)


def _assess_risk(
    active_contracts,
    overdue_contracts,
    locked_contracts,
    completed_contracts,
    rejected_applications,
) -> tuple:
    from risk.models import FraudCheck

    if locked_contracts or (active_contracts and overdue_contracts):
        return FraudCheck.RISK_BLOCK, FraudCheck.ACTION_BLOCK

    if active_contracts or overdue_contracts:
        return FraudCheck.RISK_HIGH, FraudCheck.ACTION_HQ

    if rejected_applications:
        return FraudCheck.RISK_MEDIUM, FraudCheck.ACTION_MANUAL

    if completed_contracts:
        return FraudCheck.RISK_LOW, FraudCheck.ACTION_PROCEED

    return FraudCheck.RISK_NONE, FraudCheck.ACTION_PROCEED


# ── Age / analytics helpers ──────────────────────────────────────────────────

def calculate_age(date_of_birth) -> Optional[int]:
    """Return age in years from date_of_birth (date or None)."""
    if not date_of_birth:
        return None
    from django.utils import timezone
    today = timezone.now().date()
    age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    return age


def get_age_band(age: Optional[int]) -> str:
    """Return standardised age band string."""
    if age is None:
        return "unknown"
    if age < 20:
        return "under_20"
    if age < 25:
        return "20_24"
    if age < 35:
        return "25_34"
    if age < 45:
        return "35_44"
    if age < 55:
        return "45_54"
    return "55_plus"


def payment_analytics_dimensions(contract) -> Dict[str, Any]:
    """
    Return analytics dimension dict for a PaymentContract.
    Used for HQ reporting slices by age, gender, district, etc.
    """
    app = getattr(contract, "source_application", None)
    if app is None:
        return {"district": "unknown", "age_band": "unknown", "gender": "unknown",
                "marital_status": "unknown", "phone_user": "unknown",
                "device_model": contract.device_model or "unknown",
                "merchant": "unknown"}

    dob = getattr(app, "date_of_birth", None)
    age = calculate_age(dob)
    return {
        "district": app.district or "unknown",
        "age_band": get_age_band(age),
        "age": age,
        "gender": getattr(app, "gender", "") or "unknown",
        "marital_status": getattr(app, "marital_status", "") or "unknown",
        "num_dependents": getattr(app, "num_dependents", None),
        "phone_user": getattr(app, "phone_user", "") or "unknown",
        "device_model": contract.device_model or "unknown",
        "merchant": str(app.created_by) if app.created_by else "unknown",
        "underwriter": str(app.reviewed_by) if app.reviewed_by else "unknown",
        "deposit_percent": float(app.selected_deposit_percent or 0),
    }
