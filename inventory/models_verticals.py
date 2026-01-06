# inventory/models_verticals.py
"""
Models for non-phone verticals: Liquor, Gym, Clothing.
These models extend the base MerchProduct system with vertical-specific functionality.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business, Membership

User = settings.AUTH_USER_MODEL


# ==============================================================================
# LIQUOR MODELS
# ==============================================================================


class LiquorCategory(models.TextChoices):
    """Product categories for liquor store"""

    BEER = "beer", "Beer"
    CIDER = "cider", "Cider"
    SPIRITS = "spirits", "Spirits"
    WINE = "wine", "Wine"
    OTHER = "other", "Other"


class LiquorUnitType(models.TextChoices):
    """Unit types for liquor sales"""

    BOTTLE = "bottle", "Bottle"
    SHOT = "shot", "Shot"
    GLASS = "glass", "Glass"


class LiquorSaleType(models.TextChoices):
    """Type of liquor sale"""

    SALE = "sale", "Cash Sale"
    CREDIT = "credit", "Credit Sale"
    FREE = "free", "Free (Barman/Complimentary)"
    UNDECIDED = "undecided", "Undecided"


class LiquorShiftStatus(models.TextChoices):
    """Status of a shift"""

    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class LiquorShift(models.Model):
    """
    Represents a barman's work shift with opening and closing stock counts.
    Tracks all sales, credits, and stock variance during the shift.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_shifts", db_index=True)
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_shifts"
    )

    # Shift personnel
    barman = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="liquor_shifts_worked",
        help_text="Barman working this shift (null if user deleted)",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="liquor_shifts_created",
        help_text="User who created this shift (null if user deleted)",
    )

    # Timing
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Status
    status = models.CharField(
        max_length=10, choices=LiquorShiftStatus.choices, default=LiquorShiftStatus.OPEN, db_index=True
    )

    # Aggregated metrics (computed when shift closes)
    total_sales_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_cost_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_free_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    missing_stock_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Notes
    opening_notes = models.TextField(blank=True, default="")
    closing_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["business", "status", "-started_at"]),
            models.Index(fields=["barman", "-started_at"]),
            models.Index(fields=["business", "-started_at"]),
        ]

    def __str__(self):
        status_text = self.get_status_display()
        barman_name = getattr(self.barman, "username", "Unknown")
        date = self.started_at.strftime("%Y-%m-%d %H:%M")
        return f"Shift {self.id} - {barman_name} - {status_text} ({date})"

    def duration_hours(self) -> Optional[float]:
        """Calculate shift duration in hours"""
        if not self.ended_at:
            # Shift still open - calculate from now
            duration = timezone.now() - self.started_at
        else:
            duration = self.ended_at - self.started_at
        return duration.total_seconds() / 3600

    def is_stale(self) -> bool:
        """Check if shift is open but started more than 24 hours ago"""
        if self.status != LiquorShiftStatus.OPEN:
            return False
        hours_open = (timezone.now() - self.started_at).total_seconds() / 3600
        return hours_open > 24


class LiquorShiftStock(models.Model):
    """
    Snapshot of stock levels at the start or end of a shift.
    Each product gets two records: one at opening, one at closing.
    """

    shift = models.ForeignKey(LiquorShift, on_delete=models.CASCADE, related_name="stock_snapshots")
    product = models.ForeignKey(
        "inventory.MerchProduct", on_delete=models.CASCADE, related_name="shift_stock_snapshots"
    )

    # Stock counts
    bottles_count = models.IntegerField(default=0, help_text="Full bottles in stock")
    shots_count = models.IntegerField(default=0, help_text="Individual shots available (from open bottles)")

    # Snapshot timing
    snapshot_type = models.CharField(
        max_length=10, choices=[("opening", "Opening Stock"), ("closing", "Closing Stock")], db_index=True
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    # Adjustment tracking (if barman adjusts from system count)
    was_adjusted = models.BooleanField(default=False)
    adjustment_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["shift", "product"]
        indexes = [
            models.Index(fields=["shift", "snapshot_type"]),
            models.Index(fields=["product", "shift"]),
        ]
        unique_together = [("shift", "product", "snapshot_type")]

    def __str__(self):
        return f"{self.product.name} - {self.get_snapshot_type_display()} - Shift {self.shift_id}"

    def total_sellable_shots(self) -> int:
        """Calculate total sellable shots (from full bottles + loose shots)"""
        if not self.product.has_shots:
            return 0

        sellable_per_bottle = self.product.sellable_shots_per_bottle
        return (self.bottles_count * sellable_per_bottle) + self.shots_count


class LiquorStockAdjustment(models.Model):
    """
    Records stock adjustments for liquor products.
    Used for tracking barman shots, spillage, breakage, and other non-sale stock changes.
    """

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="liquor_stock_adjustments", db_index=True
    )
    product = models.ForeignKey(
        "inventory.MerchProduct", on_delete=models.CASCADE, related_name="liquor_stock_adjustments"
    )
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_stock_adjustments"
    )

    # Adjustment details
    quantity_change = models.IntegerField(help_text="Quantity change (positive for additions, negative for deductions)")
    reason = models.CharField(
        max_length=50,
        choices=[
            ("BARMAN_SHOTS", "Barman Shots (Staff Consumption)"),
            ("SPILLAGE", "Spillage"),
            ("BREAKAGE", "Breakage"),
            ("EXPIRED", "Expired"),
            ("THEFT", "Theft"),
            ("CORRECTION", "Stock Correction"),
            ("OTHER", "Other"),
        ],
        default="OTHER",
        db_index=True,
    )
    notes = models.TextField(blank=True, default="")

    # Metadata
    adjusted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_adjustments_made"
    )
    adjusted_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-adjusted_at"]
        indexes = [
            models.Index(fields=["business", "-adjusted_at"]),
            models.Index(fields=["business", "reason", "-adjusted_at"]),
            models.Index(fields=["product", "-adjusted_at"]),
        ]

    def __str__(self):
        sign = "+" if self.quantity_change >= 0 else ""
        return f"{self.product.name}: {sign}{self.quantity_change} ({self.get_reason_display()})"


class PaymentMethod(models.TextChoices):
    """Payment methods for sales"""

    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    MOBILE_MONEY = "mobile_money", "Mobile Money"


