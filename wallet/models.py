from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

# Use AUTH_USER_MODEL string for FKs to avoid import cycles
User = settings.AUTH_USER_MODEL

from .money import q2

# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------
def is_manager_like(user) -> bool:
    """Admins (is_staff) or profile.is_manager."""
    try:
        return bool(user and user.is_authenticated and (user.is_staff or user.profile.is_manager))
    except Exception:
        return False


# ----------------------------------------------------------------------
# Wallet / Transactions / Budgets
# ----------------------------------------------------------------------
class Ledger(models.TextChoices):
    AGENT = "agent", "Agent Wallet"
    COMPANY = "company", "Company (Admin) Wallet"


class TxnType(models.TextChoices):
    COMMISSION = "commission", "Commission"
    BONUS = "bonus", "Bonus"
    DEDUCTION = "deduction", "Deduction"
    ADVANCE = "advance", "Advance (Cash out)"
    PENALTY = "penalty", "Penalty"
    PAYSLIP = "payslip", "Payslip Payment"
    ADJUSTMENT = "adjustment", "Manual Adjustment"
    BUDGET = "budget", "Budget Payout/Recovery"
    COST_ONCE_OFF = "cost_once_off", "Cost (Once-off)"
    COST_RECURRING = "cost_recurring", "Cost (Recurring)"
    REVENUE = "revenue", "Revenue"


class WalletTransactionQuerySet(models.QuerySet):
    def for_user(self, user):
        """Admin/manager â†’ all; Agent â†’ only their transactions."""
        return self if is_manager_like(user) else self.filter(agent=user)

    def balance_for_agent(self, agent_id):
        s = self.filter(ledger=Ledger.AGENT, agent_id=agent_id).aggregate(total=Sum("amount"))["total"]
        return q2(s or Decimal("0"))


