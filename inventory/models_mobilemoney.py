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
    BANK = "bank", "Bank Agent"
    OTHER = "other", "Other / Custom"


class MobileMoneyTxType(models.TextChoices):
    SEND_MONEY = "send_money", "Send Money"
    RECEIVE_MONEY = "receive_money", "Receive Money"
    CASH_IN = "cash_in", "Cash In"
    CASH_OUT = "cash_out", "Cash Out"
    FLOAT_PURCHASE = "float_purchase", "Float Purchase"
    AIRTIME = "airtime", "Airtime Top-Up"
    BILL_PAYMENT = "bill_payment", "Bill Payment"
    REVERSAL = "reversal", "Reversal"
    FAILED = "failed", "Failed Transaction"
    CORRECTION = "correction", "Correction"
    ADJUSTMENT = "adjustment", "Adjustment"


# Cash/float movement logic per transaction type
# (cash_delta_sign, float_delta_sign)
# +1 means amount is added, -1 means amount is subtracted, 0 means no movement
TX_MOVEMENTS: dict[str, tuple[int, int]] = {
    MobileMoneyTxType.SEND_MONEY:      (+1, -1),  # agent pays out float, collects cash
    MobileMoneyTxType.RECEIVE_MONEY:   (-1, +1),  # agent collects float, pays out cash
    MobileMoneyTxType.CASH_IN:         (+1, -1),  # customer deposits cash → agent gets cash, gives float
    MobileMoneyTxType.CASH_OUT:        (-1, +1),  # customer withdraws cash ← agent loses cash, gains float
    MobileMoneyTxType.FLOAT_PURCHASE:  (-1, +1),  # agent buys float: spends cash, gains float
    MobileMoneyTxType.AIRTIME:         (0,  -1),  # float only
    MobileMoneyTxType.BILL_PAYMENT:    (0,  -1),  # float only
    MobileMoneyTxType.REVERSAL:        (0,   0),  # manually set
    MobileMoneyTxType.FAILED:          (0,   0),  # no movement
    MobileMoneyTxType.CORRECTION:      (0,   0),  # manually set
    MobileMoneyTxType.ADJUSTMENT:      (0,   0),  # manually set
}


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
    charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Charges deducted from customer or network fees",
    )
    customer_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Customer name (optional)",
    )
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    reference_number = models.CharField(
        max_length=50, blank=True, default="", help_text="Transaction reference from network"
    )

    # Cash & float movements (auto-set on save if not explicitly overridden)
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
            models.Index(fields=["business", "network", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_tx_type_display()} MK {self.amount} ({self.network})"


class CreditType(models.TextChoices):
    CUSTOMER_CREDIT = "customer_credit", "Customer Credit (they owe us)"
    AGENT_DEBT = "agent_debt", "Agent Debt (we owe them)"


class MobileMoneyCredit(models.Model):
    """Tracks credit/loans — either customers who owe the agent, or agents the business owes."""

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
    credit_type = models.CharField(
        max_length=20,
        choices=CreditType.choices,
        default=CreditType.CUSTOMER_CREDIT,
        db_index=True,
        help_text="Whether we are owed (credit) or we owe (debt)",
    )
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    amount_credited = models.DecimalField(max_digits=12, decimal_places=2)
    amount_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(null=True, blank=True)
    reason = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Reason for credit/debt (e.g. 'sent money, forgot to collect')",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    notes = models.TextField(blank=True, default="")
    source_transaction = models.ForeignKey(
        MobileMoneyTransaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_credits",
        help_text="Transaction that originated this credit/debt",
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mm_credits_created"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "credit_type", "status"]),
        ]

    def __str__(self):
        label = "owes us" if self.credit_type == CreditType.CUSTOMER_CREDIT else "we owe"
        return f"{self.customer_name} ({label}): MK {self.amount_credited} (balance: MK {self.balance})"

    @property
    def balance(self) -> Decimal:
        return self.amount_credited - self.amount_repaid

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone as tz
        if self.due_date and self.status not in (self.STATUS_PAID,):
            return self.due_date < tz.now().date()
        return False

    def update_status(self) -> None:
        """Recalculate and persist status based on repayments."""
        if self.amount_repaid >= self.amount_credited:
            self.amount_repaid = self.amount_credited
            self.status = self.STATUS_PAID
        elif self.amount_repaid > 0:
            self.status = self.STATUS_PARTIAL
            if self.is_overdue:
                self.status = self.STATUS_OVERDUE
        else:
            if self.is_overdue:
                self.status = self.STATUS_OVERDUE
            else:
                self.status = self.STATUS_PENDING


class CommissionRuleType(models.TextChoices):
    FIXED = "fixed", "Fixed Amount"
    PERCENTAGE = "percentage", "Percentage of Transaction"
    SLAB = "slab", "Amount Slab"


class CommissionRule(models.Model):
    """Configurable commission structure for a provider/transaction type."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="mm_commission_rules"
    )
    network = models.CharField(
        max_length=20,
        choices=MobileMoneyNetwork.choices,
        db_index=True,
    )
    tx_type = models.CharField(
        max_length=20,
        choices=MobileMoneyTxType.choices,
        db_index=True,
    )
    rule_type = models.CharField(
        max_length=20,
        choices=CommissionRuleType.choices,
        default=CommissionRuleType.PERCENTAGE,
    )
    # For FIXED rules
    fixed_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    # For PERCENTAGE rules
    percentage_rate = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000"),
        help_text="e.g. 0.0150 = 1.5%",
    )
    # For SLAB rules — amount range
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    max_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Leave blank for no upper limit",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["network", "tx_type", "min_amount"]

    def __str__(self):
        return f"{self.get_network_display()} {self.get_tx_type_display()} — {self.get_rule_type_display()}"

    def calculate(self, amount: Decimal) -> Decimal:
        """Calculate commission for a given transaction amount."""
        if self.rule_type == CommissionRuleType.FIXED:
            return self.fixed_amount
        elif self.rule_type == CommissionRuleType.PERCENTAGE:
            return (amount * self.percentage_rate).quantize(Decimal("0.01"))
        elif self.rule_type == CommissionRuleType.SLAB:
            if amount >= self.min_amount:
                if self.max_amount is None or amount <= self.max_amount:
                    return self.fixed_amount
        return Decimal("0.00")


class AgentSettlementType(models.TextChoices):
    BORROWED_FLOAT = "borrowed_float", "Borrowed Float"
    RETURNED_FLOAT = "returned_float", "Returned Float"
    BORROWED_CASH = "borrowed_cash", "Borrowed Cash"
    RETURNED_CASH = "returned_cash", "Returned Cash"
    SETTLEMENT = "settlement", "General Settlement"


class AgentSettlement(models.Model):
    """Records inter-agent float/cash borrowing and settlements."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="mm_agent_settlements"
    )
    settlement_type = models.CharField(
        max_length=20,
        choices=AgentSettlementType.choices,
        default=AgentSettlementType.BORROWED_FLOAT,
        db_index=True,
    )
    agent_name = models.CharField(max_length=150, help_text="Other agent's name")
    agent_phone = models.CharField(max_length=20, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # direction: did we give or receive?
    DIRECTION_GIVEN = "given"
    DIRECTION_RECEIVED = "received"
    DIRECTION_CHOICES = [
        (DIRECTION_GIVEN, "We gave"),
        (DIRECTION_RECEIVED, "We received"),
    ]
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default=DIRECTION_RECEIVED,
        help_text="Did we give or receive?",
    )
    is_settled = models.BooleanField(default=False)
    settled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mm_settlements_created"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_settlement_type_display()} {self.direction} {self.agent_name}: MK {self.amount}"

    @property
    def balance_impact(self) -> Decimal:
        """Positive = we are owed / have received; Negative = we owe."""
        borrow_types = {AgentSettlementType.BORROWED_FLOAT, AgentSettlementType.BORROWED_CASH}
        if self.settlement_type in borrow_types:
            if self.direction == self.DIRECTION_RECEIVED:
                return -self.amount  # we owe them
            else:
                return self.amount   # they owe us
        # Return / settlement types
        if self.direction == self.DIRECTION_GIVEN:
            return -self.amount  # we paid out
        return self.amount


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
    total_commissions = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Commission earned on this day",
    )

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

    @property
    def status_label(self) -> str:
        if self.difference == 0:
            return "balanced"
        elif abs(self.difference) < Decimal("5000"):
            return "minor_mismatch"
        elif self.difference < 0:
            return "shortage"
        return "overage"

    @property
    def status_color(self) -> str:
        label = self.status_label
        if label == "balanced":
            return "green"
        elif label == "minor_mismatch":
            return "amber"
        return "red"
