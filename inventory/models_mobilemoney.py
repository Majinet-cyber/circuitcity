# inventory/models_mobilemoney.py
"""
Mobile Money vertical models.
Helps agents record and reconcile mobile money transactions (Airtel Money, TNM Mpamba, etc.).
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


class MobileMoneyNetwork(models.TextChoices):
    AIRTEL = "airtel", "Airtel Money"
    TNM = "tnm", "TNM Mpamba"
    OTHER = "other", "Other"


class MobileMoneyTxType(models.TextChoices):
    CASH_IN = "cash_in", "Cash In"
    CASH_OUT = "cash_out", "Cash Out"
    AIRTIME = "airtime", "Airtime Top-Up"
    BILL_PAYMENT = "bill_payment", "Bill Payment"
    REVERSAL = "reversal", "Reversal"
    ADJUSTMENT = "adjustment", "Adjustment"


class MobileMoneyTransaction(models.Model):
    """Records a single mobile money transaction made by the agent."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="mobile_money_transactions"
    )
    tx_type = models.CharField(
        max_length=20,
        choices=MobileMoneyTxType.choices,
        default=MobileMoneyTxType.CASH_IN,
        db_index=True,
        help_text="Type of transaction",
    )
    network = models.CharField(
        max_length=20,
        choices=MobileMoneyNetwork.choices,
        default=MobileMoneyNetwork.AIRTEL,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Commission/fee earned by agent",
    )
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    reference_number = models.CharField(
        max_length=50, blank=True, default="", help_text="Transaction reference from network"
    )

    # Cash & float movements
    cash_movement = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Change in physical cash (+inflow, -outflow)",
    )
    float_movement = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Change in e-float (+inflow, -outflow)",
    )

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mm_transactions_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "tx_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_tx_type_display()} MK {self.amount} ({self.network})"


class MobileMoneyCredit(models.Model):
    """Tracks credit/loans given to customers."""

    STATUS_PENDING = "pending"
    STATUS_PARTIAL = "partial"
    STATUS_PAID = "paid"
    STATUS_OVERDUE = "overdue"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PARTIAL, "Partially Paid"),
        (STATUS_PAID, "Fully Paid"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="mobile_money_credits"
    )
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    amount_credited = models.DecimalField(max_digits=12, decimal_places=2)
    amount_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mm_credits_created"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer_name}: MK {self.amount_credited} (balance: MK {self.balance})"

    @property
    def balance(self) -> Decimal:
        return self.amount_credited - self.amount_repaid


class MobileMoneyReconciliation(models.Model):
    """Daily reconciliation record for the agent."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="mobile_money_reconciliations"
    )
    date = models.DateField(db_index=True)

    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    opening_float = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    total_cash_in = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_cash_out = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_float_in = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_float_out = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    expected_closing_cash = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    actual_closing_cash = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="actual_closing_cash - expected_closing_cash (negative = shortage)",
    )

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mm_reconciliations_created"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-date"]
        unique_together = [("business", "date")]

    def __str__(self):
        return f"Reconciliation {self.date}: difference MK {self.difference}"

    def save(self, *args, **kwargs):
        self.expected_closing_cash = (
            self.opening_cash + self.total_cash_in - self.total_cash_out
        )
        self.difference = self.actual_closing_cash - self.expected_closing_cash
        super().save(*args, **kwargs)
