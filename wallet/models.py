# wallet/models.py
from __future__ import annotations
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

# Use AUTH_USER_MODEL string for FKs to avoid import cycles
User = settings.AUTH_USER_MODEL


# ----------------------------
# Wallet / Budgets / Attendance
# ----------------------------
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


class WalletTransaction(models.Model):
    """
    Signed amounts in MWK.
    - Agent ledger: positives increase agent balance; negatives reduce it.
    - Company ledger: mirror of company cash flow (optional to display).
    """
    ledger = models.CharField(max_length=16, choices=Ledger.choices, default=Ledger.AGENT)
    agent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_txns")
    type = models.CharField(max_length=20, choices=TxnType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # signed
    note = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=64, blank=True, default="")
    effective_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_wallet_txns")
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["ledger", "agent", "effective_date"]),
            models.Index(fields=["type"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.agent_id or "company"
        return f"{self.type} {self.amount} → {who} {self.effective_date}"


class SalesTarget(models.Model):
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sales_targets")
    year = models.IntegerField()
    month = models.IntegerField()  # 1..12
    target_count = models.IntegerField(default=0)
    bonus_per_extra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("5000.00"))

    class Meta:
        unique_together = [("agent", "year", "month")]

    def __str__(self) -> str:
        return f"{self.agent_id} · {self.year}-{self.month:02d}"


class AttendanceLog(models.Model):
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance_logs")
    date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)  # None if absent
    weekend = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = [("agent", "date")]

    def __str__(self) -> str:
        return f"{self.agent_id} · {self.date} · {'in' if self.check_in else 'absent'}"


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

    def __str__(self) -> str:
        return f"{self.title} · {self.agent_id} · {self.amount} · {self.status}"


# ----------------------------
# Payslips + Payments + Schedules
# ----------------------------

def _default_base_salary() -> Decimal:
    """Global fallback base salary (can be overridden per user in the future)."""
    return Decimal(getattr(settings, "WALLET_BASE_SALARY", "40000.00"))


class PayslipStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SENT = "SENT", "Sent"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"


class Payslip(models.Model):
    # Core identity (keep year/month for compatibility and uniqueness)
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payslips")
    year = models.IntegerField()
    month = models.IntegerField()  # 1..12

    # Components
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=_default_base_salary)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    bonuses_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # +/- adjustments
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))    # positive number

    # Totals (denormalized for quick display/export)
    gross = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # Delivery + bookkeeping
    reference = models.CharField(  # app-level uniqueness; indexed to search quickly
        max_length=24, editable=False, blank=True, default="", db_index=True
    )
    email_to = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=12, choices=PayslipStatus.choices, default=PayslipStatus.DRAFT)
    sent_to_email = models.BooleanField(default=False)  # legacy flag – retained
    sent_at = models.DateTimeField(null=True, blank=True)

    issued_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payslips_created")

    # Optional PDF for record keeping
    pdf = models.FileField(upload_to="payslips/", null=True, blank=True)

    # Free-form machine info (calculation inputs, preview lines, etc.)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("agent", "year", "month")]
        indexes = [
            models.Index(fields=["agent", "year", "month"]),
            models.Index(fields=["status"]),
        ]
        ordering = ("-issued_at",)

    def __str__(self) -> str:
        return f"{self.reference or 'NOREF'} · {self.agent_id} · {self.year}-{self.month:02d}"

    def _make_reference(self) -> str:
        ts = timezone.now().strftime("%y%m%d%H%M%S")
        return f"PS{ts}{(self.agent_id or 0):04d}"[-24:]

    def save(self, *args, **kwargs):
        # Auto-fill reference and email if missing
        if not self.reference:
            ref = self._make_reference()
            # Guard against rare collisions (app-level check)
            while Payslip.objects.filter(reference=ref).exists():
                ref = self._make_reference()
            self.reference = ref
        if not self.email_to and hasattr(self, "agent") and getattr(self.agent, "email", ""):
            self.email_to = self.agent.email

        # Compute totals if components present and totals not set
        if (self.gross is None or self.gross == 0) and (
            self.base_salary or self.commission or self.bonuses_fees or self.deductions
        ):
            gross = (self.base_salary or 0) + (self.commission or 0) + (self.bonuses_fees or 0)
            net = gross - (self.deductions or 0)
            self.gross = gross
            self.net = net

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
    """
    Records how a payslip was actually paid (future integrations can update this).
    """
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
        return f"{self.get_method_display()} · {self.amount} · {self.status}"


class PayoutSchedule(models.Model):
    """
    Monthly auto-send schedule.
    At `day_of_month` and `at_hour` (local time), send payslips for the PREVIOUS calendar month
    to the selected users. A Celery beat task should call the runner daily/hourly.
    """
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
        return f"{self.name} · day {self.day_of_month} @ {self.at_hour:02d}:00"


# ----------------------------
# Admin Purchase Orders (Stock List → Place Order → Invoice)
# ----------------------------
class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class AdminPurchaseOrder(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_pos_created")

    # Who we’re ordering from / for
    supplier_name = models.CharField(max_length=120, blank=True)
    supplier_email = models.EmailField(blank=True)
    supplier_phone = models.CharField(max_length=40, blank=True)  # WhatsApp-friendly
    agent_name = models.CharField(max_length=120, blank=True)     # if ordering for a specific agent

    notes = models.TextField(blank=True)
    currency = models.CharField(max_length=8, default="MWK")

    # Totals
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["supplier_name"]),
        ]

    def __str__(self) -> str:
        return f"PO-{self.id} · {self.supplier_name or 'Supplier'} · {self.total} {self.currency}"

    def recompute_totals(self, save: bool = True):
        agg = self.items.aggregate(s=models.Sum("line_total"))
        subtotal = agg["s"] or Decimal("0.00")
        self.subtotal = subtotal
        # add VAT here if you want (e.g., 16.5%): self.tax = (subtotal * Decimal("0.165")).quantize(Decimal("0.01"))
        self.tax = self.tax or Decimal("0.00")
        self.total = self.subtotal + self.tax
        if save:
            self.save(update_fields=["subtotal", "tax", "total"])


class AdminPurchaseOrderItem(models.Model):
    po = models.ForeignKey(AdminPurchaseOrder, related_name="items", on_delete=models.CASCADE)
    # FK kept as a plain string to avoid import cycle; actual model in inventory
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)   # copied from inventory.OrderPrice at creation
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["po"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity}"

    def save(self, *args, **kwargs):
        # Compute line total if not provided
        if not self.line_total and self.quantity and self.unit_price is not None:
            self.line_total = (Decimal(self.quantity) * Decimal(self.unit_price)).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
