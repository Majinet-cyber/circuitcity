# inventory/models_grocery.py
"""
Grocery vertical models - simple, no agents/wallets/timelogs.
Focus on: Costs, Stock In, Sell, Dashboard, Analytics, Quotes.
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

class GroceryCategory(models.TextChoices):
    """Product categories for grocery store"""
    GRAINS_CEREALS = "grains_cereals", "Grains & Cereals"
    COOKING_OIL = "cooking_oil", "Cooking Oil"
    SUGAR_SALT = "sugar_salt", "Sugar & Salt"
    BEVERAGES = "beverages", "Beverages"
    DAIRY = "dairy", "Dairy Products"
    SNACKS = "snacks", "Snacks"
    HOUSEHOLD = "household", "Household Items"
    PERSONAL_CARE = "personal_care", "Personal Care"
    OTHER = "other", "Other"


class GroceryUnitType(models.TextChoices):
    """Unit types for measuring grocery products"""
    KG = "kg", "Kilogram (kg)"
    UNIT = "unit", "Unit (piece)"
    BAG = "bag", "Bag"
    DOZEN = "dozen", "Dozen"
    LITRE = "litre", "Litre"
    GRAM = "gram", "Gram"
    PACKET = "packet", "Packet"


class GrocerySaleType(models.TextChoices):
    """Type of grocery sale"""
    RETAIL = "retail", "Retail Sale"
    WHOLESALE = "wholesale", "Wholesale Sale"


# ==============================================================================
# GROCERY PRODUCT
# ==============================================================================

class GroceryProduct(models.Model):
    """
    Grocery product with flexible unit types.
    Simple model - no complex batch tracking.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="grocery_products",
        db_index=True
    )
    
    # Product details
    name = models.CharField(max_length=200, help_text="Product name")
    category = models.CharField(
        max_length=30,
        choices=GroceryCategory.choices,
        default=GroceryCategory.OTHER,
        help_text="Product category"
    )
    unit_type = models.CharField(
        max_length=20,
        choices=GroceryUnitType.choices,
        default=GroceryUnitType.UNIT,
        help_text="Unit of measurement"
    )
    
    # Stock
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Current stock quantity"
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
        help_text="Cost per unit"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit"
    )
    
    # Optional fields
    barcode = models.CharField(max_length=100, blank=True, default="", db_index=True)
    description = models.TextField(blank=True, default="")
    
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
        unique_together = ("business", "name", "unit_type")
        verbose_name = "Grocery Product"
        verbose_name_plural = "Grocery Products"
    
    def __str__(self):
        return f"{self.name} ({self.get_unit_type_display()})"
    
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
# GROCERY STOCK IN
# ==============================================================================

class GroceryStockIn(models.Model):
    """
    Records stock additions for grocery products.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="grocery_stock_ins"
    )
    product = models.ForeignKey(
        GroceryProduct,
        on_delete=models.PROTECT,
        related_name="stock_ins"
    )
    
    # Stock details
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Quantity added"
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost per unit"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit"
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
        related_name="grocery_stock_ins"
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
        verbose_name = "Grocery Stock In"
        verbose_name_plural = "Grocery Stock Ins"
    
    def __str__(self):
        return f"{self.product.name} +{self.quantity} @ {self.added_at:%Y-%m-%d}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate total_cost
        self.total_cost = self.quantity * self.cost_price
        super().save(*args, **kwargs)


# ==============================================================================
# GROCERY SALE
# ==============================================================================

class GrocerySale(models.Model):
    """
    Records grocery sales (retail or wholesale).
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="grocery_sales"
    )
    product = models.ForeignKey(
        GroceryProduct,
        on_delete=models.PROTECT,
        related_name="sales"
    )
    
    # Sale details
    sale_type = models.CharField(
        max_length=20,
        choices=GrocerySaleType.choices,
        default=GrocerySaleType.RETAIL,
        help_text="Retail or Wholesale"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Quantity sold"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit"
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost price per unit (for profit calculation)"
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
        related_name="grocery_sales"
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
        related_name="grocery_sales_deleted"
    )
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["product", "-sold_at"]),
            models.Index(fields=["sold_by", "-sold_at"]),
            models.Index(fields=["is_deleted"]),
        ]
        verbose_name = "Grocery Sale"
        verbose_name_plural = "Grocery Sales"
    
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
# GROCERY COST
# ==============================================================================

class GroceryCost(models.Model):
    """
    Tracks operational costs for grocery business.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="grocery_costs"
    )
    
    # Cost details
    COST_TYPE_CHOICES = [
        ("RENT", "Rent"),
        ("UTILITIES", "Utilities (Water, Electricity)"),
        ("TRANSPORT", "Transport"),
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
        related_name="grocery_costs"
    )
    
    # Timestamps
    cost_date = models.DateField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-cost_date"]
        indexes = [
            models.Index(fields=["business", "-cost_date"]),
        ]
        verbose_name = "Grocery Cost"
        verbose_name_plural = "Grocery Costs"
    
    def __str__(self):
        return f"{self.get_cost_type_display()} - {self.amount} @ {self.cost_date}"

