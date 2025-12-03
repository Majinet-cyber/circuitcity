# inventory/models_phone_products.py
"""
Phone Product Catalog - Curated, editable phone SKU definitions for PHONES businesses.

Similar to Liquor's product catalog, this allows businesses to maintain a curated
list of phone models with brand, model name, RAM/ROM variants, and default pricing.

Each business gets their own copy of the catalog (business-scoped), seeded with
flagship models from TECNO, ITEL, and SAMSUNG.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


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
        help_text="Business this product belongs to"
    )
    
    # Brand and model info
    brand = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Phone brand (e.g., TECNO, ITEL, SAMSUNG)"
    )
    model_name = models.CharField(
        max_length=100,
        help_text="Model name (e.g., Spark 40, Pop 10, A15)"
    )
    
    # RAM/ROM variant
    ram_gb = models.PositiveIntegerField(
        help_text="RAM in GB (e.g., 4, 8)"
    )
    rom_gb = models.PositiveIntegerField(
        help_text="ROM/Storage in GB (e.g., 128, 256)"
    )
    variant_label = models.CharField(
        max_length=20,
        blank=True,
        help_text="Display label for variant (e.g., '4+128', '8+256')"
    )
    
    # Optional internal model number (editable by merchant)
    model_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Internal model/SKU number (optional, editable)"
    )
    
    # Default pricing (optional, can be overridden at sale time)
    default_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default cost price (optional)"
    )
    default_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default selling price (optional)"
    )
    
    # Metadata
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this product is active in the catalog"
    )
    is_flagship = models.BooleanField(
        default=False,
        help_text="Mark as flagship/featured product"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="phone_products_created"
    )
    
    class Meta:
        ordering = ["brand", "model_name", "ram_gb", "rom_gb"]
        indexes = [
            models.Index(fields=["business", "brand"], name="phoneprod_biz_brand_idx"),
            models.Index(fields=["business", "is_active"], name="phoneprod_biz_active_idx"),
            models.Index(fields=["brand", "model_name"], name="phoneprod_brand_model_idx"),
        ]
        unique_together = [("business", "brand", "model_name", "ram_gb", "rom_gb")]
    
    def __str__(self):
        variant = self.variant_label or f"{self.ram_gb}+{self.rom_gb}"
        return f"{self.brand} {self.model_name} ({variant})"
    
    def save(self, *args, **kwargs):
        # Auto-generate variant_label if not provided
        if not self.variant_label:
            self.variant_label = f"{self.ram_gb}+{self.rom_gb}"
        super().save(*args, **kwargs)
    
    @property
    def display_name(self):
        """Full display name for UI"""
        variant = self.variant_label or f"{self.ram_gb}+{self.rom_gb}"
        return f"{self.brand} {self.model_name} ({variant})"
    
    @property
    def has_pricing(self):
        """Check if default pricing is set"""
        return self.default_cost_price is not None and self.default_selling_price is not None