class LiquorSale(models.Model):
    """
    Records a sale of liquor product.
    Can be bottle or shot, cash or credit or free.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_sales", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="liquor_sales")

    # Shift tracking (nullable for legacy sales)
    shift = models.ForeignKey(
        LiquorShift, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales", db_index=True
    )

    # Sale details
    unit = models.CharField(max_length=10, choices=LiquorUnitType.choices, default=LiquorUnitType.BOTTLE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Cost tracking for profit calculation
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Cost per unit sold"
    )
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Payment type
    sale_type = models.CharField(max_length=10, choices=LiquorSaleType.choices, default=LiquorSaleType.SALE)
    is_credit = models.BooleanField(default=False, db_index=True)
    is_free = models.BooleanField(
        default=False, db_index=True, help_text="True for barman shots or complimentary drinks"
    )
    linked_credit = models.ForeignKey(
        "LiquorCredit", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales"
    )

    # Payment method (for cash mix tracking)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this sale",
    )

    # Payment Mix (for split payments across multiple methods)
    cash_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Amount paid in cash"
    )
    bank_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Amount paid via bank transfer"
    )
    mobile_money_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Amount paid via mobile money"
    )

    # Metadata
    sold_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_sales_made"
    )
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["business", "sale_type", "-sold_at"]),
            models.Index(fields=["is_credit", "-sold_at"]),
            models.Index(fields=["shift", "-sold_at"]),
            models.Index(fields=["business", "is_free", "-sold_at"]),
            models.Index(fields=["business", "payment_method", "-sold_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.quantity} {self.unit}) - {self.total_price}"

    @property
    def profit(self) -> Decimal:
        """Calculate profit on this sale"""
        return self.total_price - self.total_cost

    def save(self, *args, **kwargs):
        # Auto-calculate total if not set
        if not self.total_price:
            self.total_price = Decimal(self.quantity) * self.unit_price

        # Auto-calculate total cost if not set
        if not self.total_cost and self.unit_cost:
            self.total_cost = Decimal(self.quantity) * self.unit_cost

        # Sync is_credit and is_free with sale_type
        self.is_credit = self.sale_type == LiquorSaleType.CREDIT
        self.is_free = self.sale_type == LiquorSaleType.FREE

        # Handle payment mix: if all amounts are 0, default to cash = total_price
        payment_mix_total = self.cash_amount + self.bank_amount + self.mobile_money_amount
        if payment_mix_total == 0 and self.total_price > 0:
            # Default: entire amount is cash
            self.cash_amount = self.total_price
            self.payment_method = PaymentMethod.CASH
        elif payment_mix_total > 0:
            # Set payment_method based on which amount is largest (or "MIXED" if multiple)
            if self.cash_amount > 0 and self.bank_amount == 0 and self.mobile_money_amount == 0:
                self.payment_method = PaymentMethod.CASH
            elif self.bank_amount > 0 and self.cash_amount == 0 and self.mobile_money_amount == 0:
                self.payment_method = PaymentMethod.BANK
            elif self.mobile_money_amount > 0 and self.cash_amount == 0 and self.bank_amount == 0:
                self.payment_method = PaymentMethod.MOBILE_MONEY
            # If mixed, keep current payment_method or default to CASH

        super().save(*args, **kwargs)


class LiquorCreditStatus(models.TextChoices):
    """Status of credit record"""

    OPEN = "open", "Open"
    PARTIAL = "partial", "Partially Paid"
    SETTLED = "settled", "Settled"
    CANCELLED = "cancelled", "Cancelled"


class LiquorCredit(models.Model):
    """
    Tracks credit given to customers.
    Can be linked to an existing sale or created fresh.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_credits", db_index=True)

    # Customer info
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    customer_description = models.TextField(
        blank=True,
        default="",
        help_text="Physical description or identifying info (e.g., 'short guy, red jacket, comes Fridays')",
    )
    customer_photo = models.ImageField(
        upload_to="liquor/customer_photos/", null=True, blank=True, help_text="Optional photo to help identify customer"
    )

    # Amount details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Status tracking
    status = models.CharField(
        max_length=10, choices=LiquorCreditStatus.choices, default=LiquorCreditStatus.OPEN, db_index=True
    )

    # Linked sale (if converted from sale)
    related_sale = models.ForeignKey(
        LiquorSale, null=True, blank=True, on_delete=models.SET_NULL, related_name="credits"
    )

    # Metadata
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_credits_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_credits_settled"
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "-created_at"]),
            models.Index(fields=["customer_name"]),
        ]

    def __str__(self):
        return f"{self.customer_name} - {self.amount} ({self.status})"

    @property
    def balance(self):
        """Remaining balance to be paid"""
        return self.amount - self.amount_paid

    def update_status(self):
        """Update status based on amount paid"""
        if self.amount_paid >= self.amount:
            self.status = LiquorCreditStatus.SETTLED
            if not self.settled_at:
                self.settled_at = timezone.now()
        elif self.amount_paid > Decimal("0.00"):
            self.status = LiquorCreditStatus.PARTIAL
        else:
            self.status = LiquorCreditStatus.OPEN
        self.save(update_fields=["status", "settled_at"])


class LiquorCreditPaymentStatus(models.TextChoices):
    """Status of credit payment approval"""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class LiquorCreditPayment(models.Model):
    """
    Records a payment towards a credit.
    Bartenders must upload proof; managers can approve without proof.
    """

    credit = models.ForeignKey(LiquorCredit, on_delete=models.CASCADE, related_name="payments")

    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    transaction_id = models.CharField(max_length=100, blank=True, default="")
    proof_file = models.FileField(upload_to="liquor/credit_proofs/", null=True, blank=True)

    # Approval workflow
    status = models.CharField(
        max_length=10,
        choices=LiquorCreditPaymentStatus.choices,
        default=LiquorCreditPaymentStatus.PENDING,
        db_index=True,
    )

    # Metadata
    paid_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_payments_submitted"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Review tracking
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_payments_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credit", "-created_at"]),
        ]

    def __str__(self):
        return f"Payment {self.amount} for {self.credit.customer_name} - {self.status}"

    def approve(self, by_user):
        """Approve payment and update credit"""
        self.status = LiquorCreditPaymentStatus.APPROVED
        self.reviewed_by = by_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        # Update credit amount paid
        self.credit.amount_paid += self.amount
        self.credit.save(update_fields=["amount_paid"])
        self.credit.update_status()

    def reject(self, by_user, reason=""):
        """Reject payment"""
        self.status = LiquorCreditPaymentStatus.REJECTED
        self.reviewed_by = by_user
        self.reviewed_at = timezone.now()
        self.review_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_reason"])


class LiquorStockEditRequestStatus(models.TextChoices):
    """Status of stock edit request"""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class LiquorStockEditRequest(models.Model):
    """
    Bartenders cannot edit stock directly.
    They must submit requests that managers approve.
    """

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="liquor_stock_requests", db_index=True
    )
    product = models.ForeignKey(
        "inventory.MerchProduct", on_delete=models.CASCADE, related_name="liquor_stock_requests"
    )

    # Requested changes (stored as JSON)
    requested_changes = models.JSONField(default=dict, help_text="JSON of fields to change")
    reason = models.TextField(blank=True, default="")

    # Approval workflow
    status = models.CharField(
        max_length=10,
        choices=LiquorStockEditRequestStatus.choices,
        default=LiquorStockEditRequestStatus.PENDING,
        db_index=True,
    )

    # Metadata
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="liquor_stock_requests_submitted")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Review tracking
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_stock_requests_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "-created_at"]),
            models.Index(fields=["product", "-created_at"]),
        ]

    def __str__(self):
        return f"Stock edit request for {self.product.name} - {self.status}"


