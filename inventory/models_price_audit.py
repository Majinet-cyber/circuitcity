# inventory/models_price_audit.py
"""
Price Change Audit Models - Global feature for all verticals
Tracks all price edits for accountability and compliance
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business, Location

User = get_user_model()


class PriceChangeScope(models.TextChoices):
    """Scope of price change"""

    PRODUCT_PRICE = "product_price", "Product Current Price"
    SALE_LINE = "sale_line", "Sale Line Price Correction"


class PriceChangeLog(models.Model):
    """
    Audit trail for all price changes across the system.

    Used for:
    - Tracking product selling price updates (PRODUCT_PRICE)
    - Tracking historical sale price corrections (SALE_LINE)

    Features:
    - Manager-only access (enforced at view level)
    - Required reason field for accountability
    - Full audit trail (who, when, what, why)
    - Business-scoped for multi-tenancy
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="price_changes",
        db_index=True,
        help_text="Business where price change occurred",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Location (if applicable)",
    )

    # Who changed it
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes_made",
        help_text="Manager who made the change",
    )

    # What was changed
    scope = models.CharField(
        max_length=20, choices=PriceChangeScope.choices, db_index=True, help_text="What type of price was changed"
    )

    # References (nullable because scope determines which is used)
    product = models.ForeignKey(
        "inventory.MerchProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Product (for PRODUCT_PRICE scope)",
    )

    # Sale line references (vertical-specific, all nullable)
    cement_sale = models.ForeignKey(
        "inventory.CementSale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Cement sale (for SALE_LINE scope)",
    )
    liquor_sale = models.ForeignKey(
        "inventory.LiquorSale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Liquor sale (for SALE_LINE scope)",
    )
    pharmacy_sale = models.ForeignKey(
        "inventory.PharmacySale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Pharmacy sale (for SALE_LINE scope)",
    )
    grocery_sale = models.ForeignKey(
        "inventory.GrocerySale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Grocery sale (for SALE_LINE scope)",
    )
    clothing_sale = models.ForeignKey(
        "inventory.ClothingSale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
        help_text="Clothing sale (for SALE_LINE scope)",
    )

    # Price details
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Price before change",
    )
    new_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))], help_text="Price after change"
    )

    # Accountability
    reason = models.CharField(max_length=500, help_text="Required: Why was this price changed?")

    # Metadata
    created_at = models.DateTimeField(
        default=timezone.now, db_index=True, editable=False, help_text="When change was made"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "scope", "-created_at"]),
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        verbose_name = "Price Change"
        verbose_name_plural = "Price Changes"

    def __str__(self):
        return f"{self.get_scope_display()}: {self.old_price} → {self.new_price} by {self.user}"

    @property
    def price_difference(self):
        """Calculate the price change amount"""
        return self.new_price - self.old_price

    @property
    def price_change_pct(self):
        """Calculate the price change percentage"""
        if self.old_price > 0:
            return ((self.new_price - self.old_price) / self.old_price) * 100
        return Decimal("0.00")
