"""
Portal models — customer payment portal.

PaymentContract is the public-facing contract (TS-MW-XXXXXXXX / TSGXXXXXX).
PaymentTransaction records each individual payment attempt.
"""

import random
import secrets
import string

from django.db import models
from django.utils import timezone


def generate_contract_number():
    """Generate a unique TS-MW-XXXXXXXX contract number."""
    for _ in range(100):
        suffix = "".join(random.choices(string.digits, k=8))
        number = f"TS-MW-{suffix}"
        if not PaymentContract.objects.filter(contract_number=number).exists():
            return number
    raise RuntimeError("Could not generate a unique contract number after 100 attempts.")


def generate_payg_number():
    """Generate a unique TSGXXXXXX PayG number."""
    for _ in range(100):
        suffix = "".join(random.choices(string.digits, k=6))
        number = f"TSG{suffix}"
        if not PaymentContract.objects.filter(payg_number=number).exists():
            return number
    raise RuntimeError("Could not generate a unique PayG number after 100 attempts.")


def generate_payment_reference():
    """Generate a unique TS-PAY-XXXXXXXX internal payment reference."""
    for _ in range(100):
        suffix = "".join(random.choices(string.digits + string.ascii_uppercase, k=8))
        ref = f"TS-PAY-{suffix}"
        if not PaymentTransaction.objects.filter(internal_reference=ref).exists():
            return ref
    return f"TS-PAY-{secrets.token_urlsafe(8)[:8].upper()}"


class PaymentContract(models.Model):
    """Public-facing financing contract that customers pay against."""

    STATUS_ACTIVE = "active"
    STATUS_OVERDUE = "overdue"
    STATUS_LOCKED = "locked"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_OVERDUE, "Overdue"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    contract_number = models.CharField(max_length=15, unique=True, blank=True)
    payg_number = models.CharField(max_length=10, unique=True, blank=True)

    # Link to existing financing contract (optional — can also stand alone for demo)
    financing_contract = models.OneToOneField(
        "financing.FinancingContract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_contract",
    )

    # Customer info (denormalised for portal access without auth)
    customer_name = models.CharField(max_length=180)
    customer_phone = models.CharField(max_length=30)
    customer_national_id = models.CharField(max_length=80, blank=True)
    device_model = models.CharField(max_length=120, blank=True)

    # Financials
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    daily_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    thirty_day_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Dates
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    lock_date = models.DateField(null=True, blank=True)
    term_months = models.PositiveIntegerField(default=12)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    # Pricing config
    early_settlement_3m_discount = models.DecimalField(
        max_digits=5, decimal_places=2, default=25,
        help_text="Percentage discount for 3-month early settlement",
    )
    early_settlement_6m_discount = models.DecimalField(
        max_digits=5, decimal_places=2, default=15,
        help_text="Percentage discount for 6-month early settlement",
    )
    early_settlement_9m_discount = models.DecimalField(
        max_digits=5, decimal_places=2, default=8,
        help_text="Percentage discount for 9-month early settlement",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract_number"]),
            models.Index(fields=["payg_number"]),
            models.Index(fields=["customer_phone"]),
            models.Index(fields=["customer_national_id"]),
        ]

    def save(self, *args, **kwargs):
        if not self.contract_number:
            self.contract_number = generate_contract_number()
        if not self.payg_number:
            self.payg_number = generate_payg_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.contract_number} — {self.customer_name}"

    @property
    def remaining_amount(self):
        from decimal import Decimal
        return max(self.total_amount - self.amount_paid, Decimal("0"))

    @property
    def progress_percent(self):
        if not self.total_amount:
            return 0
        return min(100, round((self.amount_paid / self.total_amount) * 100))

    @property
    def masked_phone(self):
        p = str(self.customer_phone)
        if len(p) >= 6:
            return p[:3] + "***" + p[-3:]
        return p[:2] + "***"


class PaymentTransaction(models.Model):
    """Individual payment transaction against a PaymentContract."""

    PROVIDER_MOCK = "mock"
    PROVIDER_PAYCHANGU = "paychangu"
    PROVIDER_AIRTEL = "airtel_money"
    PROVIDER_TNM = "tnm_mpamba"
    PROVIDER_PAYTRIGGER = "paytrigger"

    PROVIDER_CHOICES = [
        (PROVIDER_MOCK, "Mock / Sandbox"),
        (PROVIDER_PAYCHANGU, "PayChangu"),
        (PROVIDER_AIRTEL, "Airtel Money"),
        (PROVIDER_TNM, "TNM Mpamba"),
        (PROVIDER_PAYTRIGGER, "PayTrigger"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "external_processing"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    payment_contract = models.ForeignKey(
        PaymentContract,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_MOCK)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default="MWK")
    phone = models.CharField(max_length=30)
    internal_reference = models.CharField(max_length=30, unique=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default=STATUS_PENDING)
    raw_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.internal_reference:
            self.internal_reference = generate_payment_reference()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.internal_reference} — MWK {self.amount} [{self.status}]"

    @property
    def masked_phone(self):
        p = str(self.phone)
        if len(p) >= 6:
            return p[:3] + "***" + p[-3:]
        return p[:2] + "***"
