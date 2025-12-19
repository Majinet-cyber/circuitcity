# inventory/models_unique_products.py
"""
Unique Products System - Barcode/SKU based inventory for Fast Sell verticals.

This module provides a separate inventory system for products with unique identifiers (barcode/SKU).
It works alongside existing bundled products without replacing them.

Applies to:
- Clothing
- Pharmacy (Cosmetics subset)
- Groceries
- Any vertical with Fast Sell capability
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum, Count
from django.utils import timezone

from tenants.models import Business, TenantManager

User = get_user_model()


class UniqueProduct(models.Model):
    """
    Unique Product with barcode/SKU for Fast Sell.
    
    Rules:
    - Each product has a unique barcode/SKU per business
    - Used exclusively by Fast Sell workflows
    - Does NOT replace bundled products
    - Tracks individual item sales and stock
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="unique_products",
        db_index=True
    )
    
    # Vertical (for filtering and routing)
    vertical = models.CharField(
        max_length=20,
        choices=[
            ('clothing', 'Clothing'),
            ('pharmacy', 'Pharmacy'),
            ('cosmetics', 'Cosmetics'),
            ('groceries', 'Groceries'),
        ],
        help_text="Vertical this product belongs to"
    )
    
    # Product identification
    barcode = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Barcode or SKU code (must be unique per business)"
    )
    name = models.CharField(
        max_length=255,
        help_text="Product name with any attributes (e.g., 'White Dress XL', 'Sugar 9kg bundle')"
    )
    description = models.TextField(blank=True, default="")
    
    # Stock
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Current stock quantity"
    )
    unit = models.CharField(
        max_length=50,
        default="unit",
        help_text="Unit of measurement (pieces, kg, liters, etc.)"
    )
    
    # Pricing (cost is optional but recommended)
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Cost per unit (optional)"
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit (required)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unique_products_created"
    )
    
    # Soft delete
    is_active = models.BooleanField(default=True, db_index=True)
    
    objects = TenantManager()
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "barcode"], name="uniq_prod_biz_barcode_idx"),
            models.Index(fields=["business", "vertical", "is_active"], name="uniq_prod_biz_vert_active_idx"),
            models.Index(fields=["business", "is_active", "name"], name="uniq_prod_biz_active_name_idx"),
        ]
        constraints = [
            # Barcode must be unique per business (for active products)
            models.UniqueConstraint(
                fields=["business", "barcode"],
                condition=Q(is_active=True),
                name="unique_barcode_per_business"
            )
        ]
        verbose_name = "Unique Product"
        verbose_name_plural = "Unique Products"
    
    def __str__(self):
        return f"{self.name} ({self.barcode})"
    
    @property
    def stock_value_cost(self):
        """Current stock value at cost basis."""
        return self.quantity * self.cost_price
    
    @property
    def stock_value_selling(self):
        """Current stock value at selling price."""
        return self.quantity * self.selling_price
    
    @property
    def profit_margin(self):
        """Profit margin percentage."""
        if self.selling_price <= 0:
            return Decimal("0.00")
        return ((self.selling_price - self.cost_price) / self.selling_price) * 100
    
    @property
    def is_in_stock(self):
        """Check if product has stock available."""
        return self.quantity > 0
    
    def can_sell(self, quantity: Decimal) -> bool:
        """Check if we can sell the requested quantity."""
        return self.is_active and self.quantity >= quantity > 0


class UniqueProductStockIn(models.Model):
    """
    Stock-in record for unique products.
    Tracks when and how much stock was added.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="unique_product_stock_ins",
        db_index=True
    )
    product = models.ForeignKey(
        UniqueProduct,
        on_delete=models.CASCADE,
        related_name="stock_ins"
    )
    
    # Stock details
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)]
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)]
    )
    
    # Additional info
    supplier = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    
    # Metadata
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="unique_product_stock_ins_added"
    )
    
    objects = TenantManager()
    
    class Meta:
        ordering = ["-added_at"]
        indexes = [
            models.Index(fields=["business", "-added_at"]),
            models.Index(fields=["product", "-added_at"]),
        ]
        verbose_name = "Unique Product Stock In"
        verbose_name_plural = "Unique Product Stock Ins"
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} @ {self.added_at.strftime('%Y-%m-%d')}"


class UniqueSale(models.Model):
    """
    Sales record for unique products sold via Fast Sell.
    
    This is the single source of truth for coded product sales.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="unique_sales",
        db_index=True
    )
    product = models.ForeignKey(
        UniqueProduct,
        on_delete=models.CASCADE,
        related_name="sales"
    )
    
    # Sale details
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        help_text="Cost per unit at time of sale"
    )
    
    # Payment
    payment_method = models.CharField(
        max_length=20,
        default="CASH",
        choices=[
            ("CASH", "Cash"),
            ("MOBILE_MONEY", "Mobile Money"),
            ("CARD", "Card"),
            ("BANK_TRANSFER", "Bank Transfer"),
        ]
    )
    
    # Customer (optional)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    
    # Metadata
    sold_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sold_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="unique_sales"
    )
    
    # Soft delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    
    objects = TenantManager()
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["product", "-sold_at"]),
            models.Index(fields=["business", "is_deleted", "-sold_at"]),
        ]
        verbose_name = "Unique Sale"
        verbose_name_plural = "Unique Sales"
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity} @ {self.sold_at.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def total_amount(self):
        """Total revenue for this sale."""
        return self.quantity * self.unit_price
    
    @property
    def total_cost(self):
        """Total cost for this sale."""
        return self.quantity * self.unit_cost
    
    @property
    def profit(self):
        """Profit for this sale."""
        return self.total_amount - self.total_cost
    
    @property
    def profit_margin(self):
        """Profit margin percentage."""
        if self.total_amount <= 0:
            return Decimal("0.00")
        return (self.profit / self.total_amount) * 100

