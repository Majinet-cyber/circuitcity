# inventory/models_phone_products.py
"""
Phone Product Catalog - Curated, editable electronics SKU definitions for PHONES businesses.

Extended to support Phones, Laptops, and Desktops (category discriminator).
Phones use ram_gb/rom_gb and IMEI tracking; Laptops/Desktops use specs and serial via ElectronicsStockItem.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


class ElectronicsCategory(models.TextChoices):
    """Product type within electronics vertical."""

    PHONE = "PHONE", "Phone"
    LAPTOP = "LAPTOP", "Laptop"
    DESKTOP = "DESKTOP", "Desktop"


class PhoneProductCatalog(models.Model):
    """
    Curated phone product definition for a business.

    This is NOT the same as the Product model (which is global SKU catalog).
    This is a business-specific, editable catalog of phone models they want to sell.

    When an agent records a sale, they can pick from this catalog to quickly
    fill in brand/model/RAM/ROM, then add IMEI and price.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="phone_catalog_products",
        db_index=True,
        help_text="Business this product belongs to",
    )

    # Category: PHONE | LAPTOP | DESKTOP (default PHONE for backward compat)
    category = models.CharField(
        max_length=10,
        choices=ElectronicsCategory.choices,
        default=ElectronicsCategory.PHONE,
        db_index=True,
        help_text="Product type: Phone, Laptop, or Desktop",
    )

    # Brand and model info
    brand = models.CharField(max_length=50, db_index=True, help_text="Phone brand (e.g., TECNO, ITEL, SAMSUNG)")
    model_name = models.CharField(max_length=100, help_text="Model name (e.g., Spark 40, Pop 10, A15)")

    # RAM/ROM variant (phones: required; laptops/desktops: use 0,0 and fill ram_str/storage_str)
    ram_gb = models.PositiveIntegerField(default=0, help_text="RAM in GB (e.g., 4, 8)")
    rom_gb = models.PositiveIntegerField(default=0, help_text="ROM/Storage in GB (e.g., 128, 256)")
    variant_label = models.CharField(
        max_length=20, blank=True, help_text="Display label for variant (e.g., '4+128', '8+256')"
    )

    # Laptop/Desktop specs (optional for phones)
    cpu = models.CharField(max_length=120, blank=True, default="", help_text="CPU (e.g., Intel i5-1135G7)")
    ram_str = models.CharField(
        max_length=50, blank=True, default="", help_text="RAM spec (e.g., 16GB) for laptop/desktop"
    )
    storage_str = models.CharField(
        max_length=80, blank=True, default="", help_text="Storage (e.g., 512GB SSD) for laptop/desktop"
    )
    screen_size = models.CharField(max_length=20, blank=True, default="", help_text="Screen size (e.g., 15.6\")")
    gpu = models.CharField(max_length=80, blank=True, default="", help_text="GPU (optional)")
    os = models.CharField(max_length=60, blank=True, default="", help_text="OS (e.g., Windows 11)")
    condition = models.CharField(
        max_length=20, blank=True, default="", help_text="Condition: New, Used, A, B (optional)"
    )

    # Optional internal model number (editable by merchant)
    model_number = models.CharField(
        max_length=50, blank=True, default="", help_text="Internal model/SKU number (optional, editable)"
    )

    # Default pricing (optional, can be overridden at sale time)
    default_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default cost price (optional)",
    )
    default_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default selling price (optional)",
    )

    # Metadata
    is_active = models.BooleanField(
        default=True, db_index=True, help_text="Whether this product is active in the catalog"
    )
    is_flagship = models.BooleanField(default=False, help_text="Mark as flagship/featured product")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="phone_products_created"
    )

    # Main product photo (all categories)
    main_image = models.ImageField(
        upload_to="electronics/products/%Y/%m/",
        null=True,
        blank=True,
        help_text="Main product photo",
    )

    class Meta:
        ordering = ["category", "brand", "model_name", "ram_gb", "rom_gb"]
        indexes = [
            models.Index(fields=["business", "brand"], name="phoneprod_biz_brand_idx"),
            models.Index(fields=["business", "is_active"], name="phoneprod_biz_active_idx"),
            models.Index(fields=["brand", "model_name"], name="phoneprod_brand_model_idx"),
            models.Index(fields=["business", "category"], name="phoneprod_biz_category_idx"),
        ]
        unique_together = [
            ("business", "category", "brand", "model_name", "ram_gb", "rom_gb", "ram_str", "storage_str")
        ]

    def __str__(self):
        if self.category == ElectronicsCategory.PHONE:
            variant = self.variant_label or f"{self.ram_gb}+{self.rom_gb}"
            return f"{self.brand} {self.model_name} ({variant})"
        spec = self.ram_str or self.storage_str or ""
        if spec:
            return f"{self.brand} {self.model_name} ({spec})"
        return f"{self.brand} {self.model_name}"

    def save(self, *args, **kwargs):
        if self.category == ElectronicsCategory.PHONE and not self.variant_label and (self.ram_gb or self.rom_gb):
            self.variant_label = f"{self.ram_gb}+{self.rom_gb}"
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        """Full display name for UI"""
        if self.category == ElectronicsCategory.PHONE:
            variant = self.variant_label or f"{self.ram_gb}+{self.rom_gb}"
            return f"{self.brand} {self.model_name} ({variant})"
        parts = [self.brand, self.model_name]
        if self.ram_str or self.storage_str:
            parts.append(f"{self.ram_str} / {self.storage_str}".strip(" /"))
        return " ".join(parts)

    @property
    def has_pricing(self):
        """Check if default pricing is set"""
        return self.default_cost_price is not None and self.default_selling_price is not None

    @property
    def is_phone(self):
        return self.category == ElectronicsCategory.PHONE

    @property
    def is_laptop(self):
        return self.category == ElectronicsCategory.LAPTOP

    @property
    def is_desktop(self):
        return self.category == ElectronicsCategory.DESKTOP


