# wallet/agent_models.py
"""
Agent-specific wallet models for commissions, deductions, and rankings.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum, Count
from django.utils import timezone

User = settings.AUTH_USER_MODEL


def q2(x: Optional[Decimal]) -> Decimal:
    """Quantize to 2 dp (HALF_UP)."""
    from decimal import ROUND_HALF_UP
    if x is None:
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------------
# Agent Wallet Models
# ----------------------------------------------------------------------

class AgentWallet(models.Model):
    """
    Per-agent wallet tied to a specific membership (business + location).
    One wallet per (user, business, location) combination.
    """
    membership = models.OneToOneField(
        "tenants.Membership",
        on_delete=models.CASCADE,
        related_name="agent_wallet",
        help_text="Links to the membership (user + business + location)",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Current wallet balance (non-negative)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["membership"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Wallet for {self.membership} - Balance: {self.balance}"

    def save(self, *args, **kwargs):
        # Normalize balance
        self.balance = q2(self.balance)
        # Enforce non-negative balance
        if self.balance < Decimal("0.00"):
            from django.core.exceptions import ValidationError
            raise ValidationError("Agent wallet balance cannot be negative.")
        super().save(*args, **kwargs)

    @property
    def user(self):
        """Convenience accessor for the user."""
        return self.membership.user if hasattr(self, 'membership') else None

    @property
    def business(self):
        """Convenience accessor for the business."""
        return self.membership.business if hasattr(self, 'membership') else None

    @property
    def location(self):
        """Convenience accessor for the location."""
        return self.membership.location if hasattr(self, 'membership') else None


class AgentWalletTransactionType(models.TextChoices):
    COMMISSION_SALE = "commission_sale", "Commission (Sale)"
    ADJUSTMENT_MANUAL = "adjustment_manual", "Manual Adjustment"
    DEDUCTION_TIMELOG = "deduction_timelog", "Deduction (Timelog Penalty)"
    BONUS = "bonus", "Bonus"
    PAYOUT = "payout", "Payout"


class AgentWalletTransaction(models.Model):
    """
    Records all transactions affecting an agent's wallet.
    Can be commissions, manual adjustments, or timelog deductions.
    """
    wallet = models.ForeignKey(
        AgentWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=32,
        choices=AgentWalletTransactionType.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Transaction amount (always positive; use is_debit to indicate direction)",
    )
    is_debit = models.BooleanField(
        default=False,
        help_text="True for deductions/payouts, False for credits/commissions",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    
    # Links to related objects (nullable for flexibility)
    related_sale_id = models.IntegerField(null=True, blank=True, help_text="ID of related sale")
    related_sale_model = models.CharField(max_length=50, blank=True, default="", help_text="Model name of sale")
    related_timelog = models.ForeignKey(
        "inventory.TimeLog",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_wallet_txns",
    )
    
    # Admin adjustment tracking
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_wallet_txns_created",
        help_text="User who created this transaction (for manual adjustments)",
    )
    reason = models.TextField(blank=True, default="", help_text="Reason for manual adjustments")
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    effective_date = models.DateField(default=timezone.localdate, db_index=True)
    
    # Metadata
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
            models.Index(fields=["wallet", "transaction_type", "-created_at"]),
            models.Index(fields=["effective_date"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "-" if self.is_debit else "+"
        return f"{self.transaction_type}: {sign}{self.amount} for {self.wallet.membership.user}"

    def save(self, *args, **kwargs):
        # Normalize amount
        self.amount = q2(self.amount)
        
        # Validate amount is positive
        if self.amount < Decimal("0.00"):
            from django.core.exceptions import ValidationError
            raise ValidationError("Transaction amount must be non-negative. Use is_debit for direction.")
        
        # If this is a new transaction, update the wallet balance
        if not self.pk:
            # Get the wallet and update balance
            wallet = self.wallet
            if self.is_debit:
                new_balance = wallet.balance - self.amount
                if new_balance < Decimal("0.00"):
                    from django.core.exceptions import ValidationError
                    raise ValidationError(
                        f"Insufficient balance. Current: {wallet.balance}, Deduction: {self.amount}"
                    )
                wallet.balance = new_balance
            else:
                wallet.balance += self.amount
            
            wallet.save(update_fields=["balance", "updated_at"])
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Prevent deletion of transactions to maintain audit trail.
        Use reversal transactions instead.
        """
        from django.core.exceptions import ValidationError
        raise ValidationError("Cannot delete wallet transactions. Create a reversal transaction instead.")