# ==============================================================================
# GYM MODELS
# ==============================================================================


class GymMemberStatus(models.TextChoices):
    """Membership payment status"""

    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment"
    ACTIVE = "ACTIVE", "Active"
    BEHIND_SCHEDULE = "BEHIND_SCHEDULE", "Behind Schedule"
    EXPIRED = "EXPIRED", "Expired"


class GymTrainer(models.Model):
    """
    Gym trainer who can be assigned to members.
    Can optionally be linked to a user account for wallet access.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="gym_trainers", db_index=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    # Optional linked user for wallet/login access
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gym_trainer_profile",
        help_text="Linked user account for trainer (enables wallet access)",
    )

    # Metadata
    joined_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")

    class Meta:
        unique_together = [("business", "name")]
        ordering = ["name"]
        indexes = [
            models.Index(fields=["business", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.business.name})"

    def total_fees_earned(self) -> Decimal:
        """Calculate total trainer fees earned from all payments"""
        from django.db.models import Sum

        total = GymPayment.objects.filter(trainer=self, is_active=True).aggregate(total=Sum("trainer_fee"))["total"]
        return total or Decimal("0.00")

    def payment_count(self) -> int:
        """Count number of payments with this trainer"""
        return GymPayment.objects.filter(trainer=self, is_active=True).count()


class GymMember(models.Model):
    """
    Gym member with 30-day rolling membership.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="gym_members", db_index=True)

    # Member info
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    # Unique identifiers for member
    member_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="Human-friendly member number (e.g., EW-000123)",
    )
    qr_token = models.CharField(
        max_length=64,
        blank=True,
        default="",
        unique=True,
        db_index=True,
        help_text="Stable unique QR token for scanning (UUID-based)",
    )
    qr_uuid = models.UUIDField(
        unique=True,
        db_index=True,
        editable=False,
        default=uuid.uuid4,
        help_text="Immutable UUID for QR code scanning (preferred over qr_token)",
    )

    # Legacy member_code (kept for backward compatibility)
    member_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="Legacy barcode/QR code (deprecated, use qr_token)",
    )

    # Trainer assignment
    trainer = models.ForeignKey(
        GymTrainer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
        help_text="Assigned trainer for this member",
    )

    # Trainer and fees (snapshot at signup/renewal)
    has_trainer = models.BooleanField(default=False, help_text="Whether this member has a trainer")
    membership_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Snapshot of membership fee at signup/renewal"
    )
    trainer_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Snapshot of trainer fee if has_trainer=True"
    )

    # Membership period (current/active period)
    last_payment_date = models.DateField(null=True, blank=True, help_text="Date of most recent payment")
    membership_start = models.DateField(null=True, blank=True, help_text="Start date of current membership period")
    membership_end = models.DateField(
        null=True, blank=True, db_index=True, help_text="End date of current membership period (start + 30 days)"
    )
    status = models.CharField(
        max_length=20,
        choices=GymMemberStatus.choices,
        default=GymMemberStatus.PENDING_PAYMENT,
        db_index=True,
        help_text="Current membership status",
    )

    # Membership status
    is_active = models.BooleanField(default=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    # Metadata
    joined_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_members_archived"
    )

    notes = models.TextField(blank=True, default="")

    # Gamification fields
    streak_days = models.IntegerField(default=0, help_text="Current check-in streak (consecutive days)")
    last_checkin_date = models.DateField(
        null=True, blank=True, help_text="Date of last check-in (for streak calculation)"
    )
    monthly_checkins = models.IntegerField(default=0, help_text="Total check-ins this month")
    total_checkins = models.IntegerField(default=0, help_text="Total lifetime check-ins")
    badge_level = models.CharField(
        max_length=20,
        choices=[
            ("none", "No Badge"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
            ("platinum", "Platinum"),
        ],
        default="none",
        help_text="Achievement badge based on check-in consistency",
    )

    class Meta:
        unique_together = [("business", "phone"), ("business", "member_code")]
        ordering = ["-joined_at"]
        indexes = [
            models.Index(fields=["business", "is_active", "is_archived"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["member_code"]),
            models.Index(fields=["member_number"]),
            models.Index(fields=["qr_token"]),
            models.Index(fields=["qr_uuid"]),
            models.Index(fields=["badge_level"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def save(self, *args, **kwargs):
        """Auto-generate member_number, qr_token, qr_uuid, and legacy member_code if not present"""
        if not self.member_number and self.business_id:
            self.member_number = self._generate_unique_member_number()
        if not self.qr_token:
            self.qr_token = self._generate_unique_qr_token()
        # Generate qr_uuid if not present (from qr_token or new UUID)
        if not self.qr_uuid:
            import uuid

            if self.qr_token:
                try:
                    # Try to convert existing qr_token to UUID
                    self.qr_uuid = uuid.UUID(self.qr_token)
                except (ValueError, AttributeError):
                    # If qr_token is not a valid UUID, generate new UUID
                    self.qr_uuid = uuid.uuid4()
                    # Update qr_token to match
                    if not self.qr_token:
                        self.qr_token = str(self.qr_uuid)
            else:
                # Generate new UUID
                self.qr_uuid = uuid.uuid4()
                self.qr_token = str(self.qr_uuid)
        # Legacy: also generate member_code for backward compatibility
        if not self.member_code and self.business_id:
            self.member_code = self._generate_unique_member_code()
        super().save(*args, **kwargs)

    def _generate_unique_member_number(self) -> str:
        """
        Generate a unique human-friendly member number.
        Format: EW-000123 (location prefix + sequential number)
        """
        # Try to get location prefix from business
        prefix = "GYM"
        try:
            if hasattr(self.business, "name"):
                # Use first 2-3 letters of business name as prefix
                business_name = self.business.name.upper().replace(" ", "")
                prefix = business_name[:3] if len(business_name) >= 3 else business_name[:2]
        except Exception:
            pass

        # Find the highest existing member number for this business
        import re

        from django.db.models import Max

        existing_members = GymMember.objects.filter(
            business=self.business, member_number__startswith=f"{prefix}-"
        ).exclude(member_number="")

        max_number = 0
        for member in existing_members:
            try:
                # Extract number from format "PREFIX-XXXXXX"
                match = re.search(r"-(\d+)$", member.member_number)
                if match:
                    num = int(match.group(1))
                    if num > max_number:
                        max_number = num
            except Exception:
                continue

        # Generate next number
        next_number = max_number + 1
        return f"{prefix}-{next_number:06d}"

    def _generate_unique_qr_token(self) -> str:
        """
        Generate a stable unique QR token using UUID.
        This token is used for QR code scanning and is globally unique.
        """
        import uuid

        return str(uuid.uuid4())

    def _generate_unique_member_code(self) -> str:
        """
        Generate a unique member code in format: GYM-XXXXXX
        Retries up to 20 times to avoid collisions.
        LEGACY: Kept for backward compatibility.
        """
        import random

        for _ in range(20):
            code = f"GYM-{random.randint(100000, 999999)}"
            if not GymMember.objects.filter(business=self.business, member_code=code).exists():
                return code
        # Ultra-rare fallback
        import uuid

        return f"GYM-{uuid.uuid4().hex[:6].upper()}"

    def get_qr_code_data_url(self) -> str:
        """
        Get QR code as base64 data URL for this member.
        Uses qr_token (preferred) or falls back to member_code for legacy support.
        """
        token = self.qr_token or self.member_code
        if not token:
            return ""
        from inventory.utils_gym_barcode import generate_member_qr_code_url

        return generate_member_qr_code_url(token)

    # ==============================================================================
    # CENTRALIZED MEMBERSHIP CALCULATION PROPERTIES
    # ==============================================================================

    @property
    def duration_days(self) -> int:
        """
        Get the duration of the membership in days.
        Returns the actual granted days based on the current membership period.
        """
        if self.membership_start and self.membership_end:
            # Calculate actual days in the current period (inclusive)
            return (self.membership_end - self.membership_start).days + 1

        # Fallback to 30 if no membership exists
        from inventory.utils_gym import GYM_MEMBERSHIP_DAYS

        return GYM_MEMBERSHIP_DAYS

    @property
    def days_used(self) -> int:
        """
        Calculate how many days have been used in the current membership period.

        Returns 0 if:
        - No membership exists (no membership_start)
        - Today is before the membership start date (negative days clamped to 0)

        Returns duration_days if:
        - Today is after the membership has expired (capped at duration_days)

        Otherwise returns the number of days elapsed since membership_start.
        """
        if not self.membership_start:
            return 0

        today = timezone.now().date()
        used = (today - self.membership_start).days

        # Clamp to valid range [0, duration_days]
        if used < 0:
            used = 0
        if used > self.duration_days:
            used = self.duration_days

        return used

    @property
    def days_left(self) -> int:
        """
        Calculate remaining days in the current membership period (inclusive).

        Uses membership_end date to calculate remaining days accurately.

        Returns:
        - N when membership_end is (today + N - 1) days away
        - 1 when membership_end is today (last day is inclusive)
        - 0 when membership has expired or never existed

        Examples:
        - Today = Jan 1, membership_end = Jan 30: returns 30 days
        - Today = Jan 30, membership_end = Jan 30: returns 1 day
        - Today = Jan 31, membership_end = Jan 30: returns 0 days
        """
        if not self.membership_end:
            return 0

        today = timezone.now().date()
        if self.membership_end < today:
            return 0

        # Inclusive calculation: (end - today).days + 1
        return (self.membership_end - today).days + 1

    @property
    def days_left_display(self) -> str:
        """
        Get a formatted string for displaying days left.

        Returns:
        - "30 / 30 days" on payment day
        - "29 / 30 days" the day after
        - "0 / 30 days" when expired
        """
        return f"{self.days_left} / {self.duration_days} days"

    @property
    def next_payment_date_property(self):
        """
        Get the next payment due date.

        Business rule: Next payment is due exactly duration_days after the last payment.

        Returns:
        - Date when next payment is due (last_payment_date + duration_days)
        - None if member has never paid

        Example:
        - Last payment: Jan 1
        - Duration: 30 days
        - Membership period: Jan 1 - Jan 30
        - Next payment due: Jan 31
        """
        if not self.last_payment_date:
            return None
        return self.last_payment_date + timedelta(days=self.duration_days)

    @property
    def is_active_membership(self) -> bool:
        """
        Check if the member has an active membership.

        Active means:
        - Has made a payment (last_payment_date exists)
        - AND has days remaining (days_left > 0)

        Returns:
        - True if membership is active
        - False if expired or never existed
        """
        return bool(self.last_payment_date and self.days_left > 0)

    @property
    def status_label(self) -> str:
        """
        Get a human-readable status label for display.

        Returns:
        - "Active" if membership is active
        - "No membership" if never paid or expired
        """
        if self.is_active_membership:
            return "Active"
        return "No membership"

    # ==============================================================================
    # LEGACY PROPERTIES (kept for backward compatibility)
    # ==============================================================================

    @property
    def current_payment(self):
        """
        Get the current active payment that covers today's date.
        Returns the most recent GymPayment whose period includes today.
        """
        today = timezone.localdate()
        return (
            self.payments.filter(start_date__lte=today, end_date__gte=today, is_active=True)
            .order_by("-end_date")
            .first()
        )

    @property
    def is_active_today(self):
        """
        Check if member has an active payment covering today.
        A member is ACTIVE if they have at least one GymPayment whose period covers today.
        """
        return self.current_payment is not None

    @property
    def days_left_current(self) -> int:
        """
        Calculate days left based on current_payment.
        Returns the number of days remaining (inclusive) in the current payment period.
        If no current payment exists, returns 0.

        This is the correct way to calculate days left based on GymPayment records.
        Use this instead of days_left() for accurate results.

        FIXED: Now caps at duration_days to prevent "31 / 30 days" bug.

        DEPRECATED: Use days_left property instead for the new centralized logic.
        """
        from inventory.utils_gym import GYM_MEMBERSHIP_DAYS, compute_membership_days

        payment = self.current_payment
        if not payment:
            return 0

        today = timezone.localdate()
        # Use the centralized helper function that caps days_left at duration
        days_left, _ = compute_membership_days(payment.start_date, GYM_MEMBERSHIP_DAYS, today)
        return days_left

    def days_left_legacy(self) -> int:
        """
        DEPRECATED: Old days_left calculation based on membership_end.
        Use the days_left property instead for accurate results.

        Calculate days left in membership based on membership_end date (inclusive).

        For a new member with membership ending in 29 days, this returns 30
        (today + 29 future days = 30 days total).

        This method is kept for backward compatibility.
        """
        if not self.membership_end:
            return 0

        today = timezone.now().date()
        # Inclusive counting: if membership_end is today, return 1 (not 0)
        days = (self.membership_end - today).days + 1
        return max(0, days)

    def days_attended(self) -> int:
        """Calculate days attended in current membership window"""
        if not self.membership_start or not self.membership_end:
            return 0

        # Count unique dates member checked in during current membership period
        return (
            self.checkins.filter(timestamp__date__gte=self.membership_start, timestamp__date__lte=self.membership_end)
            .dates("timestamp", "day")
            .count()
        )

    def next_payment_date(self):
        """
        Return the next payment due date.

        Business rule: Next payment is due exactly 30 days after the last payment.
        For a membership starting Jan 1, ending Jan 30, next payment is due Jan 31.

        Returns:
            Date when next payment is due, or None if member has never paid
        """
        from inventory.utils_gym import GYM_MEMBERSHIP_DAYS, compute_next_payment_date

        if not self.last_payment_date:
            return None

        return compute_next_payment_date(self.last_payment_date, GYM_MEMBERSHIP_DAYS)

    def membership_status(self) -> str:
        """
        Return human-readable membership status.

        DEPRECATED: Use get_membership_status() from utils_gym for accurate status.
        This method is kept for backward compatibility.
        """
        if self.status == GymMemberStatus.ACTIVE:
            return "Active"
        elif self.status == GymMemberStatus.PENDING_PAYMENT:
            return "Pending Payment"
        elif self.status == GymMemberStatus.BEHIND_SCHEDULE:
            return "Behind Schedule"
        elif self.status == GymMemberStatus.EXPIRED:
            return "Expired"
        return "Unknown"

    def get_status(self):
        """
        Get accurate membership status using the single source of truth.

        Returns MembershipStatus dict from utils_gym.get_membership_status().
        Use this instead of days_left() or membership_status() for accurate results.
        """
        from inventory.utils_gym import get_membership_status

        return get_membership_status(self)

    def update_status(self):
        """Update status based on membership dates"""
        if not self.membership_start or not self.membership_end:
            self.status = GymMemberStatus.PENDING_PAYMENT
        else:
            today = timezone.now().date()
            if today <= self.membership_end:
                self.status = GymMemberStatus.ACTIVE
            else:
                # Membership has expired
                self.status = GymMemberStatus.BEHIND_SCHEDULE
        self.save(update_fields=["status"])

    def set_paid(self, payment_date=None, membership_fee=None, trainer_fee=None, paid_by=None, amount=None):
        """
        Mark member as paid and set prorated membership period based on amount.
        This is the core business logic for membership activation/renewal.

        Args:
            payment_date: Date of payment (defaults to today)
            membership_fee: Membership fee to snapshot (optional)
            trainer_fee: Trainer fee to snapshot (optional)
            paid_by: User who processed the payment
            amount: Total payment amount for proration calculation (if None, uses membership_fee + trainer_fee)
        """
        from datetime import timedelta

        from inventory.utils_gym import calculate_membership_period

        if payment_date is None:
            payment_date = timezone.now().date()

        # Calculate total amount
        if amount is None:
            total_amount = (membership_fee or self.membership_fee or Decimal("0.00")) + (
                trainer_fee or self.trainer_fee or Decimal("0.00")
            )
        else:
            total_amount = amount

        # Calculate prorated membership period with auto-extension
        new_start, new_end, days_granted = calculate_membership_period(
            amount=total_amount, member=self, start_date=payment_date, today=payment_date
        )

        # Update member fields
        self.last_payment_date = payment_date
        self.membership_start = new_start
        self.membership_end = new_end
        self.status = GymMemberStatus.ACTIVE

        # Update fees if provided
        if membership_fee is not None:
            self.membership_fee = membership_fee
        if trainer_fee is not None:
            self.trainer_fee = trainer_fee

        self.save(
            update_fields=[
                "last_payment_date",
                "membership_start",
                "membership_end",
                "status",
                "membership_fee",
                "trainer_fee",
            ]
        )

        # Create a payment record
        if total_amount > 0:
            GymPayment.objects.create(
                member=self,
                amount=total_amount,
                start_date=new_start,
                end_date=new_end,
                paid_by=paid_by,
                notes=f"{'With trainer' if self.has_trainer else 'No trainer'} - {days_granted} days",
            )

    def archive(self, by_user):
        """Archive this member"""
        self.is_archived = True
        self.is_active = False
        self.archived_at = timezone.now()
        self.archived_by = by_user
        self.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])

    def get_qr_code_data_url(self):
        """
        Generate a QR code as a data URL for this member.
        Returns base64 encoded PNG image that can be used directly in <img src="">
        """
        if not self.member_code:
            return None

        try:
            import base64
            import io

            import qrcode

            # Create QR code with member code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(self.member_code)
            qr.make(fit=True)

            # Generate image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64 data URL
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            img_str = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/png;base64,{img_str}"
        except ImportError:
            # qrcode library not installed
            return None
        except Exception:
            # Any other error in QR generation
            return None

    # ==============================================================================
    # GAMIFICATION METHODS
    # ==============================================================================

    def update_checkin_stats(self, checkin_date=None):
        """
        Update gamification stats after a check-in.
        Updates: streak, monthly count, total count, badge level.

        Args:
            checkin_date: Date of check-in (defaults to today)
        """
        from datetime import date, timedelta

        if checkin_date is None:
            checkin_date = timezone.now().date()

        # Update streak
        if self.last_checkin_date:
            days_since_last = (checkin_date - self.last_checkin_date).days
            if days_since_last == 1:
                # Consecutive day - increment streak
                self.streak_days += 1
            elif days_since_last == 0:
                # Same day - don't update streak
                pass
            else:
                # Streak broken - reset to 1
                self.streak_days = 1
        else:
            # First check-in
            self.streak_days = 1

        # Update monthly check-ins (reset if new month)
        if self.last_checkin_date:
            if self.last_checkin_date.month != checkin_date.month or self.last_checkin_date.year != checkin_date.year:
                # New month - reset
                self.monthly_checkins = 1
            else:
                # Same month - increment
                self.monthly_checkins += 1
        else:
            self.monthly_checkins = 1

        # Update total check-ins
        self.total_checkins += 1

        # Update last check-in date
        self.last_checkin_date = checkin_date

        # Calculate badge level
        self.badge_level = self._calculate_badge_level()

        # Save changes
        self.save(
            update_fields=["streak_days", "last_checkin_date", "monthly_checkins", "total_checkins", "badge_level"]
        )

    def _calculate_badge_level(self):
        """
        Calculate badge level based on check-in metrics.

        Badge criteria:
        - Bronze: 10+ total check-ins OR 3+ day streak
        - Silver: 30+ total check-ins OR 7+ day streak
        - Gold: 60+ total check-ins OR 14+ day streak OR 15+ monthly check-ins
        - Platinum: 100+ total check-ins OR 30+ day streak OR 20+ monthly check-ins
        """
        if self.total_checkins >= 100 or self.streak_days >= 30 or self.monthly_checkins >= 20:
            return "platinum"
        elif self.total_checkins >= 60 or self.streak_days >= 14 or self.monthly_checkins >= 15:
            return "gold"
        elif self.total_checkins >= 30 or self.streak_days >= 7:
            return "silver"
        elif self.total_checkins >= 10 or self.streak_days >= 3:
            return "bronze"
        else:
            return "none"

    def get_badge_display(self):
        """Get display info for badge"""
        badges = {
            "none": {"label": "No Badge", "color": "secondary", "icon": ""},
            "bronze": {"label": "Bronze Member", "color": "warning", "icon": "🥉"},
            "silver": {"label": "Silver Member", "color": "secondary", "icon": "🥈"},
            "gold": {"label": "Gold Member", "color": "warning", "icon": "🥇"},
            "platinum": {"label": "Platinum Member", "color": "primary", "icon": "💎"},
        }
        return badges.get(self.badge_level, badges["none"])

    def get_level_display(self):
        """Get level based on lifetime check-ins: 0-9 Bronze, 10-29 Silver, 30+ Gold"""
        if self.total_checkins >= 30:
            return {"name": "Gold", "icon": "🥇", "color": "warning"}
        elif self.total_checkins >= 10:
            return {"name": "Silver", "icon": "🥈", "color": "secondary"}
        elif self.total_checkins > 0:
            return {"name": "Bronze", "icon": "🥉", "color": "warning"}
        else:
            return {"name": "Newbie", "icon": "🌱", "color": "info"}

    def get_gamification_badges(self):
        """Get list of achievement badges for member detail page"""
        badges = []

        # On Fire: streak >= 5
        if self.streak_days >= 5:
            badges.append(
                {"name": "On Fire", "icon": "🔥", "color": "danger", "description": f"{self.streak_days}-day streak!"}
            )

        # Consistent: >= 12 check-ins this month
        if self.monthly_checkins >= 12:
            badges.append(
                {
                    "name": "Consistent",
                    "icon": "⭐",
                    "color": "warning",
                    "description": f"{self.monthly_checkins} check-ins this month",
                }
            )

        # Newbie: first week (joined within last 7 days)
        if self.joined_at:
            from datetime import timedelta

            days_since_join = (timezone.now().date() - self.joined_at.date()).days
            if days_since_join <= 7:
                badges.append({"name": "Newbie", "icon": "🌱", "color": "info", "description": "First week!"})

        return badges


class GymPayment(models.Model):
    """
    Records a membership payment with optional trainer fee.
    Membership days are calculated from membership_amount only.
    """

    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="payments")

    # Payment breakdown
    membership_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("55000.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Base membership fee (used for days calculation)",
    )
    trainer_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Additional trainer fee (does not grant extra days)",
    )
    trainer = models.ForeignKey(
        GymTrainer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        help_text="Trainer assigned for this payment period",
    )

    # Legacy amount field (for backward compatibility)
    # Total amount = membership_amount + trainer_fee
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Total amount paid (membership + trainer fee)",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this membership payment",
    )

    # Membership period (calculated from membership_amount only)
    start_date = models.DateField()
    end_date = models.DateField()

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    # Metadata
    paid_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_payments_collected"
    )
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-paid_at"]
        indexes = [
            models.Index(fields=["member", "-paid_at"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["trainer", "-paid_at"]),
        ]

    def __str__(self):
        return f"{self.member.name} - {self.start_date} to {self.end_date}"

    @property
    def total_amount(self) -> Decimal:
        """Calculate total amount (membership + trainer fee)"""
        return self.membership_amount + self.trainer_fee

    def save(self, *args, **kwargs):
        # Auto-calculate total amount if not set
        if not self.amount:
            self.amount = self.membership_amount + self.trainer_fee

        # End date should be set by the caller based on prorated calculation
        # Only set default if not provided (for backward compatibility)
        if not self.end_date and self.start_date:
            from inventory.utils_gym import GYM_MEMBERSHIP_DAYS

            self.end_date = self.start_date + timedelta(days=GYM_MEMBERSHIP_DAYS - 1)

        super().save(*args, **kwargs)


class GymMemberAction(models.TextChoices):
    """Action types for gym member log"""

    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    DELETED = "deleted", "Deleted"
    ARCHIVED = "archived", "Archived"
    RESTORED = "restored", "Restored"


class GymMemberLog(models.Model):
    """
    Audit log for all changes to gym members.
    """

    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=10, choices=GymMemberAction.choices)

    # Changed fields (JSON)
    changes = models.JSONField(default=dict, blank=True)

    # Metadata
    performed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_member_logs_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["member", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.member.name} at {self.created_at}"


