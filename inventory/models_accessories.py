# inventory/models_accessories.py
"""
Accessories models - quantity-based stock system for phone accessories.
Separate from IMEI-based phones to avoid conflicts.
"""
from __future__ import annotations

import re
import secrets
import string
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


def normalize_barcode(raw: str) -> str:
    """
    Normalize barcode for consistent storage and lookup.
    - Trim whitespace
    - Remove spaces/hyphens
    - Convert to uppercase
    - Keep only alphanumerics for numeric barcodes (digits only)
    """
    if not raw:
        return ""
    # Remove whitespace, hyphens, spaces
    cleaned = re.sub(r"[\s\-]+", "", str(raw).strip())
    # Uppercase for consistency
    cleaned = cleaned.upper()
    # If all digits, keep only digits (for EAN/UPC)
    if cleaned.isdigit():
        return cleaned
    # Otherwise return cleaned alphanumeric
    return re.sub(r"[^A-Z0-9]", "", cleaned)


def generate_sku() -> str:
    """Generate a unique SKU code for accessories."""
    timestamp = timezone.now().strftime("%y%m%d")
    random_part = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"ACC-{timestamp}-{random_part}"


class AccessoryCategory(models.TextChoices):
    """Accessory categories matching the requirements."""

    POWERBANK = "powerbank", "Powerbank"
    CHARGER = "charger", "Charger"
    CABLE = "cable", "Data Cable"
    BATTERY = "battery", "Battery"
    HEADSET = "headset", "Headset/Earbuds"
    SPEAKER = "speaker", "Speaker"
    OTHER = "other", "Other"