# ----------------------------------------------------------------------
# Helper functions for agent wallet operations
# ----------------------------------------------------------------------

def get_or_create_agent_wallet(membership) -> AgentWallet:
    """Get or create an agent wallet for a given membership."""
    wallet, created = AgentWallet.objects.get_or_create(membership=membership)
    return wallet


def add_commission(membership, amount: Decimal, description: str = "", **kwargs) -> AgentWalletTransaction:
    """
    Add a commission to an agent's wallet.
    
    Args:
        membership: The Membership object
        amount: Commission amount (positive)
        description: Description of the commission
        **kwargs: Additional fields (related_sale_id, related_sale_model, meta, etc.)
    
    Returns:
        AgentWalletTransaction instance
    """
    wallet = get_or_create_agent_wallet(membership)
    
    txn = AgentWalletTransaction(
        wallet=wallet,
        transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
        amount=q2(amount),
        is_debit=False,
        description=description or "Sale commission",
        **{k: v for k, v in kwargs.items() if k in [
            'related_sale_id', 'related_sale_model', 'created_by', 'effective_date', 'meta'
        ]}
    )
    txn.save()
    return txn


def add_deduction(membership, amount: Decimal, description: str = "", **kwargs) -> AgentWalletTransaction:
    """
    Add a deduction to an agent's wallet.
    
    Args:
        membership: The Membership object
        amount: Deduction amount (positive, will be subtracted)
        description: Description of the deduction
        **kwargs: Additional fields (related_timelog, created_by, reason, etc.)
    
    Returns:
        AgentWalletTransaction instance
    
    Raises:
        ValidationError if insufficient balance
    """
    wallet = get_or_create_agent_wallet(membership)
    
    txn = AgentWalletTransaction(
        wallet=wallet,
        transaction_type=AgentWalletTransactionType.DEDUCTION_TIMELOG,
        amount=q2(amount),
        is_debit=True,
        description=description or "Timelog penalty",
        **{k: v for k, v in kwargs.items() if k in [
            'related_timelog', 'created_by', 'reason', 'effective_date', 'meta'
        ]}
    )
    txn.save()
    return txn


def add_manual_adjustment(membership, amount: Decimal, is_debit: bool, reason: str, created_by, **kwargs) -> AgentWalletTransaction:
    """
    Add a manual adjustment (positive or negative) to an agent's wallet.
    
    Args:
        membership: The Membership object
        amount: Adjustment amount (always positive)
        is_debit: True for deduction, False for credit
        reason: Required reason for the adjustment
        created_by: User making the adjustment
        **kwargs: Additional fields
    
    Returns:
        AgentWalletTransaction instance
    """
    if not reason or not reason.strip():
        from django.core.exceptions import ValidationError
        raise ValidationError("Reason is required for manual adjustments.")
    
    wallet = get_or_create_agent_wallet(membership)
    
    txn = AgentWalletTransaction(
        wallet=wallet,
        transaction_type=AgentWalletTransactionType.ADJUSTMENT_MANUAL,
        amount=q2(amount),
        is_debit=is_debit,
        description=f"Manual adjustment: {reason}",
        reason=reason,
        created_by=created_by,
        **{k: v for k, v in kwargs.items() if k in ['effective_date', 'meta']}
    )
    txn.save()
    return txn


# ----------------------------------------------------------------------
# Agent Earnings & Rankings
# ----------------------------------------------------------------------