class RecurrenceType(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    # Future: WEEKLY, QUARTERLY, YEARLY


class WalletTransaction(models.Model):
    """
    Signed amounts in MWK.
    - Agent ledger: positives increase agent balance; negatives reduce it.
    - Company ledger: mirror of company cash flow (optional to display).
    - For cost transactions: use COMPANY ledger with negative amounts for expenses.
    """
    ledger = models.CharField(max_length=16, choices=Ledger.choices, default=Ledger.AGENT)
    agent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_txns")
    type = models.CharField(max_length=20, choices=TxnType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # signed
    note = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=64, blank=True, default="")
    # Use a date callable (not datetime) for DateField defaults
    effective_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_wallet_txns"
    )
    meta = models.JSONField(default=dict, blank=True)
    
    # --- Cost/recurring fields (only used for admin cost transactions) ---
    is_recurring = models.BooleanField(default=False, help_text="If True, this cost recurs monthly")
    recurrence = models.CharField(
        max_length=20,
        choices=RecurrenceType.choices,
        default=RecurrenceType.MONTHLY,
        blank=True,
        help_text="Recurrence pattern (only used if is_recurring=True)",
    )
    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="When recurring costs start being applied (relevant for recurring costs)",
    )
    
    # --- Business scoping (to support multi-tenant cost tracking) ---
    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="wallet_transactions",
        help_text="Business this transaction belongs to (for company costs/revenue)",
    )

    objects = WalletTransactionQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["ledger", "agent", "effective_date"]),
            models.Index(fields=["type"]),
            models.Index(fields=["business", "type", "effective_date"]),
            models.Index(fields=["business", "is_recurring", "effective_from"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.agent_id or "company"
        return f"{self.type} {self.amount} â†' {who} {self.effective_date}"

    def clean(self):
        """Validate cost transaction rules."""
        from django.core.exceptions import ValidationError
        errors = {}
        
        # Cost transactions must use COMPANY ledger
        if self.type in [TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]:
            if self.ledger != Ledger.COMPANY:
                errors["ledger"] = "Cost transactions must use COMPANY ledger."
            # Costs should have negative amounts (expenses)
            if self.amount and self.amount > 0:
                errors["amount"] = "Cost amounts should be negative (expense)."
        
        # Recurring costs need effective_from
        if self.is_recurring and not self.effective_from:
            errors["effective_from"] = "Recurring costs must have an effective_from date."
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Normalize amount to 2dp
        self.amount = q2(self.amount)
        
        # Auto-set effective_from for recurring costs if not provided
        if self.is_recurring and not self.effective_from:
            self.effective_from = self.effective_date
        
        super().save(*args, **kwargs)


class CashBankTransaction(models.Model):
    class Direction(models.TextChoices):
        CASH_IN = "cash_in", "Cash In"
        CASH_OUT = "cash_out", "Cash Out"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        AIRTEL = "airtel_money", "Airtel Money"
        MPAMBA = "mpamba", "Mpamba"
        OTHER = "other", "Other"

    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="cash_bank_transactions",
    )
    date = models.DateField(default=timezone.localdate, db_index=True)
    direction = models.CharField(max_length=12, choices=Direction.choices)
    category = models.CharField(max_length=80)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.TextField(blank=True, default="")
    related_sale_reference = models.CharField(max_length=80, blank=True, default="")
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cash_bank_transactions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-id")
        indexes = [
            models.Index(fields=["business", "date"]),
            models.Index(fields=["business", "payment_method", "date"]),
            models.Index(fields=["business", "direction", "date"]),
            models.Index(fields=["business", "category", "date"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.direction == self.Direction.CASH_IN else "-"
        return f"{self.date} {sign}{self.amount} {self.get_payment_method_display()}"

    @property
    def signed_amount(self) -> Decimal:
        amount = q2(self.amount)
        return amount if self.direction == self.Direction.CASH_IN else -amount

    def save(self, *args, **kwargs):
        self.amount = q2(self.amount)
        super().save(*args, **kwargs)
        recalculate_cash_bank_balances(self.business_id)

    def delete(self, *args, **kwargs):
        business_id = self.business_id
        result = super().delete(*args, **kwargs)
        recalculate_cash_bank_balances(business_id)
        return result


def recalculate_cash_bank_balances(business_id: int | None) -> None:
    if not business_id:
        return
    balance = Decimal("0.00")
    rows = CashBankTransaction.objects.filter(business_id=business_id).order_by("date", "created_at", "id")
    for row in rows.only("id", "amount", "direction", "balance_after"):
        balance += row.signed_amount
        new_balance = q2(balance)
        if row.balance_after != new_balance:
            CashBankTransaction.objects.filter(pk=row.pk).update(balance_after=new_balance)


# ----------------------------------------------------------------------
# Sales Targets & Attendance
# ----------------------------------------------------------------------
class SalesTarget(models.Model):
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sales_targets")
    year = models.IntegerField()
    month = models.IntegerField()  # 1..12
    target_count = models.IntegerField(default=0)
    bonus_per_extra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("5000.00"))

    class Meta:
        unique_together = [("agent", "year", "month")]

    def __str__(self) -> str:
        return f"{self.agent_id} Â· {self.year}-{self.month:02d}"


class AttendanceLog(models.Model):
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance_logs")
    date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)  # None if absent
    weekend = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = [("agent", "date")]

    def __str__(self) -> str:
        return f"{self.agent_id} Â· {self.date} Â· {'in' if self.check_in else 'absent'}"


# ----------------------------------------------------------------------
# Budget Requests
# ----------------------------------------------------------------------
class BudgetRequestQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Admin/manager see all; agent sees only their requests."""
        return self if is_manager_like(user) else self.filter(agent=user)

    def pending(self):
        return self.filter(status=BudgetRequest.Status.PENDING)

    def decided(self):
        return self.exclude(status=BudgetRequest.Status.PENDING)


class BudgetRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="budget_requests")
    title = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="decided_budgets")

    objects = BudgetRequestQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["agent", "status", "created_at"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} Â· {self.agent_id} Â· {self.amount} Â· {self.status}"

    def save(self, *args, **kwargs):
        self.amount = q2(self.amount)
        super().save(*args, **kwargs)

    # Helpers
    def approve(self, by_user):
        self.status = self.Status.APPROVED
        self.decided_at = timezone.now()
        self.decided_by = by_user
        self.save(update_fields=["status", "decided_at", "decided_by"])

    def reject(self, by_user):
        self.status = self.Status.REJECTED
        self.decided_at = timezone.now()
        self.decided_by = by_user
        self.save(update_fields=["status", "decided_at", "decided_by"])

    def mark_paid(self, by_user=None):
        self.status = self.Status.PAID
        self.decided_at = self.decided_at or timezone.now()
        if by_user:
            self.decided_by = by_user
        self.save(update_fields=["status", "decided_at", "decided_by"])


# ----------------------------------------------------------------------
# Payslips + Payments + Schedules
# ----------------------------------------------------------------------
def _default_base_salary() -> Decimal:
    """Global fallback base salary (kept for historical migrations)."""
    return Decimal(getattr(settings, "WALLET_BASE_SALARY", "40000.00"))


class PayslipStatus(models.TextChoices):
    DRAFT = "DRAFT", "Prepared"
    SENT = "SENT", "Issued"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Cancelled"


class Payslip(models.Model):
    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="payslips",
    )
    agent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payslips")
    year = models.IntegerField()
    month = models.IntegerField()  # 1..12
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    employee_name = models.CharField(max_length=160, blank=True, default="")
    employee_role = models.CharField(max_length=120, blank=True, default="")
    employee_phone = models.CharField(max_length=60, blank=True, default="")
    employee_email = models.EmailField(blank=True, default="")
    employee_identifier = models.CharField(max_length=80, blank=True, default="")

    # Components
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=_default_base_salary)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    bonuses_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    other_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    payment_method_label = models.CharField(max_length=80, blank=True, default="")

    # Totals
    gross = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # Delivery
    reference = models.CharField(max_length=24, editable=False, blank=True, default="", db_index=True)
    email_to = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=12, choices=PayslipStatus.choices, default=PayslipStatus.DRAFT)
    sent_to_email = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    issued_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payslips_created")

    # Optional PDF
    pdf = models.FileField(upload_to="payslips/", null=True, blank=True)

    # Machine info (calculation inputs, preview lines, etc.)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("agent", "year", "month")]
        indexes = [
            models.Index(fields=["business", "year", "month"]),
            models.Index(fields=["agent", "year", "month"]),
            models.Index(fields=["employee_name"]),
            models.Index(fields=["status"]),
        ]
        ordering = ("-issued_at",)

    def __str__(self) -> str:
        return f"{self.reference or 'NOREF'} - {self.display_employee_name} - {self.year}-{self.month:02d}"

    @property
    def display_employee_name(self) -> str:
        if self.employee_name:
            return self.employee_name
        if self.agent_id:
            full = self.agent.get_full_name()
            return full or self.agent.get_username()
        return "Employee"

    @property
    def display_status(self) -> str:
        if self.status == PayslipStatus.DRAFT:
            return "Prepared"
        if self.status == PayslipStatus.SENT:
            return "Issued"
        if self.status == PayslipStatus.PAID:
            return "Paid"
        if self.status == PayslipStatus.FAILED:
            return "Cancelled"
        return str(self.status or "Prepared").title()

    def _make_reference(self) -> str:
        ts = timezone.now().strftime("%y%m%d%H%M%S")
        return f"PS{ts}{(self.agent_id or 0):04d}"[-24:]

    def save(self, *args, **kwargs):
        if not self.reference:
            ref = self._make_reference()
            while Payslip.objects.filter(reference=ref).exists():
                ref = self._make_reference()
            self.reference = ref
        if not self.email_to and self.employee_email:
            self.email_to = self.employee_email
        if not self.employee_name and self.agent_id:
            self.employee_name = self.agent.get_full_name() or self.agent.get_username()
        if not self.employee_email and self.agent_id and getattr(self.agent, "email", ""):
            self.employee_email = self.agent.email
        if not self.email_to and self.agent_id and getattr(self.agent, "email", ""):
            self.email_to = self.agent.email

        gross = q2((self.base_salary or 0) + (self.commission or 0) + (self.bonuses_fees or 0) + (self.other_earnings or 0))
        net = q2(gross - (self.deductions or 0))
        self.gross = gross
        self.net = net

        # Normalize
        self.base_salary = q2(self.base_salary)
        self.commission = q2(self.commission)
        self.bonuses_fees = q2(self.bonuses_fees)
        self.other_earnings = q2(self.other_earnings)
        self.deductions = q2(self.deductions)
        self.gross = q2(self.gross)
        self.net = q2(self.net)

        super().save(*args, **kwargs)


class PaymentMethod(models.TextChoices):
    NB = "NB", "National Bank (future)"
    SB = "SB", "Standard Bank (future)"
    AM = "AM", "Airtel Money (future)"
    MANUAL = "MANUAL", "Manual"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class Payment(models.Model):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.MANUAL)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    txn_ref = models.CharField(max_length=48, blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments_processed")
    status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["method"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_method_display()} Â· {self.amount} Â· {self.status}"

    def save(self, *args, **kwargs):
        self.amount = q2(self.amount)
        super().save(*args, **kwargs)


class PayoutSchedule(models.Model):
    """Monthly auto-send schedule for payslips."""
    name = models.CharField(max_length=120)
    users = models.ManyToManyField(User, related_name="payout_schedules", blank=True)
    day_of_month = models.PositiveSmallIntegerField(default=28)  # 1..31
    at_hour = models.PositiveSmallIntegerField(default=9)        # 0..23
    active = models.BooleanField(default=True)

    last_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payout_schedules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} Â· day {self.day_of_month} @ {self.at_hour:02d}:00"


# ----------------------------------------------------------------------
# Admin Purchase Orders
# ----------------------------------------------------------------------
class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "Prepared"
    SENT = "sent", "Sent"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class AdminPurchaseOrder(models.Model):
    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="admin_purchase_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_pos_created")

    supplier_name = models.CharField(max_length=120, blank=True)
    supplier_email = models.EmailField(blank=True)
    supplier_phone = models.CharField(max_length=40, blank=True)
    agent_name = models.CharField(max_length=120, blank=True)

    notes = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=255, blank=True, default="")
    expected_delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="MWK")

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    pdf = models.FileField(upload_to="purchase_orders/", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["supplier_name"]),
        ]

    def __str__(self) -> str:
        return f"PO-{self.id} Â· {self.supplier_name or 'Supplier'} Â· {self.total} {self.currency}"

    def recompute_totals(self, save: bool = True):
        agg = self.items.aggregate(s=Sum("line_total"))
        subtotal = agg["s"] or Decimal("0.00")
        self.subtotal = q2(subtotal)
        self.tax = q2(self.tax or Decimal("0.00"))
        self.total = q2(self.subtotal + self.tax)
        if save:
            self.save(update_fields=["subtotal", "tax", "total"])


class AdminPurchaseOrderItem(models.Model):
    po = models.ForeignKey(AdminPurchaseOrder, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["po"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self) -> str:
        return f"{self.product} Ã— {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.line_total and self.quantity and self.unit_price is not None:
            self.line_total = q2(Decimal(self.quantity) * Decimal(self.unit_price))
        else:
            self.line_total = q2(self.line_total)
        self.unit_price = q2(self.unit_price)
        super().save(*args, **kwargs)


