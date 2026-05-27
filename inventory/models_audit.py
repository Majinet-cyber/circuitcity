# inventory/models_audit.py
"""
Stock audit trail and activity logging for HQ visibility.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class StockAction(models.TextChoices):
    """Actions that can be performed on stock."""

    CREATE = "CREATE", "Created"
    UPDATE = "UPDATE", "Updated"
    ADJUST_QUANTITY = "ADJUST_QUANTITY", "Quantity Adjusted"
    SOFT_DELETE = "SOFT_DELETE", "Soft Deleted"
    DELETE_ATTEMPT = "DELETE_ATTEMPT", "Delete Attempted (Blocked)"
    IMPORT = "IMPORT", "Bulk Import"
    RESTORE = "RESTORE", "Restored"


class StockActivityLog(models.Model):
    """
    Comprehensive audit log for all stock-related activities.

    Tracks who did what, when, and on which stock item.
    Critical for HQ visibility and preventing fraud/disputes.
    """

    # Core identifiers
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="stock_activity_logs",
        help_text="Business this stock belongs to",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_activity_logs",
        help_text="Location (if applicable)",
    )

    # Stock item reference (flexible to work with different models)
    product_model = models.CharField(max_length=100, help_text="Model name (e.g., 'InventoryItem', 'MerchProduct')")
    product_id = models.IntegerField(help_text="ID of the product/stock item")
    product_name = models.CharField(max_length=255, blank=True, help_text="Product name (for quick reference)")

    # For phones: track IMEI
    imei = models.CharField(max_length=20, blank=True, db_index=True, help_text="IMEI (for phones)")

    # What happened
    action = models.CharField(max_length=32, choices=StockAction.choices, db_index=True, help_text="Action performed")

    # Who did it
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_activities",
        help_text="User who performed the action (null if system)",
    )

    # Quantity tracking (for auditing changes)
    old_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Quantity before change"
    )
    new_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Quantity after change"
    )

    # Additional context
    note = models.TextField(blank=True, help_text="Optional note or reason for action")

    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="IP address of request (if available)")
    user_agent = models.CharField(max_length=255, blank=True, help_text="User agent string")

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="When this action occurred")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["location", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["performed_by", "-created_at"]),
            models.Index(fields=["product_model", "product_id"]),
            models.Index(fields=["imei"]),
        ]
        verbose_name = "Stock Activity Log"
        verbose_name_plural = "Stock Activity Logs"

    def __str__(self):
        user_str = self.performed_by.username if self.performed_by else "System"
        return f"{self.action} by {user_str} on {self.product_name or f'#{self.product_id}'}"

    @classmethod
    def log_activity(cls, business, action: str, product_model: str, product_id: int, performed_by=None, **kwargs):
        """
        Convenience method to create an activity log entry.

        Usage:
            StockActivityLog.log_activity(
                business=business,
                action=StockAction.CREATE,
                product_model="InventoryItem",
                product_id=item.id,
                performed_by=request.user,
                product_name=item.product.name,
                imei=item.imei,
                note="Added via bulk import",
            )
        """
        return cls.objects.create(
            business=business,
            action=action,
            product_model=product_model,
            product_id=product_id,
            performed_by=performed_by,
            **kwargs,
        )