class AgentEarnings:
    """
    Helper class to compute agent earnings, deductions, and rankings.
    Scoped by business and location.
    """
    
    def __init__(self, membership):
        self.membership = membership
        self.user = membership.user
        self.business = membership.business
        self.location = membership.location
        self._wallet = None
    
    @property
    def wallet(self) -> AgentWallet:
        """Lazy-load wallet."""
        if not self._wallet:
            self._wallet = get_or_create_agent_wallet(self.membership)
        return self._wallet
    
    @property
    def balance(self) -> Decimal:
        """Current wallet balance."""
        return self.wallet.balance
    
    def earnings_for_period(self, start_date, end_date) -> Decimal:
        """Calculate total earnings (commissions + bonuses) for a period."""
        txns = AgentWalletTransaction.objects.filter(
            wallet=self.wallet,
            is_debit=False,
            effective_date__gte=start_date,
            effective_date__lte=end_date,
        )
        total = txns.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return q2(total)
    
    def deductions_for_period(self, start_date, end_date) -> Decimal:
        """Calculate total deductions for a period."""
        txns = AgentWalletTransaction.objects.filter(
            wallet=self.wallet,
            is_debit=True,
            effective_date__gte=start_date,
            effective_date__lte=end_date,
        )
        total = txns.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return q2(total)
    
    def net_for_period(self, start_date, end_date) -> Decimal:
        """Calculate net earnings (earnings - deductions) for a period."""
        earnings = self.earnings_for_period(start_date, end_date)
        deductions = self.deductions_for_period(start_date, end_date)
        return q2(earnings - deductions)
    
    def mtd_earnings(self) -> Decimal:
        """Month-to-date earnings."""
        today = timezone.localdate()
        start = today.replace(day=1)
        return self.earnings_for_period(start, today)
    
    def mtd_deductions(self) -> Decimal:
        """Month-to-date deductions."""
        today = timezone.localdate()
        start = today.replace(day=1)
        return self.deductions_for_period(start, today)
    
    def mtd_net(self) -> Decimal:
        """Month-to-date net earnings."""
        return q2(self.mtd_earnings() - self.mtd_deductions())
    
    def lifetime_earnings(self) -> Decimal:
        """All-time earnings."""
        txns = AgentWalletTransaction.objects.filter(
            wallet=self.wallet,
            is_debit=False,
        )
        total = txns.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return q2(total)
    
    def lifetime_deductions(self) -> Decimal:
        """All-time deductions."""
        txns = AgentWalletTransaction.objects.filter(
            wallet=self.wallet,
            is_debit=True,
        )
        total = txns.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return q2(total)
    
    def lifetime_net(self) -> Decimal:
        """All-time net earnings."""
        return q2(self.lifetime_earnings() - self.lifetime_deductions())


def get_agent_ranking(membership, period_start=None, period_end=None):
    """
    Get agent's ranking within their business and location for a given period.
    
    Returns:
        dict with keys: rank, total_agents, sales_count, top_sales_count, behind_top
    """
    from tenants.models import Membership
    
    # Get all active agents in the same business and location
    peer_memberships = Membership.objects.filter(
        business=membership.business,
        location=membership.location,
        role="AGENT",
        status="ACTIVE",
    ).exclude(pk=membership.pk)
    
    # If no period specified, use current month
    if not period_start:
        today = timezone.localdate()
        period_start = today.replace(day=1)
    if not period_end:
        period_end = timezone.localdate()
    
    # Calculate sales count for this agent
    my_wallet = get_or_create_agent_wallet(membership)
    my_commissions = AgentWalletTransaction.objects.filter(
        wallet=my_wallet,
        transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
        effective_date__gte=period_start,
        effective_date__lte=period_end,
    ).count()
    
    # Calculate sales counts for all peers
    peer_counts = []
    for peer in peer_memberships:
        peer_wallet = get_or_create_agent_wallet(peer)
        peer_commissions = AgentWalletTransaction.objects.filter(
            wallet=peer_wallet,
            transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
            effective_date__gte=period_start,
            effective_date__lte=period_end,
        ).count()
        peer_counts.append(peer_commissions)
    
    # Sort to find rank
    all_counts = peer_counts + [my_commissions]
    all_counts_sorted = sorted(all_counts, reverse=True)
    
    rank = all_counts_sorted.index(my_commissions) + 1
    total_agents = len(all_counts)
    top_sales_count = all_counts_sorted[0] if all_counts_sorted else 0
    behind_top = max(0, top_sales_count - my_commissions)
    
    return {
        "rank": rank,
        "total_agents": total_agents,
        "sales_count": my_commissions,
        "top_sales_count": top_sales_count,
        "behind_top": behind_top,
        "is_top": rank == 1,
    }

