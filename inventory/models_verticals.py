# inventory/models_verticals.py
"""
Models for non-phone verticals: Liquor, Gym, Clothing.
These models extend the base MerchProduct system with vertical-specific functionality.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from datetime import timedelta

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


class LiquorSaleType(models.TextChoices):
    """Type of liquor sale"""
    SALE = "sale", "Cash Sale"
    CREDIT = "credit", "Credit Sale"
    UNDECIDED = "undecided", "Undecided"


class LiquorSale(models.Model):
    """
    Records a sale of liquor product.
    Can be bottle or shot, cash or credit.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_sales", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.PROTECT, related_name="liquor_sales")
    
    # Sale details
    unit = models.CharField(max_length=10, choices=LiquorUnitType.choices, default=LiquorUnitType.BOTTLE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Payment type
    sale_type = models.CharField(max_length=10, choices=LiquorSaleType.choices, default=LiquorSaleType.SALE)
    is_credit = models.BooleanField(default=False, db_index=True)
    linked_credit = models.ForeignKey("LiquorCredit", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales")
    
    # Metadata
    sold_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_sales_made")
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["business", "sale_type", "-sold_at"]),
            models.Index(fields=["is_credit", "-sold_at"]),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.quantity} {self.unit}) - {self.total_price}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total if not set
        if not self.total_price:
            self.total_price = Decimal(self.quantity) * self.unit_price
        
        # Sync is_credit with sale_type
        self.is_credit = self.sale_type == LiquorSaleType.CREDIT
        
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
    
    # Amount details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    
    # Status tracking
    status = models.CharField(max_length=10, choices=LiquorCreditStatus.choices, default=LiquorCreditStatus.OPEN, db_index=True)
    
    # Linked sale (if converted from sale)
    related_sale = models.ForeignKey(LiquorSale, null=True, blank=True, on_delete=models.SET_NULL, related_name="credits")
    
    # Metadata
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_credits_created")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True)
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
    status = models.CharField(max_length=10, choices=LiquorCreditPaymentStatus.choices, default=LiquorCreditPaymentStatus.PENDING, db_index=True)
    
    # Metadata
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_payments_submitted")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Review tracking
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_payments_reviewed")
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
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_stock_requests", db_index=True)
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.CASCADE, related_name="liquor_stock_requests")
    
    # Requested changes (stored as JSON)
    requested_changes = models.JSONField(default=dict, help_text="JSON of fields to change")
    reason = models.TextField(blank=True, default="")
    
    # Approval workflow
    status = models.CharField(max_length=10, choices=LiquorStockEditRequestStatus.choices, default=LiquorStockEditRequestStatus.PENDING, db_index=True)
    
    # Metadata
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="liquor_stock_requests_submitted")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Review tracking
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_stock_requests_reviewed")
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

class GymMember(models.Model):
    """
    Gym member with 30-day rolling membership.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="gym_members", db_index=True)
    
    # Member info
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    
    # Membership status
    is_active = models.BooleanField(default=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    
    # Metadata
    joined_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_members_archived")
    
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        unique_together = [("business", "phone")]
        ordering = ["-joined_at"]
        indexes = [
            models.Index(fields=["business", "is_active", "is_archived"]),
            models.Index(fields=["phone"]),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.phone})"
    
    def days_left(self) -> int:
        """Calculate days left in membership based on latest payment"""
        latest_payment = self.payments.filter(is_active=True).order_by("-end_date").first()
        if not latest_payment:
            return 0
        
        days = (latest_payment.end_date - timezone.now().date()).days
        return max(0, days)
    
    def membership_status(self) -> str:
        """Return 'Active' or 'In arrears'"""
        return "Active" if self.days_left() > 0 else "In arrears"
    
    def archive(self, by_user):
        """Archive this member"""
        self.is_archived = True
        self.is_active = False
        self.archived_at = timezone.now()
        self.archived_by = by_user
        self.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])


class GymPayment(models.Model):
    """
    Records a 30-day membership payment.
    Each payment grants exactly 30 days.
    """
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="payments")
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    
    # 30-day period
    start_date = models.DateField()
    end_date = models.DateField()  # Always start_date + 30 days
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Metadata
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_payments_collected")
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-paid_at"]
        indexes = [
            models.Index(fields=["member", "-paid_at"]),
            models.Index(fields=["start_date", "end_date"]),
        ]
    
    def __str__(self):
        return f"{self.member.name} - {self.start_date} to {self.end_date}"
    
    def save(self, *args, **kwargs):
        # Always set end_date to start_date + 30 days
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=30)
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
    performed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_member_logs_created")
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
    
    # Default membership price
    default_membership_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50000.00"))
    
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
    related_payment = models.ForeignKey(GymPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries")
    
    # Metadata
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="gym_wallet_entries_created")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["entry_type", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.entry_type}: {self.amount} - {self.description}"


# ==============================================================================
# CLOTHING MODELS
# ==============================================================================

class ClothingProductAction(models.TextChoices):
    """Action types for clothing product log"""
    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    ARCHIVED = "archived", "Archived"
    RESTORED = "restored", "Restored"


class ClothingProductLog(models.Model):
    """
    Audit log for all changes to clothing products.
    """
    product = models.ForeignKey("inventory.MerchProduct", on_delete=models.CASCADE, related_name="clothing_logs")
    action = models.CharField(max_length=10, choices=ClothingProductAction.choices)
    
    # Changed fields (JSON)
    changes = models.JSONField(default=dict, blank=True)
    
    # Metadata
    performed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="clothing_logs_created")
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
    
    # Metadata
    sold_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="clothing_sales_made")
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
        ]
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity} - {self.total_price}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total if not set
        if not self.total_price:
            self.total_price = Decimal(self.quantity) * self.unit_price
        super().save(*args, **kwargs)


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
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_expenses_created")
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
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="liquor_wallet_entries", db_index=True)
    
    # Entry details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    entry_type = models.CharField(max_length=20, choices=[("income", "Income"), ("expense", "Expense")])
    
    # Link to sale or credit payment if applicable
    related_sale = models.ForeignKey(LiquorSale, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries")
    related_payment = models.ForeignKey(LiquorCreditPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="wallet_entries")
    
    # Metadata
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="liquor_wallet_entries_created")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["entry_type", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.entry_type}: {self.amount} - {self.description}"

