# inventory/models_stock_barcodes.py
"""
Stock-level barcode tracking for clothing, shoes, and other barcode-tracked products.

This model stores individual barcode instances for stock items, allowing:
- Multiple barcodes per product (when quantity > 1)
- Unique barcode validation per business
- Archive support for barcode records
- Linkage to stock items or products
"""
from __future__ import annotations

from django.db import models
from django.core.validators import MinLengthValidator
from django.utils import timezone

from tenants.models import Business, TenantManager


class InventoryBarcode(models.Model):
    """
    Individual barcode instance for stock items.
    
    Each barcode is unique per business. When quantity=N, exactly N barcode rows should exist.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="inventory_barcodes",
        db_index=True,
        help_text="Business this barcode belongs to"
    )
    
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="barcodes",
        help_text="Location where this barcode is stored (optional)"
    )
    
    # Link to product or stock item
    product = models.ForeignKey(
        "inventory.MerchProduct",
        on_delete=models.CASCADE,
        related_name="stock_barcodes",
        null=True,
        blank=True,
        help_text="Product this barcode belongs to"
    )
    
    # Barcode code (unique per business)
    code = models.CharField(
        max_length=100,
        db_index=True,
        validators=[MinLengthValidator(3)],
        help_text="Barcode value (EAN, UPC, QR, etc.)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_stock_barcodes"
    )
    
    # Archive support
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Set to True to archive this barcode without deleting"
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this barcode was archived"
    )
    archived_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_stock_barcodes"
    )
    
    # Manager
    objects = TenantManager()
    
    class Meta:
        verbose_name = "Inventory Barcode"
        verbose_name_plural = "Inventory Barcodes"
        ordering = ["-created_at"]
        indexes = [
            # Fast lookups by business + code (using unique names to avoid conflicts with BarcodeRegistry)
            models.Index(fields=["business", "code", "is_archived"], name="invbarcode_biz_code_active"),
            # Product lookups
            models.Index(fields=["product", "is_archived"], name="invbarcode_product_active"),
            # Location lookups
            models.Index(fields=["location", "is_archived"], name="invbarcode_location_active"),
        ]
        constraints = [
            # Each barcode must be unique per business (when not archived)
            models.UniqueConstraint(
                fields=["business", "code"],
                condition=models.Q(is_archived=False),
                name="unique_invbarcode_per_business"
            )
        ]
    
    def __str__(self):
        return f"{self.code} ({self.business.name if self.business else 'N/A'})"
    
    def archive(self, user=None):
        """Archive this barcode"""
        self.is_archived = True
        self.archived_at = timezone.now()
        if user:
            self.archived_by = user
        self.save(update_fields=['is_archived', 'archived_at', 'archived_by'])


class ArchiveBatch(models.Model):
    """
    Tracks archive operations for stock, products, and barcodes.
    
    Used for the premium 4-step archive flow to maintain audit trail.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="archive_batches",
        db_index=True
    )
    
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archive_batches",
        help_text="Location archived (null if entire business)"
    )
    
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_archive_batches"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    reason = models.TextField(
        blank=True,
        help_text="Optional reason for archiving"
    )
    
    # Snapshot of counts at time of archive
    counts_snapshot = models.JSONField(
        default=dict,
        help_text="JSON snapshot of affected records: products, stock_items, barcodes, etc."
    )
    
    class Meta:
        verbose_name = "Archive Batch"
        verbose_name_plural = "Archive Batches"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"], name="archive_batch_biz_date"),
        ]
    
    def __str__(self):
        scope = self.location.name if self.location else "Entire Business"
        return f"Archive Batch {self.id} - {scope} ({self.created_at})"

