# inventory/models_cement.py
"""
Cement & Hardware vertical models - simple, focused on cement products.
NO agents, wallets, or timelogs - keep it basic like groceries.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ==============================================================================
# ENUMS
# ==============================================================================

class CementType(models.TextChoices):
    """Types of cement"""
    PPC = "ppc", "PPC (Portland Pozzolana Cement)"
    OPC = "opc", "OPC (Ordinary Portland Cement)"
    PSC = "psc", "PSC (Portland Slag Cement)"
    RHC = "rhc", "RHC (Rapid Hardening Cement)"
    SRC = "src", "SRC (Sulphate Resisting Cement)"
    OTHER = "other", "Other"


class HardwareCategory(models.TextChoices):
    """Hardware product categories"""
    CEMENT = "cement", "Cement"
    SAND = "sand", "Sand"
    GRAVEL = "gravel", "Gravel / Aggregate"
    BRICKS = "bricks", "Bricks / Blocks"
    STEEL = "steel", "Steel / Rebar"
    TIMBER = "timber", "Timber / Wood"
    PAINT = "paint", "Paint"
    TOOLS = "tools", "Tools"
    PLUMBING = "plumbing", "Plumbing"
    ELECTRICAL = "electrical", "Electrical"
    OTHER = "other", "Other"


# ==============================================================================
# CEMENT PRODUCT
# ==============================================================================

class CementProduct(models.Model):
    """
    Cement and hardware products.
    Simple model - no complex tracking.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="cement_products",
        db_index=True
    )
    
    # Product details
    name = models.CharField(max_length=200, help_text="Product name")
    category = models.CharField(
        max_length=30,
        choices=HardwareCategory.choices,
        default=HardwareCategory.CEMENT,
        help_text="Product category"
    )
    
    # Cement-specific (optional for non-cement products)
    cement_type = models.CharField(
        max_length=20,
        choices=CementType.choices,
        blank=True,
        default="",
        help_text="Type of cement (if applicable)"
    )
    
    # Stock (in bags for cement, units for others)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Current stock quantity (bags/units)"
    )
    reorder_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Alert when stock drops to or below this level"
    )
    
    # Pricing
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost per unit/bag"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit/bag"
    )
    
    # Optional fields
    description = models.TextField(blank=True, default="")
    brand = models.CharField(max_length=100, blank=True, default="")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Soft delete
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["business", "name"]),
            models.Index(fields=["business", "category"]),
            models.Index(fields=["business", "is_active"]),
        ]
        unique_together = ("business", "name", "category")
        verbose_name = "Cement/Hardware Product"
        verbose_name_plural = "Cement/Hardware Products"
    
    def __str__(self):
        if self.cement_type:
            return f"{self.name} ({self.get_cement_type_display()})"
        return self.name
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is at or below reorder level."""
        return self.quantity <= self.reorder_level
    
    @property
    def stock_value_cost(self) -> Decimal:
        """Total value at cost price."""
        return self.quantity * self.cost_price
    
    @property
    def stock_value_selling(self) -> Decimal:
        """Total value at selling price."""
        return self.quantity * self.selling_price


# ==============================================================================
# CEMENT STOCK IN
# ==============================================================================

class CementStockIn(models.Model):
    """
    Records stock additions for cement/hardware products.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="cement_stock_ins"
    )
    product = models.ForeignKey(
        CementProduct,
        on_delete=models.PROTECT,
        related_name="stock_ins"
    )
    
    # Stock details
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Quantity added (bags/units)"
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost per bag/unit"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per bag/unit"
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total cost (quantity * cost_price)"
    )
    
    # Supplier info (optional)
    supplier = models.CharField(max_length=200, blank=True, default="")
    
    # Who added
    added_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cement_stock_ins"
    )
    
    # Timestamps
    added_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-added_at"]
        indexes = [
            models.Index(fields=["business", "-added_at"]),
            models.Index(fields=["product", "-added_at"]),
        ]
        verbose_name = "Cement/Hardware Stock In"
        verbose_name_plural = "Cement/Hardware Stock Ins"
    
    def __str__(self):
        return f"{self.product.name} +{self.quantity} @ {self.added_at:%Y-%m-%d}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total_cost
        self.total_cost = self.quantity * self.cost_price
        super().save(*args, **kwargs)


# ==============================================================================
# CEMENT SALE
# ==============================================================================

class CementSale(models.Model):
    """
    Records cement/hardware sales.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="cement_sales"
    )
    product = models.ForeignKey(
        CementProduct,
        on_delete=models.PROTECT,
        related_name="sales"
    )
    
    # Sale details
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Quantity sold (bags/units)"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per bag/unit"
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost price per bag/unit (for profit calculation)"
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total sale amount (quantity * unit_price)"
    )
    
    # Payment
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("BANK", "Bank Transfer"),
        ("CREDIT", "Credit"),
    ]
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="CASH"
    )
    
    # Customer (optional)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=20, blank=True, default="")
    
    # Who made the sale
    sold_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cement_sales"
    )
    
    # Timestamps
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    # Soft delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cement_sales_deleted"
    )
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["product", "-sold_at"]),
            models.Index(fields=["sold_by", "-sold_at"]),
            models.Index(fields=["is_deleted"]),
        ]
        verbose_name = "Cement/Hardware Sale"
        verbose_name_plural = "Cement/Hardware Sales"
    
    def __str__(self):
        return f"{self.product.name} x{self.quantity} @ {self.sold_at:%Y-%m-%d %H:%M}"
    
    @property
    def profit(self) -> Decimal:
        """Calculate profit for this sale."""
        total_cost = self.unit_cost * self.quantity
        return self.total_amount - total_cost
    
    def save(self, *args, **kwargs):
        # Auto-calculate total_amount
        self.total_amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)


# ==============================================================================
# CEMENT COST
# ==============================================================================

class CementCost(models.Model):
    """
    Tracks operational costs for cement/hardware business.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="cement_costs"
    )
    
    # Cost details
    COST_TYPE_CHOICES = [
        ("RENT", "Rent"),
        ("UTILITIES", "Utilities"),
        ("TRANSPORT", "Transport / Delivery"),
        ("WAGES", "Wages"),
        ("MAINTENANCE", "Maintenance"),
        ("OTHER", "Other"),
    ]
    cost_type = models.CharField(max_length=20, choices=COST_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    description = models.TextField(blank=True, default="")
    
    # Who recorded
    recorded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cement_costs"
    )
    
    # Timestamps
    cost_date = models.DateField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-cost_date"]
        indexes = [
            models.Index(fields=["business", "-cost_date"]),
        ]
        verbose_name = "Cement/Hardware Cost"
        verbose_name_plural = "Cement/Hardware Costs"
    
    def __str__(self):
        return f"{self.get_cost_type_display()} - {self.amount} @ {self.cost_date}"

