"""
PHASE 4: Price Correction Audit Models
Tracks all price changes for accountability and reporting.
"""
from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class PriceAdjustment(models.Model):
    """
    Immutable audit trail for price corrections on sold items.

    Original Sale record is never modified. Reporting uses this
    adjustment layer to calculate "effective" price/profit.
    """

    ADJUSTMENT_TYPE_CHOICES = [
        ("PRICE_CORRECTION", "Price Correction"),
        ("COST_CORRECTION", "Cost Correction"),
        ("BOTH", "Price and Cost Correction"),
    ]

    # Link to original sale
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, related_name="price_adjustments", help_text="Sale being adjusted"
    )

    # What changed
    adjustment_type = models.CharField(
        max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, help_text="What aspect of the sale is being corrected"
    )

    # Original values (snapshot for audit trail)
    original_selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Selling price before adjustment"
    )
    original_cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Cost price before adjustment (if applicable)"
    )

    # New values
    new_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="New selling price (null if only cost changed)",
    )
    new_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="New cost price (null if only selling price changed)",
    )

    # Audit metadata
    reason = models.TextField(help_text="Why this adjustment was made (required)")
    adjusted_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="price_adjustments", help_text="Manager who made the adjustment"
    )
    adjusted_at = models.DateTimeField(default=timezone.now, help_text="When adjustment was made")

    # Business context
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="price_adjustments",
        help_text="Business this adjustment belongs to",
    )

    # Commission impact tracking
    commission_adjusted = models.BooleanField(
        default=False, help_text="Whether a compensating wallet transaction was created"
    )
    commission_adjustment_txn_id = models.IntegerField(
        null=True, blank=True, help_text="ID of compensating WalletTransaction (if any)"
    )

    class Meta:
        ordering = ["-adjusted_at"]
        indexes = [
            models.Index(fields=["sale", "-adjusted_at"]),
            models.Index(fields=["business", "-adjusted_at"]),
            models.Index(fields=["adjusted_by", "-adjusted_at"]),
        ]

    def __str__(self):
        return f"Price Adjustment #{self.id} for Sale #{self.sale_id}"

    @property
    def effective_selling_price(self):
        """Return the adjusted selling price or original if not changed."""
        return self.new_selling_price if self.new_selling_price is not None else self.original_selling_price

    @property
    def effective_cost_price(self):
        """Return the adjusted cost price or original if not changed."""
        return self.new_cost_price if self.new_cost_price is not None else self.original_cost_price

    @property
    def price_delta(self):
        """Calculate change in selling price."""
        if self.new_selling_price is None:
            return Decimal("0.00")
        return self.new_selling_price - self.original_selling_price

    @property
    def cost_delta(self):
        """Calculate change in cost price."""
        if self.new_cost_price is None or self.original_cost_price is None:
            return Decimal("0.00")
        return self.new_cost_price - self.original_cost_price


class UnsoldPriceEdit(models.Model):
    """
    Audit trail for price edits on unsold inventory items.

    Simpler than PriceAdjustment since no wallet/commission impact.
    """

    FIELD_CHOICES = [
        ("order_price", "Order Price (Cost)"),
        ("selling_price", "Selling Price"),
        ("both", "Both Prices"),
    ]

    # Link to inventory item
    item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.CASCADE,
        related_name="price_edits",
        help_text="Inventory item that was edited",
    )

    # What changed
    field_changed = models.CharField(max_length=20, choices=FIELD_CHOICES, help_text="Which price field(s) changed")

    # Old values
    old_order_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    old_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # New values
    new_order_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    new_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Audit metadata
    reason = models.TextField(help_text="Why this edit was made (required)")
    edited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="unsold_price_edits",
    )
    edited_at = models.DateTimeField(default=timezone.now)

    # Business context
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="unsold_price_edits",
    )

    class Meta:
        ordering = ["-edited_at"]
        indexes = [
            models.Index(fields=["item", "-edited_at"]),
            models.Index(fields=["business", "-edited_at"]),
            models.Index(fields=["edited_by", "-edited_at"]),
        ]

    def __str__(self):
        return f"Price Edit #{self.id} for Item #{self.item_id}"
