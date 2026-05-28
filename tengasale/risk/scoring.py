"""
risk/scoring.py

Internal credit scoring engine for TengaSale.

Produces a CreditRiskAssessment for a FinancingApplication using rule-based scoring.
No black-box logic — every reason is human-readable and explainable.

Risk bands:
  low        → 15% deposit recommended
  medium     → 20% deposit recommended
  high       → 30% deposit recommended
  manual_review → requires human decision

Scoring dimensions (each 0–100):
  1. Affordability     (income vs monthly payment)
  2. Identity          (KYC completeness and ID match)
  3. Repayment risk    (guarantor, call verification, prior history)
  4. Data quality      (completeness of application fields)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Tuple

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from applications.models import FinancingApplication
    from .models import CreditRiskAssessment


def score_application(app: "FinancingApplication", save: bool = True) -> "CreditRiskAssessment":
    """
    Run credit risk scoring on a FinancingApplication.

    Creates or updates a CreditRiskAssessment.
    Returns the assessment instance.
    """
    from .models import CreditRiskAssessment

    affordability, aff_reasons = _score_affordability(app)
    identity, id_reasons = _score_identity(app)
    repayment, rep_reasons = _score_repayment_risk(app)
    data_quality, dq_reasons = _score_data_quality(app)

    final = _weighted_final(affordability, identity, repayment, data_quality)
    all_reasons = aff_reasons + id_reasons + rep_reasons + dq_reasons
    risk_band, deposit_pct = _determine_risk_band(final, all_reasons)

    assessment, _ = CreditRiskAssessment.objects.get_or_create(application=app)
    assessment.affordability_score = affordability
    assessment.identity_score = identity
    assessment.repayment_risk_score = repayment
    assessment.data_quality_score = data_quality
    assessment.final_score = final
    assessment.risk_band = risk_band
    assessment.recommended_deposit_percent = deposit_pct
    assessment.reasons = all_reasons

    if save:
        assessment.save()

    logger.info(
        "Scored application %s: final=%d risk=%s deposit=%s%%",
        app.application_number, final, risk_band, deposit_pct,
    )
    return assessment


# ──────────────────────────────────────────────────────────────────────────────
# Scoring dimensions
# ──────────────────────────────────────────────────────────────────────────────


def _score_affordability(app: "FinancingApplication") -> Tuple[int, List[str]]:
    """Income vs monthly payment ratio."""
    reasons: List[str] = []
    monthly_income = Decimal(app.exact_monthly_income or app.monthly_income or 0)
    monthly_payment = Decimal(app.calculated_monthly_payment or 0)

    if monthly_payment <= 0:
        return 50, ["Monthly payment not calculated"]

    if monthly_income <= 0:
        reasons.append("income amount is missing or zero")
        return 20, reasons

    ratio = monthly_income / monthly_payment

    if ratio >= 10:
        score = 100
    elif ratio >= 7:
        score = 85
    elif ratio >= 5:
        score = 70
    elif ratio >= 3:
        score = 50
        reasons.append("income-to-payment ratio is below 5x (moderate affordability)")
    elif ratio >= 2:
        score = 30
        reasons.append("income-to-payment ratio is below 3x (low affordability)")
    else:
        score = 10
        reasons.append("monthly instalment exceeds affordability threshold (ratio below 2x)")

    return score, reasons


def _score_identity(app: "FinancingApplication") -> Tuple[int, List[str]]:
    """KYC completeness and document presence."""
    reasons: List[str] = []
    score = 100
    deductions = []

    if not app.customer_face_image:
        deductions.append(("selfie image is missing", 25))
    if not app.id_front_image:
        deductions.append(("ID front image is missing", 20))
    if not app.id_back_image:
        deductions.append(("ID back image is missing", 15))
    if not app.national_id or len(app.national_id.strip()) < 4:
        deductions.append(("National ID number is missing or too short", 20))
    if not app.customer_name or len(app.customer_name.strip()) < 3:
        deductions.append(("customer name is missing", 15))

    for reason, penalty in deductions:
        reasons.append(reason)
        score -= penalty

    score = max(score, 0)
    return score, reasons


def _score_repayment_risk(app: "FinancingApplication") -> Tuple[int, List[str]]:
    """
    Combines guarantor confidence, call verification answers,
    and any available prior history.
    """
    reasons: List[str] = []
    score = 100
    deductions = []

    has_guarantor = bool(app.next_of_kin_1_name and app.next_of_kin_1_phone)
    if not has_guarantor:
        deductions.append(("no guarantor/next-of-kin provided", 20))

    has_kin2 = bool(app.next_of_kin_2_name and app.next_of_kin_2_phone)
    if not has_kin2:
        deductions.append(("no secondary contact provided", 10))

    try:
        review = app.underwriter_review
        if review.customer_spoken is False:
            deductions.append(("underwriter could not reach customer for call verification", 25))
        elif review.customer_spoken is None:
            deductions.append(("customer call not yet completed", 15))

        if review.income_contact_spoken is False:
            deductions.append(("income/employer contact could not be reached", 20))
        elif review.income_contact_spoken is None:
            deductions.append(("income verification call not yet completed", 10))

        if review.income_contact_confident is False:
            deductions.append(("income contact expressed doubt about repayment ability", 15))

        if review.location_traceable is False:
            deductions.append(("address traceability is weak — location may be hard to follow up", 10))
    except Exception:
        deductions.append(("underwriter review not yet completed", 20))

    active_corrections = app.corrections.filter(resolved=False).count() if app.pk else 0
    if active_corrections >= 5:
        deductions.append((f"{active_corrections} fields marked for correction — high data concern", 15))
    elif active_corrections >= 3:
        deductions.append((f"{active_corrections} fields marked for correction", 8))

    for reason, penalty in deductions:
        reasons.append(reason)
        score -= penalty

    score = max(score, 0)
    return score, reasons


def _score_data_quality(app: "FinancingApplication") -> Tuple[int, List[str]]:
    """Application field completeness."""
    reasons: List[str] = []
    score = 100
    deductions = []

    if not app.region:
        deductions.append(("region not specified", 10))
    if not app.district:
        deductions.append(("district not specified", 8))
    if not app.traditional_authority:
        deductions.append(("traditional authority not specified", 5))
    if not app.precise_location:
        deductions.append(("precise location description missing", 5))
    if not app.occupation:
        deductions.append(("occupation is missing", 10))
    if not app.proof_of_income_type:
        deductions.append(("proof of income type not provided", 10))
    if not app.proof_income_file and not app.proof_contact_name:
        deductions.append(("no income proof file or contact provided", 8))
    if not app.agreed_to_terms:
        deductions.append(("customer has not agreed to terms", 10))

    for reason, penalty in deductions:
        reasons.append(reason)
        score -= penalty

    score = max(score, 0)
    return score, reasons


def _weighted_final(affordability: int, identity: int, repayment: int, data_quality: int) -> int:
    """Weighted average: affordability 35%, identity 25%, repayment 25%, data 15%."""
    return int(
        affordability * 0.35
        + identity * 0.25
        + repayment * 0.25
        + data_quality * 0.15
    )


def _determine_risk_band(final_score: int, reasons: List[str]) -> Tuple[str, Decimal]:
    """Map final score to risk band and recommended deposit."""
    from .models import CreditRiskAssessment

    if final_score >= 75:
        return CreditRiskAssessment.RISK_LOW, Decimal("15")
    elif final_score >= 60:
        return CreditRiskAssessment.RISK_MEDIUM, Decimal("20")
    elif final_score >= 40:
        return CreditRiskAssessment.RISK_HIGH, Decimal("30")
    else:
        return CreditRiskAssessment.RISK_MANUAL, Decimal("30")


# ──────────────────────────────────────────────────────────────────────────────
# Simulation tools (for HQ dashboard — clearly labelled as simulation)
# ──────────────────────────────────────────────────────────────────────────────


def simulate_portfolio(
    *,
    cash_price: float,
    selling_total: float,
    deposit_percent: float,
    term_months: int,
    expected_default_rate: float,
    monthly_hosting_cost: float = 0,
    lock_provider_cost_per_device: float = 0,
    payment_fee_percent: float = 0,
    num_devices: int = 1,
) -> Dict:
    """
    Simulate phone financing profitability.
    All outputs are estimates — clearly labelled as SIMULATION.
    """
    deposit_amount = cash_price * (deposit_percent / 100)
    financed_amount = selling_total - deposit_amount
    monthly_payment = financed_amount / term_months if term_months > 0 else 0

    total_capital = cash_price * num_devices
    total_deposit_collected = deposit_amount * num_devices
    total_expected_collections = selling_total * num_devices
    total_gross_margin = (selling_total - cash_price) * num_devices

    defaulting_devices = int(num_devices * (expected_default_rate / 100))
    defaulting_loss = cash_price * defaulting_devices * 0.5  # assume 50% recovery

    payment_fees = total_expected_collections * (payment_fee_percent / 100)
    fixed_costs = (monthly_hosting_cost * term_months) + (lock_provider_cost_per_device * num_devices)
    total_costs = total_capital + defaulting_loss + payment_fees + fixed_costs

    net_gain = total_expected_collections + total_deposit_collected - total_costs - total_capital
    expected_loss = defaulting_loss

    cashflow_pressure = total_capital - total_deposit_collected
    break_even_month = None
    cumulative = -cashflow_pressure
    for m in range(1, term_months + 1):
        monthly_in = monthly_payment * (num_devices - defaulting_devices)
        monthly_cost = monthly_hosting_cost + (lock_provider_cost_per_device * num_devices / term_months)
        cumulative += monthly_in - monthly_cost
        if cumulative >= 0 and break_even_month is None:
            break_even_month = m

    return {
        "label": "SIMULATION — Estimates Only",
        "inputs": {
            "cash_price": cash_price,
            "selling_total": selling_total,
            "deposit_percent": deposit_percent,
            "term_months": term_months,
            "expected_default_rate": expected_default_rate,
            "num_devices": num_devices,
        },
        "outputs": {
            "total_capital_needed": round(total_capital, 2),
            "expected_collections": round(total_expected_collections, 2),
            "expected_gross_margin": round(total_gross_margin, 2),
            "expected_loss": round(expected_loss, 2),
            "net_gain": round(net_gain, 2),
            "cashflow_pressure": round(cashflow_pressure, 2),
            "break_even_month": break_even_month,
            "defaulting_devices": defaulting_devices,
            "monthly_payment_per_device": round(monthly_payment, 2),
            "deposit_per_device": round(deposit_amount, 2),
        },
    }