class GymSettings(models.Model):
    """
    Settings for gym business.
    """

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="gym_settings")

    # Contact info for arrears
    support_phone = models.CharField(max_length=20, blank=True, default="")
    support_email = models.EmailField(blank=True, default="")

    # Default membership prices
    default_membership_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("50000.00"),
        help_text="Default monthly membership fee (30 days)",
    )
    default_trainer_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("30000.00"), help_text="Default trainer fee per month"
    )

    # Other settings
    arrears_message = models.TextField(default="Your membership is in arrears. Please contact us to renew.")

    class Meta:
        verbose_name = "Gym Settings"
        verbose_name_plural = "Gym Settings"

    def __str__(self):
        return f"Gym Settings for {self.business.name}"


class GymWalletEntry(models.Model):
    """
    Wallet entries specific to gym business.
    Tracks payments and expenses.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="gym_wallet_entries", db_index=True)

    # Entry details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    entry_type = models.CharField(max_length=20, choices=[("income", "Income"), ("expense", "Expense")])

    # Link to payment if applicable
    related_payment = models.ForeignKey(
        GymPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries"
    )

    # Metadata
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_wallet_entries_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["entry_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.entry_type}: {self.amount} - {self.description}"


class GymCheckIn(models.Model):
    """
    Records when a gym member checks in (arrives at gym).
    Used for attendance tracking and conversion metrics.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="gym_checkins", db_index=True)
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_checkins"
    )
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="checkins")

    # Check-in metadata
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    checked_in_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_checkins_performed"
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["business", "-timestamp"]),
            models.Index(fields=["member", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.member.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class TrainerFee(models.Model):
    """
    Records trainer fees for gym members.
    Tracks earnings for trainers per membership period.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="trainer_fees", db_index=True)
    trainer = models.ForeignKey(GymTrainer, on_delete=models.CASCADE, related_name="fees")
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="trainer_fees")

    # Fee details
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Trainer fee amount for this period",
    )

    # Period covered by this fee
    period_start = models.DateField(help_text="Start date of membership period")
    period_end = models.DateField(help_text="End date of membership period")

    # Metadata
    recorded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="trainer_fees_recorded"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["trainer", "-created_at"]),
            models.Index(fields=["member", "period_start", "period_end"]),
        ]
        # Prevent duplicate fees for same member/period
        unique_together = [("member", "period_start", "period_end")]

    def __str__(self):
        return f"{self.trainer.name} - {self.member.name} ({self.period_start} to {self.period_end})"


# ==============================================================================
# CLOTHING MODELS
# ==============================================================================


class ClothingProductAction(models.TextChoices):
    """Action types for clothing product log"""

    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    ARCHIVED = "archived", "Archived"
    RESTORED = "restored", "Restored"
    STOCK_IN = "stock_in", "Stock In"
    SOLD = "sold", "Sold"


class ClothingProductLog(models.Model):
    """
    Audit log for all changes to clothing products.
    """

    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.CASCADE, related_name="clothing_logs")
    action = models.CharField(max_length=10, choices=ClothingProductAction.choices)

    # Changed fields (JSON)
    changes = models.JSONField(default=dict, blank=True)

    # Metadata
    performed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="clothing_logs_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.product.name} at {self.created_at}"


class ClothingSale(models.Model):
    """
    Records a sale of clothing product.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="clothing_sales", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="clothing_sales")

    # Sale details
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Cost tracking (for profit calculation)
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Cost per unit sold (for profit calculation)",
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Total cost of goods sold"
    )

    # Payment method (for cash mix tracking)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this sale",
    )

    # Metadata
    sold_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="clothing_sales_made"
    )
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["business", "payment_method", "-sold_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity} - {self.total_price}"

    def save(self, *args, **kwargs):
        # Auto-calculate totals if not set
        if not self.total_price:
            self.total_price = Decimal(self.quantity) * self.unit_price
        if not self.total_cost:
            self.total_cost = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)

    @property
    def profit(self):
        """Calculate profit for this sale"""
        return self.total_price - self.total_cost


