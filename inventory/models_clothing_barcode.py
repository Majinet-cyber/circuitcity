# inventory/models_clothing_barcode.py
"""
Clothing Barcode Unit Model - Unique barcoded clothing items.

Similar to InventoryItem (phones with IMEI) and LaptopSerial (laptops with serial),
this model tracks individual barcoded clothing items as unique units.

Each barcode scan represents ONE physical unit with its own barcode, size, and prices.
"""
from decimal import Decimal

from django.core.validators import MinLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business, TenantManager


class ClothingBarcodeUnit(models.Model):
    """
    Individual barcoded clothing item tracked by barcode.

    Similar to InventoryItem for phones (IMEI) but uses barcode for clothing.
    Each unit is a unique physical item with its own barcode, size, and pricing.

    IMPORTANT:
    - Barcode must be UNIQUE per business (enforced by DB constraint)
    - Used for FAST SELL (scan -> auto-sell using stored prices)
    - NOT used for non-barcoded bulk stock (use ClothingVariant/MerchProduct quantity)
    """

    STATUS_CHOICES = [
        ("IN_STOCK", "In Stock"),
        ("SOLD", "Sold"),
    ]

    # --- TENANCY ---
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="clothing_barcode_units",
        db_index=True,
        help_text="Business this unit belongs to",
    )

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="clothing_barcode_units",
        db_index=True,
        help_text="Location where this unit is stocked",
    )

    # --- PRODUCT REFERENCE ---
    # Link to parent product (optional, for reporting/grouping)
    product = models.ForeignKey(
        "inventory.MerchProduct",
        on_delete=models.PROTECT,
        related_name="barcode_units",
        null=True,
        blank=True,
        help_text="Parent product (optional, for grouping)",
    )

    # --- BARCODE (UNIQUE IDENTIFIER) ---
    barcode = models.CharField(
        max_length=100,
        db_index=True,
        validators=[MinLengthValidator(3)],
        help_text="Barcode (unique per business, required)",
    )

    # --- CLOTHING ATTRIBUTES ---
    # Store size directly on unit (required for clothing)
    size = models.CharField(max_length=20, help_text="Size for this unit (e.g., M, 42, 32x30)")

    # Optional: store category/subcategory for filtering
    category = models.CharField(max_length=50, blank=True, default="", help_text="Category (e.g., shoes, shirt, jeans)")

    subcategory = models.CharField(
        max_length=50, blank=True, default="", help_text="Subcategory (e.g., sneaker, boot, t-shirt)"
    )

    # Optional: color
    color = models.CharField(max_length=50, blank=True, default="", help_text="Color (optional)")

    # Optional: brand
    brand = models.CharField(max_length=100, blank=True, default="", help_text="Brand (optional)")

    # --- PRICING ---
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Cost price when purchased",
    )

    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Selling price (required, must be > 0)",
    )

    # --- STATUS ---
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="IN_STOCK",
        db_index=True,
        help_text="Current status of this unit",
    )

    # --- TIMESTAMPS ---
    received_at = models.DateField(default=timezone.localdate, help_text="Date unit was received/stocked")

    sold_at = models.DateField(null=True, blank=True, db_index=True, help_text="Date unit was sold (null if not sold)")

    # --- ARCHIVE SUPPORT ---
    is_active = models.BooleanField(default=True, db_index=True, help_text="False if archived/deleted")

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    archived_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="archived_clothing_barcode_units"
    )

    # --- AUDIT ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clothing_barcode_units",
        help_text="User who created this unit",
    )

    # --- MANAGER ---
    objects = TenantManager()

    class Meta:
        verbose_name = "Clothing Barcode Unit"
        verbose_name_plural = "Clothing Barcode Units"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "is_active"]),
            models.Index(fields=["business", "barcode"]),
            models.Index(fields=["business", "category", "status"]),
            models.Index(fields=["location", "status"]),
            models.Index(fields=["sold_at"]),
        ]
        constraints = [
            # CRITICAL: Barcode must be unique per business
            models.UniqueConstraint(fields=["business", "barcode"], name="unique_clothing_barcode_per_business"),
        ]

    def __str__(self):
        return f"{self.barcode} - Size {self.size} ({self.get_status_display()})"

    @property
    def profit(self):
        """Calculate profit if sold"""
        if self.status == "SOLD":
            return self.selling_price - self.cost_price
        return Decimal("0.00")

    def mark_sold(self, sold_date=None):
        """Mark this unit as sold"""
        self.status = "SOLD"
        self.sold_at = sold_date or timezone.localdate()
        self.save(update_fields=["status", "sold_at", "updated_at"])

    def archive(self, user=None):
        """Archive this unit (soft delete)"""
        self.is_active = False
        self.archived_at = timezone.now()
        self.archived_by = user
        self.save(update_fields=["is_active", "archived_at", "archived_by", "updated_at"])
