"""
applications/services/discount_policy.py

TengaSale Discount & Deposit Policy Engine.

COMPLIANCE NOTE:
    Gender is collected for analytics and portfolio reporting ONLY.
    Gender must NOT be used for automated pricing, deposit requirements,
    eligibility decisions, or any risk/discount outcome.
    Any code path that offers different terms based on gender is non-compliant
    and must be removed or gated behind a compliance flag defaulted OFF.

Discount/reduced-deposit eligibility is based solely on:
    - Completed prior contracts with good repayment history
    - No existing active or running contract
    - Affordability score (income vs repayment ratio)
    - Income stability signals
    - Deposit strength (higher deposit = stronger application)
    - Customer age band (25–69 = full eligibility; 20–24 = no loyalty discount)
    - Customer risk score (if available)
    - Arrears / default history
    - External credit bureau score (if integrated)
    - Emajinet ID / KYC verification status (if integrated)
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List


# ── Policy constants ──────────────────────────────────────────────────────────

DEPOSIT_BANDS = [
    Decimal("30"),  # standard / highest risk
    Decimal("20"),  # moderate risk
    Decimal("15"),  # low risk / returning good customer
]

# Age eligibility: must be 20–69 to apply
AGE_MIN = 20
AGE_MAX = 69

# Loyalty discount: only available to returning customers aged 25+
LOYALTY_AGE_MIN = 25

# Affordability ceiling: monthly repayment must not exceed 40% of income
MAX_REPAYMENT_TO_INCOME_RATIO = Decimal("0.40")

# Maximum loyalty discount on deposit percentage (e.g. 30% → 20%)
MAX_LOYALTY_DEPOSIT_REDUCTION = Decimal("10")  # percentage points


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_deposit_eligibility(
    age: Optional[int],
    completed_contracts: int = 0,
    repayment_score: Optional[Decimal] = None,  # 0–100 scale
    monthly_income: Optional[Decimal] = None,
    monthly_repayment: Optional[Decimal] = None,
    has_active_contract: bool = False,
    has_arrears_history: bool = False,
    credit_bureau_score: Optional[int] = None,  # external score if available
    kyc_verified: bool = False,
    # Gender deliberately excluded — analytics only
) -> Dict[str, Any]:
    """
    Determine the minimum eligible deposit band and any loyalty discount
    for an applicant.

    Parameters
    ----------
    age                    : Customer age in years (None = unknown).
    completed_contracts    : Number of successfully completed prior contracts.
    repayment_score        : Historical repayment quality score (0–100).
    monthly_income         : Declared monthly income (MWK).
    monthly_repayment      : Expected monthly repayment amount (MWK).
    has_active_contract    : True if customer currently has an open contract.
    has_arrears_history    : True if customer has prior arrears / defaults.
    credit_bureau_score    : External credit score (optional, future use).
    kyc_verified           : Whether KYC (Emajinet / national ID) verified.

    Returns
    -------
    dict with keys:
        eligible             bool
        min_deposit_pct      Decimal  (30, 20, or 15)
        loyalty_discount_pct Decimal  (0 unless returning good customer)
        blocks               list[str]
        reasons              list[str]
        warnings             list[str]
    """
    blocks: List[str] = []
    reasons: List[str] = []
    warnings: List[str] = []

    # ── Hard blocks ───────────────────────────────────────────────────────────

    if has_active_contract:
        blocks.append(
            "Customer already has an active or pending contract. "
            "New applications are blocked until the existing contract is settled."
        )

    if age is not None:
        if age < AGE_MIN:
            blocks.append(f"Customer is under {AGE_MIN} years old (age {age}). Minimum age to apply is {AGE_MIN}.")
        elif age > AGE_MAX:
            blocks.append(f"Customer is over {AGE_MAX} years old (age {age}). Maximum eligible age is {AGE_MAX}.")

    # ── Affordability check ───────────────────────────────────────────────────

    if monthly_income and monthly_repayment:
        if monthly_income <= 0:
            warnings.append("Declared monthly income is zero or invalid — affordability cannot be confirmed.")
        else:
            ratio = monthly_repayment / monthly_income
            if ratio > MAX_REPAYMENT_TO_INCOME_RATIO:
                warnings.append(
                    f"Monthly repayment ({ratio:.0%} of income) exceeds the {MAX_REPAYMENT_TO_INCOME_RATIO:.0%} "
                    f"affordability ceiling. Manual review recommended."
                )
            else:
                reasons.append(f"Affordability check passed ({ratio:.0%} of income).")

    # ── Arrears / default history ─────────────────────────────────────────────

    if has_arrears_history:
        warnings.append("Customer has prior arrears or default history. Higher deposit required.")

    # ── KYC verification ─────────────────────────────────────────────────────

    if kyc_verified:
        reasons.append("KYC / National ID verified.")
    else:
        warnings.append("KYC not verified — consider flagging for enhanced review.")

    # ── Deposit band determination ────────────────────────────────────────────

    min_deposit_pct = Decimal("30")  # default: highest deposit
    loyalty_discount_pct = Decimal("0")

    if not blocks:
        if completed_contracts >= 1 and not has_arrears_history:
            # Returning customer with clean history
            if age is not None and age >= LOYALTY_AGE_MIN:
                # Full loyalty: can access 15% deposit band
                min_deposit_pct = Decimal("15")
                loyalty_discount_pct = Decimal("15")  # up to 15pp reduction from 30%
                reasons.append(
                    f"Returning customer ({completed_contracts} completed contract(s)) "
                    f"with clean repayment history — eligible for minimum 15% deposit."
                )
            else:
                # 20–24 year old returning customer: moderate reduction
                min_deposit_pct = Decimal("20")
                loyalty_discount_pct = Decimal("10")
                reasons.append(
                    "Returning customer with clean history (under 25) — eligible for 20% deposit band."
                )
        elif repayment_score is not None and repayment_score >= Decimal("80"):
            # Strong repayment score without completed contracts
            min_deposit_pct = Decimal("20")
            reasons.append("High repayment score — eligible for 20% deposit band.")
        elif credit_bureau_score is not None and credit_bureau_score >= 650:
            # Good external credit bureau score
            min_deposit_pct = Decimal("20")
            reasons.append("Good external credit bureau score — eligible for 20% deposit band.")
        else:
            # Standard new customer
            min_deposit_pct = Decimal("30")
            reasons.append("New customer with no prior history — standard 30% deposit applies.")

        if has_arrears_history:
            # Arrears always forces highest deposit band regardless of loyalty
            min_deposit_pct = Decimal("30")
            loyalty_discount_pct = Decimal("0")
            reasons.append("Prior arrears history — minimum deposit reset to 30%.")

    eligible = len(blocks) == 0

    return {
        "eligible": eligible,
        "min_deposit_pct": min_deposit_pct,
        "loyalty_discount_pct": loyalty_discount_pct,
        "blocks": blocks,
        "reasons": reasons,
        "warnings": warnings,
    }


def get_eligible_deposit_options(
    age: Optional[int],
    completed_contracts: int = 0,
    repayment_score: Optional[Decimal] = None,
    monthly_income: Optional[Decimal] = None,
    monthly_repayment: Optional[Decimal] = None,
    has_active_contract: bool = False,
    has_arrears_history: bool = False,
    credit_bureau_score: Optional[int] = None,
    kyc_verified: bool = False,
) -> List[Decimal]:
    """
    Return the list of deposit % options the applicant is eligible to choose from.
    Always returns a list sorted ascending (e.g. [15, 20, 30]).
    An ineligible applicant gets an empty list.
    """
    result = evaluate_deposit_eligibility(
        age=age,
        completed_contracts=completed_contracts,
        repayment_score=repayment_score,
        monthly_income=monthly_income,
        monthly_repayment=monthly_repayment,
        has_active_contract=has_active_contract,
        has_arrears_history=has_arrears_history,
        credit_bureau_score=credit_bureau_score,
        kyc_verified=kyc_verified,
    )
    if not result["eligible"]:
        return []
    min_pct = result["min_deposit_pct"]
    return [d for d in DEPOSIT_BANDS if d >= min_pct]