# ==============================================================================
# CLOTHING VARIANT MODEL (for size/color combinations)
# ==============================================================================


class ClothingVariant(models.Model):
    """
    Optional variant model for clothing products with size/color combinations.
    Only used when product.has_sizes or product.has_colors is True.
    """

    product = models.ForeignKey(
        "inventory.MerchProduct", on_delete=models.CASCADE, related_name="clothing_variants", help_text="Parent product"
    )

    # Variant attributes
    size = models.CharField(max_length=20, blank=True, default="", help_text="Size for this variant (e.g., M, 42)")
    color = models.CharField(max_length=50, blank=True, default="", help_text="Color for this variant")

    # Auto-generated variant SKU
    variant_sku = models.CharField(max_length=100, blank=True, default="", help_text="Auto-generated variant SKU")

    # Stock tracking per variant
    quantity_in_stock = models.PositiveIntegerField(default=0, help_text="Stock quantity for this variant")

    # Optional price overrides
    selling_price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override selling price for this variant (optional)",
    )
    cost_price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override cost price for this variant (optional)",
    )

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["size", "color"]
        indexes = [
            models.Index(fields=["product", "is_active"], name="clothvar_prod_active_idx"),
            models.Index(fields=["product", "size", "color"], name="clothvar_prod_sz_col_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["product", "size", "color"], name="unique_product_size_color"),
        ]

    def __str__(self):
        parts = [self.product.name]
        if self.size:
            parts.append(f"Size {self.size}")
        if self.color:
            parts.append(self.color)
        return " - ".join(parts)

    def get_selling_price(self):
        """Get effective selling price (override or parent)"""
        if self.selling_price_override is not None:
            return self.selling_price_override
        return self.product.selling_price or Decimal("0.00")

    def get_cost_price(self):
        """Get effective cost price (override or parent)"""
        if self.cost_price_override is not None:
            return self.cost_price_override
        return self.product.cost_price or Decimal("0.00")

    def save(self, *args, **kwargs):
        # Auto-generate variant SKU if not set
        if not self.variant_sku and self.product.internal_sku:
            from inventory.clothing_config import generate_variant_sku

            self.variant_sku = generate_variant_sku(self.product.internal_sku, size=self.size, color=self.color)
        super().save(*args, **kwargs)


# ==============================================================================
# CEMENT MODELS
# ==============================================================================


class CementSale(models.Model):
    """
    Records a sale of cement/hardware product.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="cement_sales", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="cement_sales")

    # Sale details
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Cost tracking (for profit calculation)
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Cost per unit sold (for profit calculation)",
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Total cost of goods sold"
    )

    # Payment method
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this sale",
    )

    # Metadata
    sold_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="cement_sales_made"
    )
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    # Void/undo tracking
    is_void = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this sale was undone/voided (do not include in reports)",
    )

    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["business", "payment_method", "-sold_at"]),
            models.Index(fields=["business", "is_void", "-sold_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity} - {self.total_price}"

    def save(self, *args, **kwargs):
        # Always auto-calculate totals to ensure consistency
        self.total_price = Decimal(self.quantity) * self.unit_price
        self.total_cost = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)

    @property
    def profit(self):
        """Calculate profit for this sale"""
        return self.total_price - self.total_cost


class CementSaleUndo(models.Model):
    """
    Records an undo/rollback of a cement sale.
    Used to fix data entry errors - restores stock and reverses transactions.
    """

    sale = models.OneToOneField(
        CementSale,
        on_delete=models.CASCADE,
        related_name="undo_record",
        help_text="The sale that was undone",
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="cement_sale_undos", db_index=True)

    # Undo metadata
    undone_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cement_sales_undone",
        help_text="Manager who undid the sale",
    )
    undone_at = models.DateTimeField(default=timezone.now, db_index=True)
    reason = models.TextField(blank=True, default="", help_text="Reason for undoing the sale")

    # Audit trail (snapshot of original sale data)
    original_quantity = models.PositiveIntegerField(help_text="Original quantity sold")
    original_total_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Original sale amount")
    original_product_name = models.CharField(max_length=255, help_text="Product name at time of undo")

    class Meta:
        ordering = ["-undone_at"]
        indexes = [
            models.Index(fields=["business", "-undone_at"]),
        ]

    def __str__(self):
        return f"Undo: {self.original_product_name} x {self.original_quantity} (MK {self.original_total_price})"


class GrocerySale(models.Model):
    """
    Records a sale of grocery product.
    Supports both retail and wholesale modes.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="grocery_sales", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="grocery_sales")

    # Sale details
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Sale mode (retail or wholesale)
    sale_mode = models.CharField(
        max_length=20,
        choices=[
            ("retail", "Retail"),
            ("wholesale", "Wholesale"),
        ],
        default="retail",
        db_index=True,
        help_text="Whether this was a retail or wholesale sale",
    )

    # Cost tracking (for profit calculation)
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Cost per unit sold (for profit calculation)",
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Total cost of goods sold"
    )

    # Payment method
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this sale",
    )

    # Metadata
    sold_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="grocery_sales_made"
    )
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["business", "payment_method", "-sold_at"]),
            models.Index(fields=["business", "sale_mode", "-sold_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity} ({self.sale_mode}) - {self.total_price}"

    def save(self, *args, **kwargs):
        # Auto-calculate totals if not set
        if not self.total_price:
            self.total_price = Decimal(self.quantity) * self.unit_price
        if not self.total_cost:
            self.total_cost = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)

    @property
    def profit(self):
        """Calculate profit for this sale"""
        return self.total_price - self.total_cost


class CementCost(models.Model):
    """
    Tracks costs/expenses for cement business (transport, labor, rent, utilities, etc.)
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="cement_costs", db_index=True)
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="cement_costs"
    )

    # Cost details
    cost_type = models.CharField(
        max_length=20,
        choices=[
            ("operating", "Operating Expense"),
            ("cogs", "Stock/COGS"),
            ("other", "Other"),
        ],
        default="operating",
        db_index=True,
        help_text="Type of cost: operating expenses, inventory/COGS, or other",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    category = models.CharField(
        max_length=50,
        choices=[
            ("transport", "Transport"),
            ("labor", "Labor"),
            ("rent", "Rent"),
            ("utilities", "Utilities"),
            ("other", "Other"),
        ],
        default="other",
        db_index=True,
    )
    description = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")

    # Date tracking
    cost_date = models.DateField(default=timezone.now, db_index=True, help_text="Date when cost was incurred")

    # Metadata
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="cement_costs_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-cost_date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-cost_date"]),
            models.Index(fields=["business", "category", "-cost_date"]),
        ]

    def __str__(self):
        return f"{self.get_category_display()} - {self.amount} ({self.cost_date})"


# ==============================================================================
# ADDITIONAL LIQUOR & GROCERY (if needed for future)
# ==============================================================================


class LiquorExpense(models.Model):
    """
    Tracks expenses for liquor business.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_expenses", db_index=True)

    # Expense details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=50, blank=True, default="")

    # Metadata
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_expenses_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.description} - {self.amount}"


