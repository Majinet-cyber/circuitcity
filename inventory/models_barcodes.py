# inventory/models_barcodes.py
"""
Barcode Registry - Robust barcode → product mapping for multi-tenant system.

This model stores the relationship between barcodes and products, supporting:
- Multiple barcodes per product (raw + normalized)
- Fast lookups with database indexes
- Multi-tenant isolation (business-scoped)
- Barcode normalization for consistent matching
"""
from __future__ import annotations

from django.db import models
from django.core.validators import MinLengthValidator, MaxLengthValidator
from django.utils import timezone

from tenants.models import Business, TenantManager


class BarcodeRegistry(models.Model):
    """
    Maps barcodes to products in a multi-tenant system.
    
    Each barcode is unique per business. Multiple barcodes can map to the same product.
    Both raw (as-scanned) and normalized (cleaned) versions are stored for matching.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="barcode_registry",
        db_index=True,
        help_text="Business this barcode belongs to"
    )
    
    # Raw barcode (exactly as scanned)
    raw_code = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Original barcode exactly as scanned"
    )
    
    # Normalized barcode (cleaned for matching)
    normalized_code = models.CharField(
        max_length=100,
        db_index=True,
        validators=[MinLengthValidator(3)],
        help_text="Normalized barcode: uppercase, no spaces/hyphens, alphanumeric only"
    )
    
    # Product reference (MerchProduct for clothing/pharmacy)
    product = models.ForeignKey(
        "inventory.MerchProduct",
        on_delete=models.CASCADE,
        related_name="barcodes",
        null=True,
        blank=True,
        help_text="Product this barcode maps to"
    )
    
    # Optional: Pharmacy batch reference (for batch-level barcodes)
    batch = models.ForeignKey(
        "inventory.PharmacyBatch",
        on_delete=models.CASCADE,
        related_name="barcodes",
        null=True,
        blank=True,
        help_text="Pharmacy batch this barcode maps to (if batch-level tracking)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_barcodes"
    )
    
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Set to False to disable barcode without deleting"
    )
    
    # Manager
    objects = TenantManager()
    
    class Meta:
        verbose_name = "Barcode Registry Entry"
        verbose_name_plural = "Barcode Registry"
        ordering = ["-created_at"]
        indexes = [
            # Fast lookups by business + normalized code
            models.Index(fields=["business", "normalized_code", "is_active"], name="barcode_biz_norm_active"),
            # Fast lookups by business + raw code
            models.Index(fields=["business", "raw_code", "is_active"], name="barcode_biz_raw_active"),
            # Product lookups
            models.Index(fields=["product", "is_active"], name="barcode_product_active"),
            # Batch lookups (pharmacy)
            models.Index(fields=["batch", "is_active"], name="barcode_batch_active"),
        ]
        constraints = [
            # Each normalized barcode must be unique per business
            models.UniqueConstraint(
                fields=["business", "normalized_code"],
                condition=models.Q(is_active=True),
                name="unique_barcode_per_business"
            )
        ]
    
    def __str__(self):
        target = self.batch or self.product
        target_name = getattr(target, 'name', 'Unknown') if target else 'Unlinked'
        return f"{self.raw_code} → {target_name}"
    
    def save(self, *args, **kwargs):
        """Auto-normalize on save"""
        from inventory.utils_barcodes import normalize_barcode_enhanced
        self.normalized_code = normalize_barcode_enhanced(self.raw_code)
        super().save(*args, **kwargs)


# Re-export for convenient imports
__all__ = ["BarcodeRegistry"]

