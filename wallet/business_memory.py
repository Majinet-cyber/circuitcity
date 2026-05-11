from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from .money import q2
from .models import CashBankTransaction, Ledger, TxnType, WalletTransaction

log = logging.getLogger(__name__)


def payment_method_for_cash_bank(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"bank", "bank_transfer", "transfer"}:
        return CashBankTransaction.PaymentMethod.BANK
    if raw in {"airtel", "airtel_money"}:
        return CashBankTransaction.PaymentMethod.AIRTEL
    if raw in {"mpamba", "tnm_mpamba"}:
        return CashBankTransaction.PaymentMethod.MPAMBA
    if raw in {"mobile", "mobile_money", "momo", "wallet"}:
        return CashBankTransaction.PaymentMethod.AIRTEL
    if raw in {"cash", ""}:
        return CashBankTransaction.PaymentMethod.CASH
    return CashBankTransaction.PaymentMethod.OTHER


def business_date(value: Any = None) -> date:
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value).date()
    if isinstance(value, date):
        return value
    return timezone.localdate()


def is_credit_payment(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {"credit", "layby", "unpaid", "receivable", "invoice"}


def record_cash_bank_transaction(
    *,
    business,
    amount: Any,
    direction: str,
    category: str,
    payment_method: Any = None,
    tx_date: Any = None,
    description: str = "",
    related_sale_reference: str = "",
    created_by=None,
) -> CashBankTransaction | None:
    if not business:
        return None
    amount = q2(amount)
    if amount <= Decimal("0.00"):
        return None
    if direction not in CashBankTransaction.Direction.values:
        return None

    tx_date = business_date(tx_date)
    method = payment_method_for_cash_bank(payment_method)
    reference = (related_sale_reference or "").strip()

    qs = CashBankTransaction.objects.filter(
        business=business,
        direction=direction,
        amount=amount,
        date=tx_date,
    )
    if reference:
        qs = qs.filter(related_sale_reference=reference)
    else:
        qs = qs.filter(category=category, payment_method=method, description=description[:255])
    existing = qs.first()
    if existing:
        return existing

    try:
        return CashBankTransaction.objects.create(
            business=business,
            date=tx_date,
            direction=direction,
            category=category[:80] or "Business transaction",
            payment_method=method,
            amount=amount,
            description=description,
            related_sale_reference=reference,
            created_by=created_by,
        )
    except Exception:
        log.exception("Failed to record cash/bank transaction for business memory.")
        return None


def record_sale_cash_memory(
    *,
    sale,
    business,
    amount: Any,
    payment_method: Any,
    sold_at: Any = None,
    created_by=None,
    reference: str,
    category: str = "Sale payment",
) -> CashBankTransaction | None:
    if getattr(sale, "is_rolled_back", False) or getattr(sale, "is_reversed", False):
        return None
    if getattr(sale, "is_deleted", False) or getattr(sale, "is_void", False) or getattr(sale, "is_free", False):
        return None
    if getattr(sale, "is_credit", False) or is_credit_payment(payment_method):
        return None
    return record_cash_bank_transaction(
        business=business,
        amount=amount,
        direction=CashBankTransaction.Direction.CASH_IN,
        category=category,
        payment_method=payment_method,
        tx_date=sold_at,
        description=f"Recorded from {reference}",
        related_sale_reference=reference,
        created_by=created_by,
    )


def record_company_expense_once(
    *,
    business,
    amount: Any,
    note: str,
    reference: str,
    created_by=None,
    agent=None,
    effective_date: Any = None,
    txn_type: str = TxnType.COST_ONCE_OFF,
    meta: dict[str, Any] | None = None,
) -> WalletTransaction | None:
    if not business:
        return None
    amount = q2(amount)
    if amount <= Decimal("0.00"):
        return None
    if reference and WalletTransaction.objects.filter(business=business, reference=reference).exists():
        return None
    payload = dict(meta or {})
    payload.setdefault("business_memory", True)
    try:
        return WalletTransaction.objects.create(
            business=business,
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=-amount,
            type=txn_type,
            note=note,
            reference=reference[:64],
            effective_date=business_date(effective_date),
            created_by=created_by,
            meta=payload,
        )
    except Exception:
        log.exception("Failed to record company expense for business memory.")
        return None