class LiquorWalletEntry(models.Model):
    """
    Wallet entries specific to liquor business.
    """

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="liquor_wallet_entries", db_index=True
    )

    # Entry details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    entry_type = models.CharField(max_length=20, choices=[("income", "Income"), ("expense", "Expense")])

    # Link to sale or credit payment if applicable
    related_sale = models.ForeignKey(
        LiquorSale, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries"
    )
    related_payment = models.ForeignKey(
        LiquorCreditPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries"
    )

    # Metadata
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_wallet_entries_created"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["entry_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.entry_type}: {self.amount} - {self.description}"


class LiquorStockThreshold(models.Model):
    """
    Stock capacity thresholds for liquor categories.
    Used to calculate "battery" percentages in stock overview.
    """

    CATEGORY_CHOICES = [
        ("beer", "Beer"),
        ("cider", "Cider"),
        ("spirits", "Spirits"),
        ("wine", "Wine"),
        ("other", "Other"),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_stock_thresholds")
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.CASCADE, related_name="liquor_stock_thresholds"
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    full_capacity = models.PositiveIntegerField(default=600, help_text="Target capacity (bottles) when fully stocked")

    class Meta:
        unique_together = ("business", "location", "category")
        indexes = [
            models.Index(fields=["business", "location", "category"]),
        ]

    def __str__(self):
        return f"{self.business.name} - {self.get_category_display()} - {self.full_capacity} bottles"


class LiquorStockSettings(models.Model):
    """
    Business-level stock settings for liquor store.
    Provides default targets per category and default auto-adjust percentage.
    """

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="liquor_stock_settings")

    # Category-level default targets (fallback when no per-product targets exist)
    beer_target = models.PositiveIntegerField(default=600, help_text="Default target for beer category")
    cider_target = models.PositiveIntegerField(default=600, help_text="Default target for cider category")
    spirits_target = models.PositiveIntegerField(default=600, help_text="Default target for spirits category")
    whiskey_target = models.PositiveIntegerField(default=600, help_text="Default target for whiskey category")
    wine_target = models.PositiveIntegerField(default=600, help_text="Default target for wine category")
    other_target = models.PositiveIntegerField(default=600, help_text="Default target for other category")

    # Default auto-adjust percentage for all products
    default_auto_adjust_pct = models.PositiveIntegerField(
        default=20, help_text="Default auto-adjust percentage for products (typically 20%)"
    )

    # Auto-adjust settings
    auto_adjust_lookback_days = models.PositiveIntegerField(
        default=30, help_text="Days to look back when calculating peak demand"
    )

    class Meta:
        verbose_name = "Liquor Stock Settings"
        verbose_name_plural = "Liquor Stock Settings"

    def __str__(self):
        return f"Stock Settings for {self.business.name}"


