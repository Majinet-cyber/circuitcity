# sales/models.py
"""
Sales models including commission tracking and bonus/penalty configuration.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from inventory.models import InventoryItem, Location

User = get_user_model()


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    BANK = "BANK", "Bank"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"


class Sale(models.Model):
    """
    Created when an InventoryItem is sold on credit.
    """
    item            = models.OneToOneField(InventoryItem, on_delete=models.PROTECT, related_name="sale")
    agent           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales", help_text="Agent who made the sale (null if agent deleted)")
    location        = models.ForeignKey(Location, on_delete=models.PROTECT)
    sold_at         = models.DateField()
    price           = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    commission_pct  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                          validators=[MinValueValidator(0), MaxValueValidator(100)])
    payment_method  = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        db_index=True,
        help_text="Payment method used for this sale"
    )
    # Phase 5: index for fast dashboards / recents
    created_at      = models.DateTimeField(default=timezone.now, editable=False)
    
    # Rollback tracking fields
    is_rolled_back  = models.BooleanField(default=False, db_index=True, help_text="Whether this sale has been rolled back/reversed")
    rolled_back_at  = models.DateTimeField(null=True, blank=True, help_text="When this sale was rolled back")
    rolled_back_by  = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="rolled_back_sales", help_text="User who rolled back this sale")

    class Meta:
        indexes = [
            models.Index(fields=["created_at"], name="sale_created_at_idx"),
            models.Index(fields=["sold_at"], name="sale_sold_at_idx"),
            models.Index(fields=["location", "created_at"], name="sale_loc_created_idx"),
            models.Index(fields=["agent", "created_at"], name="sale_agent_created_idx"),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="sale_price_nonneg"),
            models.CheckConstraint(check=models.Q(commission_pct__gte=0) & models.Q(commission_pct__lte=100),
                                   name="sale_commission_pct_0_100"),
        ]

    @property
    def commission_amount(self):
        return (self.price * self.commission_pct) / 100

    def __str__(self):
        return f"Sale #{self.pk} - item {self.item_id}"


class RollbackReason(models.TextChoices):
    """Reasons for rolling back a sale"""
    DAMAGED = "DAMAGED", "Damaged"
    RETURNED = "RETURNED", "Returned"
    ERROR = "ERROR", "Data Entry Error"
    OTHER = "OTHER", "Other"


class SaleRollback(models.Model):
    """
    Audit record for sale rollbacks/reversals.
    When a sale is rolled back, we create this record and mark the Sale as rolled_back.
    """
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="rollbacks",
        help_text="The sale that was rolled back"
    )
    reason = models.CharField(
        max_length=20,
        choices=RollbackReason.choices,
        help_text="Reason for rollback"
    )
    refunded = models.BooleanField(
        default=False,
        help_text="Whether a refund was issued to customer"
    )
    refunded_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Amount refunded to customer (if any)"
    )
    return_to_stock = models.BooleanField(
        default=False,
        help_text="Whether item was returned to stock"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the rollback"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_rollbacks",
        help_text="User who performed the rollback"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        help_text="When the rollback was performed"
    )
    
    class Meta:
        db_table = "sales_sale_rollback"
        indexes = [
            models.Index(fields=["created_at"], name="rollback_created_idx"),
            models.Index(fields=["sale"], name="rollback_sale_idx"),
            models.Index(fields=["created_by"], name="rollback_user_idx"),
        ]
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Rollback #{self.pk} - Sale #{self.sale_id} ({self.get_reason_display()})"


# =========================================================================
# Commission Configuration
# =========================================================================

class CommissionConfig(models.Model):
    """
    Commission and bonus/penalty configuration per business.
    ONE active config per business at a time.
    """
    
    COMMISSION_MODE_PERCENT = 'PERCENT'
    COMMISSION_MODE_FIXED = 'FIXED'
    COMMISSION_MODE_CHOICES = [
        (COMMISSION_MODE_PERCENT, 'Percentage'),
        (COMMISSION_MODE_FIXED, 'Fixed Amount'),
    ]
    
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="commission_configs",
    )
    
    # Master toggle for commissions
    commissions_enabled = models.BooleanField(
        default=True,
        help_text="Enable or disable commission calculation for new sales. When OFF, agents do not earn commissions.",
    )
    
    # Commission mode selector
    commission_mode = models.CharField(
        max_length=20,
        choices=COMMISSION_MODE_CHOICES,
        default=COMMISSION_MODE_PERCENT,
        help_text="Commission calculation mode: Percentage or Fixed amount per sale.",
    )
    
    # Base commission rate for phone sales (percentage mode)
    base_commission_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("12.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Commission percentage for phone sales (e.g., 12.00 = 12%). Used when commission_mode=PERCENT.",
    )
    
    # Alternative: fixed amount per sale (fixed mode)
    fixed_commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("2000.00"),
        validators=[MinValueValidator(0)],
        help_text="Fixed commission per sale in MWK. Used when commission_mode=FIXED.",
    )
    
    # Bonus/Penalty configuration for time-based incentives
    early_bonus_per_30min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("5000.00"),
        validators=[MinValueValidator(0)],
        help_text="Bonus amount per 30 minutes arrived early (MWK).",
    )
    
    late_penalty_per_30min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("7000.00"),
        validators=[MinValueValidator(0)],
        help_text="Penalty amount per 30 minutes arrived late (MWK).",
    )
    
    lateness_penalties_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic lateness penalties based on time logs.",
    )
    
    early_bonus_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic early arrival bonuses based on time logs.",
    )
    
    # Active flag for versioning
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "is_active"]),
        ]
    
    def __str__(self):
        return f"Commission Config for {self.business.name} (active={self.is_active})"
    
    @classmethod
    def get_active(cls, business) -> Optional["CommissionConfig"]:
        """Get the active commission config for a business."""
        return cls.objects.filter(business=business, is_active=True).first()
    
    @classmethod
    def ensure_config(cls, business) -> "CommissionConfig":
        """Get or create a commission config for a business."""
        config = cls.get_active(business)
        if config:
            return config
        return cls.objects.create(business=business, is_active=True)


# =========================================================================
# Sale Commission Tracking
# =========================================================================

class SaleCommission(models.Model):
    """
    Records the computed commission for a sale, including bonuses and penalties.
    One row per Sale.
    """
    sale = models.OneToOneField(
        Sale,
        on_delete=models.CASCADE,
        related_name="commission_record",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commissions",
    )
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="sale_commissions",
    )
    
    # Base commission from the sale
    base_commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    
    # Time-based bonuses/penalties
    early_bonus = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Bonus for arriving early.",
    )
    late_penalty = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Penalty for arriving late.",
    )
    
    # Computed net
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Final commission after bonuses and penalties.",
    )
    
    # Metadata for transparency
    early_blocks = models.PositiveIntegerField(
        default=0,
        help_text="Number of 30-min blocks arrived early.",
    )
    late_blocks = models.PositiveIntegerField(
        default=0,
        help_text="Number of 30-min blocks arrived late.",
    )
    
    # Link to the work log used for calculation (optional)
    work_log = models.ForeignKey(
        "timelogs.AgentWorkLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_commissions",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Reversal tracking (for rollbacks)
    is_reversed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this commission was reversed due to sale rollback"
    )
    reversed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this commission was reversed"
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent", "created_at"]),
            models.Index(fields=["business", "created_at"]),
        ]
    
    def __str__(self):
        return f"Commission for Sale #{self.sale_id}: {self.net_amount}"
    
    def compute_net(self) -> None:
        """Compute net_amount from base, bonus, and penalty."""
        self.net_amount = self.base_commission + self.early_bonus - self.late_penalty
    
    def save(self, *args, **kwargs):
        self.compute_net()
        super().save(*args, **kwargs)
    
    @classmethod
    def create_for_sale(cls, sale: Sale) -> "SaleCommission":
        """
        Create a commission record for a sale, applying config and time-based bonuses/penalties.
        """
        from timelogs.models import AgentWorkLog
        
        business = sale.location.business if sale.location else None
        if not business:
            # Try to get from item
            business = getattr(sale.item, "business", None)
        
        config = CommissionConfig.get_active(business) if business else None
        
        # Calculate base commission
        if config and config.fixed_commission_amount:
            base = config.fixed_commission_amount
        elif config:
            base = sale.price * config.base_commission_pct / 100
        else:
            base = sale.commission_amount  # Use sale's built-in calculation
        
        # Get work log for the sale date
        work_log = None
        early_blocks = 0
        late_blocks = 0
        early_bonus = Decimal("0.00")
        late_penalty = Decimal("0.00")
        
        if business:
            try:
                work_log = AgentWorkLog.objects.get(
                    agent=sale.agent,
                    business=business,
                    work_date=sale.sold_at,
                )
                early_blocks = work_log.early_bonus_blocks
                late_blocks = work_log.late_penalty_blocks
            except AgentWorkLog.DoesNotExist:
                pass
        
        # Apply bonuses/penalties if config allows
        if config and work_log:
            if config.early_bonus_enabled and early_blocks > 0:
                early_bonus = config.early_bonus_per_30min * early_blocks
            
            if config.lateness_penalties_enabled and late_blocks > 0:
                late_penalty = config.late_penalty_per_30min * late_blocks
        
        commission = cls.objects.create(
            sale=sale,
            agent=sale.agent,
            business=business,
            base_commission=base,
            early_bonus=early_bonus,
            late_penalty=late_penalty,
            early_blocks=early_blocks,
            late_blocks=late_blocks,
            work_log=work_log,
        )
        
        return commission


# =========================================================================
# Agent Earnings Summary (helper model for dashboards)
# =========================================================================

class AgentEarningsSummary:
    """
    Non-persisted helper class for computing agent earnings over a period.
    Use this for dashboard displays.
    """
    
    def __init__(self, agent, business, start_date, end_date):
        self.agent = agent
        self.business = business
        self.start_date = start_date
        self.end_date = end_date
        self._compute()
    
    def _compute(self):
        commissions = SaleCommission.objects.filter(
            agent=self.agent,
            business=self.business,
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        )
        
        agg = commissions.aggregate(
            total_base=Sum("base_commission"),
            total_bonus=Sum("early_bonus"),
            total_penalty=Sum("late_penalty"),
            total_net=Sum("net_amount"),
        )
        
        self.total_base = agg["total_base"] or Decimal("0.00")
        self.total_bonus = agg["total_bonus"] or Decimal("0.00")
        self.total_penalty = agg["total_penalty"] or Decimal("0.00")
        self.total_net = agg["total_net"] or Decimal("0.00")
        self.sale_count = commissions.count()
    
    def to_dict(self):
        return {
            "agent_id": self.agent.id,
            "agent_name": self.agent.get_full_name() or self.agent.username,
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "sale_count": self.sale_count,
            "total_base": float(self.total_base),
            "total_bonus": float(self.total_bonus),
            "total_penalty": float(self.total_penalty),
            "total_net": float(self.total_net),
        }


# =========================================================================
# LIQUOR BARMAN ATTRIBUTION (for Liquor vertical only)
# =========================================================================

class LiquorSaleAttribution(models.Model):
    """
    Tracks liquor sales attributed by a barman to a specific agent.
    Used for barman/agent reconciliation workflows in the liquor vertical.
    
    When a barman makes a sale via Fast Sell, they can optionally assign it to an agent.
    This creates an attribution record that needs to be reconciled later.
    """
    
    STATUS_PENDING = 'pending'
    STATUS_RECONCILED = 'reconciled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Reconciliation'),
        (STATUS_RECONCILED, 'Reconciled'),
    ]
    
    # Link to the actual sale (using generic relation since LiquorSale is in inventory app)
    # We'll store the sale ID and reference it via application logic
    liquor_sale_id = models.PositiveIntegerField(
        db_index=True,
        help_text="ID of the LiquorSale this attribution is for"
    )
    
    # Business context
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="liquor_sale_attributions",
        db_index=True
    )
    
    # Attribution: who sold it (barman) and who it's assigned to (agent)
    attributed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="liquor_attributions_made",
        help_text="The barman who made this sale"
    )
    
    attributed_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="liquor_attributions_received",
        help_text="The agent this sale is attributed to"
    )
    
    # Reconciliation status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True
    )
    
    # Reconciliation metadata
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="liquor_attributions_reconciled"
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Sale amount for quick aggregation (denormalized for performance)
    sale_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total sale amount (denormalized for performance)"
    )
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "-created_at"]),
            models.Index(fields=["attributed_to", "status", "-created_at"]),
            models.Index(fields=["attributed_by", "-created_at"]),
            models.Index(fields=["liquor_sale_id"]),
        ]
    
    def __str__(self):
        return f"Attribution #{self.pk}: Sale {self.liquor_sale_id} → {self.attributed_to.username} ({self.status})"
    
    def mark_reconciled(self, user):
        """Mark this attribution as reconciled"""
        self.status = self.STATUS_RECONCILED
        self.reconciled_by = user
        self.reconciled_at = timezone.now()
        self.save(update_fields=["status", "reconciled_by", "reconciled_at", "updated_at"])
    
    def mark_pending(self):
        """Mark this attribution as pending"""
        self.status = self.STATUS_PENDING
        self.reconciled_by = None
        self.reconciled_at = None
        self.save(update_fields=["status", "reconciled_by", "reconciled_at", "updated_at"])