class ElectronicsStockItem(models.Model):
    """
    One physical laptop or desktop unit, tracked by serial number.
    Phones use InventoryItem (IMEI). Laptops/Desktops use this model.
    """

    STATUS_CHOICES = [("IN_STOCK", "In Stock"), ("SOLD", "Sold")]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="electronics_stock_items", db_index=True
    )
    catalog_product = models.ForeignKey(
        PhoneProductCatalog,
        on_delete=models.PROTECT,
        related_name="stock_items",
        limit_choices_to={"category__in": [ElectronicsCategory.LAPTOP, ElectronicsCategory.DESKTOP]},
        help_text="Catalog model (Laptop or Desktop)",
    )
    serial_number = models.TextField(
        db_index=True,
        help_text="Serial number (unique per business); any length",
    )
    current_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="electronics_stock_items",
        db_index=True,
    )
    received_at = models.DateField(default=timezone.localdate, help_text="Date received/stocked")
    order_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Cost price"
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Selling price"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="IN_STOCK", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_electronics_stock_items",
    )
    sold_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sold_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="electronics_items_sold",
    )
    payment_method = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=[
            ("CASH", "Cash"),
            ("BANK", "Bank Transfer"),
            ("MOBILE_MONEY", "Mobile Money"),
        ],
        help_text="Payment method used at sale time",
    )
    battery_health = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Battery health indicator (e.g. 'Good', '85%'). Laptops/desktops only.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Electronics stock item (laptop/desktop)"
        verbose_name_plural = "Electronics stock items"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["business", "serial_number", "is_active"],
                name="electronics_stock_biz_serial",
            ),
            models.Index(
                fields=["business", "status", "is_active"],
                name="electronics_stock_status",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "serial_number"],
                condition=models.Q(is_active=True),
                name="unique_electronics_serial_per_business",
            )
        ]

    def __str__(self):
        return f"{self.catalog_product} — {self.serial_number}"

    @property
    def display_name(self):
        if len(self.serial_number) > 20:
            return f"{self.catalog_product.display_name} (SN: {self.serial_number[:20]}...)"
        return f"{self.catalog_product.display_name} (SN: {self.serial_number})"