# ==============================================================================
# MONTHLY SALES TARGETS (Generic for all verticals)
# ==============================================================================


class MonthlySalesTarget(models.Model):
    """
    Monthly sales target for any business vertical.
    Generic model that can be used across phones, liquor, gym, clothing, etc.
    Stock-aware: warns if target is inconsistent with current inventory.
    """

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="monthly_sales_targets", db_index=True
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="monthly_sales_targets",
    )

    # Vertical identifier (use same choices as business vertical/product kind)
    vertical = models.CharField(
        max_length=32, db_index=True, help_text="Business vertical: liquor, phones, gym, clothing, pharmacy, etc."
    )

    # Time period
    year = models.IntegerField(db_index=True)
    month = models.IntegerField(db_index=True, help_text="1-12")

    # Targets
    target_units = models.PositiveIntegerField(default=0, help_text="Target number of items/units to sell this month")
    target_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), help_text="Optional revenue target in local currency"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="monthly_sales_targets_created"
    )

    class Meta:
        unique_together = ("business", "location", "vertical", "year", "month")
        indexes = [
            models.Index(fields=["business", "vertical", "year", "month"]),
            models.Index(fields=["business", "location", "vertical", "year", "month"]),
        ]
        ordering = ["-year", "-month"]

    def __str__(self):
        location_str = f" @ {self.location.name}" if self.location else ""
        return f"{self.business.name}{location_str} - {self.vertical} - {self.year}-{self.month:02d} - {self.target_units} units"

    def is_current_month(self) -> bool:
        """Check if this target is for the current calendar month."""
        now = timezone.now()
        return self.year == now.year and self.month == now.month
