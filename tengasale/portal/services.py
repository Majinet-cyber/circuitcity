"""
Portal business logic services.

All pricing, payment allocation, and contract helper functions.
These are pure functions where possible — easy to test.
"""

from decimal import ROUND_HALF_UP, Decimal
from datetime import timedelta

from django.utils import timezone


# ---------------------------------------------------------------------------
# Pricing helpers
# ---------------------------------------------------------------------------

def calculate_daily_price(total_amount: Decimal, term_months: int) -> Decimal:
    """Daily price = total / (term_months * 30)."""
    if not total_amount or not term_months:
        return Decimal("0")
    daily = total_amount / Decimal(term_months * 30)
    return daily.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_thirty_day_price(total_amount: Decimal, term_months: int) -> Decimal:
    """30-day price = total / term_months."""
    if not total_amount or not term_months:
        return Decimal("0")
    monthly = total_amount / Decimal(term_months)
    return monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_remaining_amount(contract) -> Decimal:
    """Remaining = total_amount - amount_paid (floor at 0)."""
    remaining = contract.total_amount - contract.amount_paid
    return max(remaining, Decimal("0"))


def calculate_lock_date(contract) -> "date | None":
    """
    Lock date = due_date + 3 grace days (configurable).
    Returns None if due_date is not set.
    """
    if not contract.due_date:
        return None
    return contract.due_date + timedelta(days=3)


def calculate_next_due_date(contract) -> "date":
    """
    Recalculate due date based on amount paid.
    Each daily_price paid extends active usage by 1 day from start_date.
    """
    if not contract.daily_price or contract.daily_price <= 0:
        # Fallback: extend by term if fully paid, else today
        return timezone.localdate()

    days_paid = int(contract.amount_paid / contract.daily_price)
    return contract.start_date + timedelta(days=days_paid)


def calculate_early_settlement_options(contract) -> list[dict]:
    """
    Return early settlement options for 3, 6, 9, 12 months.

    Each option shows:
      - term_months
      - total_cost
      - remaining_amount (to pay now)
      - daily_price
      - thirty_day_price
      - discount_percent
    """
    remaining = calculate_remaining_amount(contract)
    options = []

    settlement_configs = [
        (3, Decimal(str(contract.early_settlement_3m_discount))),
        (6, Decimal(str(contract.early_settlement_6m_discount))),
        (9, Decimal(str(contract.early_settlement_9m_discount))),
        (12, Decimal("0")),  # No discount for full term
    ]

    for term_months, discount_percent in settlement_configs:
        if discount_percent > 0:
            discounted_remaining = remaining * (1 - discount_percent / 100)
            discounted_remaining = discounted_remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_cost = contract.amount_paid + discounted_remaining
        else:
            discounted_remaining = remaining
            total_cost = contract.total_amount

        options.append({
            "term_months": term_months,
            "discount_percent": discount_percent,
            "total_cost": total_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "remaining_to_pay": discounted_remaining,
            "daily_price": calculate_daily_price(discounted_remaining, max(term_months, 1)),
            "thirty_day_price": calculate_thirty_day_price(discounted_remaining, max(term_months, 1)),
        })

    return options


# ---------------------------------------------------------------------------
# Payment allocation
# ---------------------------------------------------------------------------

def apply_payment_to_contract(contract, amount: Decimal, db_save: bool = True) -> dict:
    """
    Apply a payment to a contract.

    Allocation order:
    1. First clears any arrears (overdue amount).
    2. Remaining payment extends active usage days.

    Returns a dict with allocation details.
    """
    if amount <= 0:
        return {"applied": Decimal("0"), "arrears_cleared": Decimal("0"), "days_extended": 0}

    remaining_before = calculate_remaining_amount(contract)
    applied = min(amount, remaining_before)

    # Calculate days extended by this payment
    days_extended = 0
    if contract.daily_price and contract.daily_price > 0:
        days_extended = int(applied / contract.daily_price)

    # Update contract
    contract.amount_paid += applied

    # Recalculate due date and lock date
    new_due = calculate_next_due_date(contract)
    contract.due_date = new_due
    contract.lock_date = new_due + timedelta(days=3)

    # Update status
    if contract.amount_paid >= contract.total_amount:
        contract.status = "completed"
    elif new_due < timezone.localdate():
        contract.status = "overdue"
    else:
        contract.status = "active"

    # Update pricing fields
    remaining_after = calculate_remaining_amount(contract)
    contract.daily_price = calculate_daily_price(remaining_after, max(contract.term_months, 1))
    contract.thirty_day_price = calculate_thirty_day_price(remaining_after, max(contract.term_months, 1))

    if db_save:
        contract.save(update_fields=[
            "amount_paid", "due_date", "lock_date", "status",
            "daily_price", "thirty_day_price",
        ])

    return {
        "applied": applied,
        "days_extended": days_extended,
        "new_due_date": contract.due_date,
        "new_lock_date": contract.lock_date,
        "remaining": remaining_after,
        "status": contract.status,
    }


# ---------------------------------------------------------------------------
# Contract search
# ---------------------------------------------------------------------------

def search_payment_contract(query: str):
    """
    Look up a PaymentContract by:
      - contract_number (TS-MW-XXXXXXXX)
      - payg_number (TSGXXXXXX)
      - customer_national_id
      - customer_phone (last 9 digits matched)

    Returns the first matching PaymentContract or None.
    """
    from portal.models import PaymentContract

    q = query.strip()
    if not q:
        return None

    # Direct contract number / PayG lookup
    contract = (
        PaymentContract.objects.filter(contract_number__iexact=q).first()
        or PaymentContract.objects.filter(payg_number__iexact=q).first()
        or PaymentContract.objects.filter(customer_national_id__iexact=q).first()
    )
    if contract:
        return contract

    # Phone lookup — strip country code and match last 9 digits
    digits = "".join(c for c in q if c.isdigit())
    if len(digits) >= 9:
        last9 = digits[-9:]
        contract = PaymentContract.objects.filter(
            customer_phone__endswith=last9
        ).first()
    return contract