class AccessoryProduct(models.Model):
    """
    Quantity-based accessory product.
    Completely separate from IMEI-based phones.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="accessory_products",
        db_index=True,
        help_text="Business that owns this accessory product",
    )

    # Product identification
    name = models.CharField(max_length=160, help_text="Product name (e.g., 'Oraimo Powerbank OPB-P1100D')")
    category = models.CharField(
        max_length=20, choices=AccessoryCategory.choices, db_index=True, help_text="Accessory category"
    )
    brand = models.CharField(
        max_length=80, blank=True, default="", help_text="Brand name (optional, e.g., 'Oraimo', 'Tecno')"
    )

    # SKU/Code - unique per business
    sku = models.CharField(max_length=64, db_index=True, help_text="Internal SKU/code (auto-generated if not provided)")

    # Barcode - optional, unique per business when provided
    barcode = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Product barcode (EAN, UPC, QR, etc.) - optional",
    )

    # Pricing (defaults for stock-in, can be overridden per stock entry)
    default_order_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], help_text="Default order/cost price (MWK)"
    )
    default_selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], help_text="Default selling price (MWK)"
    )

    # Metadata
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ("business", "name"),  # Product name unique per business
            ("business", "sku"),  # SKU unique per business
        ]
        indexes = [
            models.Index(fields=["business", "name"], name="acc_prod_biz_name_idx"),
            models.Index(fields=["business", "category"], name="acc_prod_biz_cat_idx"),
            models.Index(fields=["business", "barcode"], name="acc_prod_biz_barcode_idx"),
            models.Index(fields=["business", "is_active"], name="acc_prod_biz_active_idx"),
        ]
        # Enforce barcode uniqueness per business when provided (nullable unique)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "barcode"],
                condition=models.Q(barcode__isnull=False) & ~models.Q(barcode=""),
                name="uniq_accessory_barcode_per_business",
            )
        ]
        ordering = ["name"]
        verbose_name = "Accessory Product"
        verbose_name_plural = "Accessory Products"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def save(self, *args, **kwargs):
        """Auto-generate SKU if not provided, normalize barcode."""
        # Auto-generate SKU if missing
        if not self.sku:
            self.sku = generate_sku()

        # Normalize barcode for consistent storage
        if self.barcode:
            self.barcode = normalize_barcode(self.barcode)

        super().save(*args, **kwargs)

    def clean(self):
        """Validate product fields."""
        errors = {}

        # Validate name
        if not self.name or not self.name.strip():
            errors["name"] = "Product name is required."

        # Validate prices
        if self.default_order_price < 0:
            errors["default_order_price"] = "Order price must be non-negative."
        if self.default_selling_price < 0:
            errors["default_selling_price"] = "Selling price must be non-negative."

        # Validate barcode uniqueness per business
        if self.barcode:
            normalized = normalize_barcode(self.barcode)
            existing = AccessoryProduct.objects.filter(business=self.business, barcode=normalized).exclude(pk=self.pk)
            if existing.exists():
                errors["barcode"] = f"Barcode '{self.barcode}' already exists for another accessory in this business."

        if errors:
            raise ValidationError(errors)

    @property
    def total_stock(self) -> int:
        """Get total quantity on hand across all locations."""
        return self.stock_entries.aggregate(total=models.Sum("qty_on_hand"))["total"] or 0

    @property
    def stock_value(self) -> Decimal:
        """Get total stock value (cost basis) across all locations."""
        total = Decimal("0.00")
        for stock in self.stock_entries.all():
            total += stock.stock_value
        return total


class AccessoryStock(models.Model):
    """
    Quantity-based stock for accessories at a specific location.
    Tracks inventory levels and cost basis (average cost method).
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="accessory_stocks",
        db_index=True,
        help_text="Business that owns this stock",
    )

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="accessory_stocks",
        help_text="Store/warehouse location",
    )

    product = models.ForeignKey(
        AccessoryProduct, on_delete=models.PROTECT, related_name="stock_entries", help_text="Accessory product"
    )

    # Quantity on hand
    qty_on_hand = models.IntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="Current quantity in stock"
    )

    # Cost basis (weighted average cost)
    avg_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Average cost per unit (MWK)",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ("business", "location", "product"),  # One stock entry per product per location
        ]
        indexes = [
            models.Index(fields=["business", "location"], name="acc_stock_biz_loc_idx"),
            models.Index(fields=["business", "product"], name="acc_stock_biz_prod_idx"),
            models.Index(fields=["product", "qty_on_hand"], name="acc_stock_prod_qty_idx"),
        ]
        ordering = ["-updated_at"]
        verbose_name = "Accessory Stock"
        verbose_name_plural = "Accessory Stocks"

    def __str__(self):
        return f"{self.product.name} @ {self.location.name}: {self.qty_on_hand} units"

    @property
    def stock_value(self) -> Decimal:
        """Total value of stock on hand (qty * avg_cost)."""
        return Decimal(self.qty_on_hand) * self.avg_cost

    def add_stock(self, qty: int, unit_cost: Decimal):
        """
        Add stock using weighted average cost method.

        Args:
            qty: Quantity to add (positive integer)
            unit_cost: Cost per unit for this batch
        """
        if qty <= 0:
            raise ValueError("Quantity must be positive.")
        if unit_cost < 0:
            raise ValueError("Unit cost must be non-negative.")

        # Calculate new weighted average cost
        old_value = self.stock_value
        new_value = Decimal(qty) * unit_cost
        new_qty = self.qty_on_hand + qty

        if new_qty > 0:
            self.avg_cost = (old_value + new_value) / Decimal(new_qty)
        else:
            self.avg_cost = unit_cost

        self.qty_on_hand = new_qty
        self.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])

    def remove_stock(self, qty: int):
        """
        Remove stock (e.g., for a sale).
        Cost basis (avg_cost) remains unchanged.

        Args:
            qty: Quantity to remove (positive integer)

        Raises:
            ValueError: If insufficient stock
        """
        if qty <= 0:
            raise ValueError("Quantity must be positive.")
        if qty > self.qty_on_hand:
            raise ValueError(f"Insufficient stock: requested {qty}, available {self.qty_on_hand}")

        self.qty_on_hand -= qty
        self.save(update_fields=["qty_on_hand", "updated_at"])

    @classmethod
    def get_or_create_stock(cls, business, location, product):
        """
        Get or create a stock entry for a product at a location.
        Safe helper to avoid duplicate stock entries.
        """
        stock, created = cls.objects.get_or_create(
            business=business,
            location=location,
            product=product,
            defaults={
                "qty_on_hand": 0,
                "avg_cost": product.default_order_price,
            },
        )
        return stock


class AccessoryStockLog(models.Model):
    """
    Audit log for accessory stock movements (stock-in, sales, adjustments).
    """

    ACTION_CHOICES = [
        ("STOCK_IN", "Stock In"),
        ("SALE", "Sale"),
        ("ADJUSTMENT", "Adjustment"),
        ("RETURN", "Return"),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="accessory_stock_logs", db_index=True)

    product = models.ForeignKey(
        AccessoryProduct, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_logs"
    )

    location = models.ForeignKey(
        "inventory.Location", on_delete=models.SET_NULL, null=True, blank=True, related_name="accessory_stock_logs"
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)

    quantity = models.IntegerField(help_text="Quantity moved (positive for stock-in, negative for sale/adjustment)")

    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Cost per unit (for stock-in)"
    )

    by_user = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="accessory_stock_logs"
    )

    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "action", "created_at"], name="acc_log_biz_act_time_idx"),
            models.Index(fields=["product", "created_at"], name="acc_log_prod_time_idx"),
        ]
        verbose_name = "Accessory Stock Log"
        verbose_name_plural = "Accessory Stock Logs"

    def __str__(self):
        action_label = self.get_action_display()
        product_name = self.product.name if self.product else "Unknown"
        return f"{action_label}: {product_name} x {self.quantity} @ {self.created_at:%Y-%m-%d %H:%M}"


# Export models for easy import
__all__ = [
    "AccessoryProduct",
    "AccessoryStock",
    "AccessoryStockLog",
    "AccessoryCategory",
    "normalize_barcode",
    "generate_sku",
]
