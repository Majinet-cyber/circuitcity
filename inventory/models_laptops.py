# inventory/models_laptops.py
"""
Laptop product and serial tracking models.

Laptops are tracked by serial number (not IMEI like phones).
Each laptop has a unique serial per business.
"""
from __future__ import annotations

from django.db import models
from django.core.validators import MinLengthValidator
from django.utils import timezone

from tenants.models import Business, TenantManager


class LaptopBrand(models.TextChoices):
    """Common laptop brands in Malawi"""

    DELL = "dell", "Dell"
    LENOVO = "lenovo", "Lenovo"
    APPLE = "apple", "Apple (MacBook)"
    HP = "hp", "HP"
    ACER = "acer", "Acer"
    ASUS = "asus", "Asus"
    TOSHIBA = "toshiba", "Toshiba"
    SAMSUNG = "samsung", "Samsung"
    OTHER = "other", "Other"


class LaptopProduct(models.Model):
    """
    Laptop product catalog (similar to PhoneProductCatalog).

    Defines a laptop model with brand, specs, and pricing.
    Individual laptops are tracked via LaptopSerial.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="laptop_products", db_index=True)

    brand = models.CharField(max_length=50, choices=LaptopBrand.choices, db_index=True)

    model_name = models.CharField(max_length=100, help_text="Model name (e.g., 'ThinkPad X1', 'MacBook Pro 13')")

    # Specs
    ram = models.CharField(max_length=50, blank=True, help_text="RAM specification (e.g., '8GB', '16GB DDR4')")

    storage = models.CharField(
        max_length=50, blank=True, help_text="Storage specification (e.g., '256GB SSD', '1TB HDD')"
    )

    battery_life = models.CharField(max_length=50, blank=True, help_text="Battery life (e.g., '8 hours', '12 hours')")

    # Pricing
    default_cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Default cost price for this model"
    )

    default_selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Default selling price for this model"
    )

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Laptop Product"
        verbose_name_plural = "Laptop Products"
        ordering = ["brand", "model_name"]
        unique_together = [("business", "brand", "model_name", "ram", "storage")]
        indexes = [
            models.Index(fields=["business", "brand"], name="laptop_biz_brand"),
            models.Index(fields=["business", "is_active"], name="laptop_biz_active"),
        ]

    def __str__(self):
        return f"{self.get_brand_display()} {self.model_name}"

    @property
    def display_name(self):
        """Human-readable display name"""
        parts = [self.get_brand_display(), self.model_name]
        if self.ram:
            parts.append(f"{self.ram} RAM")
        if self.storage:
            parts.append(f"{self.storage}")
        return " ".join(parts)


class LaptopSerial(models.Model):
    """
    Individual laptop instance tracked by serial number.

    Similar to InventoryItem for phones, but uses serial instead of IMEI.
    """

    STATUS_CHOICES = [
        ("IN_STOCK", "In Stock"),
        ("SOLD", "Sold"),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="laptop_serials", db_index=True)

    location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, related_name="laptop_serials", db_index=True
    )

    product = models.ForeignKey(
        LaptopProduct, on_delete=models.PROTECT, related_name="serials", help_text="Laptop product model"
    )

    # Serial number (required, unique per business)
    serial = models.CharField(
        max_length=100,
        db_index=True,
        validators=[MinLengthValidator(3)],
        help_text="Laptop serial number (any format, must be unique per business)",
    )

    # Stock-in details
    received_at = models.DateField(default=timezone.localdate, help_text="Date laptop was received/stocked")

    order_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Cost price when purchased")

    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Selling price (can override product default)"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="IN_STOCK", db_index=True)

    # Archive support
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="archived_laptop_serials"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Manager
    objects = TenantManager()

    class Meta:
        verbose_name = "Laptop Serial"
        verbose_name_plural = "Laptop Serials"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "serial", "is_active"], name="laptop_serial_biz_code"),
            models.Index(fields=["business", "status", "is_active"], name="laptop_serial_status"),
            models.Index(fields=["product", "status"], name="laptop_serial_product"),
        ]
        constraints = [
            # Serial must be unique per business (when not archived)
            models.UniqueConstraint(
                fields=["business", "serial"],
                condition=models.Q(is_active=True),
                name="unique_laptop_serial_per_business",
            )
        ]

    def __str__(self):
        return f"{self.product} - Serial: {self.serial}"

    def archive(self, user=None):
        """Archive this laptop serial"""
        from django.utils import timezone

        self.is_active = False
        self.archived_at = timezone.now()
        if user:
            self.archived_by = user
        self.save(update_fields=["is_active", "archived_at", "archived_by"])
