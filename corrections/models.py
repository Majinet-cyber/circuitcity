"""
Corrections Framework Models (Feb 2026)
========================================

Generic, vertical-aware data correction models.

Architecture:
- CorrectionBatch: Groups multiple corrections into a single logical unit
- CorrectionItem: Individual field correction (old_value → new_value)
- CorrectionAuditLog: WHO did WHAT, WHEN, and WHY

Design Goals:
- Vertical-agnostic (works for Phones, Clothing, Gym, Liquor, etc.)
- Preview before apply (see impact without committing)
- Rollback support (restore old values if correction was wrong)
- Full audit trail (every action is logged)
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from tenants.models import Business


class CorrectionStatus(models.TextChoices):
    """Status of a correction batch."""
    
    DRAFT = 'DRAFT', 'Draft'
    PREVIEW = 'PREVIEW', 'Previewed'
    APPLIED = 'APPLIED', 'Applied'
    ROLLED_BACK = 'ROLLED_BACK', 'Rolled Back'
    FAILED = 'FAILED', 'Failed'


class CorrectionBatch(models.Model):
    """
    A batch of data corrections.
    
    Workflow:
    1. Manager creates batch (status=DRAFT)
    2. Manager adds correction items to batch
    3. Manager previews impact (status=PREVIEW)
    4. Manager applies all corrections in batch (status=APPLIED)
    5. (Optional) Manager rolls back batch if corrections were wrong (status=ROLLED_BACK)
    """
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='correction_batches',
        db_index=True,
        help_text='Business where corrections are being made',
    )
    
    vertical = models.CharField(
        max_length=32,
        db_index=True,
        help_text='Vertical slug (phones, clothing, gym, liquor, etc.)',
    )
    
    status = models.CharField(
        max_length=20,
        choices=CorrectionStatus.choices,
        default=CorrectionStatus.DRAFT,
        db_index=True,
    )
    
    # Who and when
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_correction_batches',
        help_text='Manager who created this batch',
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )
    
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='applied_correction_batches',
        help_text='Manager who applied this batch',
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )
    
    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='rolled_back_correction_batches',
    )
    rolled_back_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    # Reason and notes
    reason = models.TextField(
        help_text='Required: Why are these corrections needed?',
    )
    notes = models.TextField(
        blank=True,
        default='',
        help_text='Optional notes about this batch',
    )
    
    # Computed metrics (updated when batch is applied)
    items_count = models.PositiveIntegerField(
        default=0,
        help_text='Total number of correction items in this batch',
    )
    items_applied = models.PositiveIntegerField(
        default=0,
        help_text='Number of items successfully applied',
    )
    items_failed = models.PositiveIntegerField(
        default=0,
        help_text='Number of items that failed to apply',
    )
    
    # Financial impact (sum of all items)
    revenue_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total revenue impact of this batch',
    )
    profit_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total profit impact of this batch',
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'vertical', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
        ]
        verbose_name = 'Correction Batch'
        verbose_name_plural = 'Correction Batches'
    
    def __str__(self):
        return f"Batch #{self.pk} ({self.vertical}) - {self.get_status_display()}"
    
    def can_be_applied(self) -> bool:
        """Check if this batch can be applied."""
        return self.status in (CorrectionStatus.DRAFT, CorrectionStatus.PREVIEW)
    
    def can_be_rolled_back(self) -> bool:
        """Check if this batch can be rolled back."""
        return self.status == CorrectionStatus.APPLIED
    
    def recalculate_metrics(self):
        """Recalculate batch metrics from items."""
        items = self.items.all()
        self.items_count = items.count()
        self.items_applied = items.filter(applied_at__isnull=False, error__isnull=True).count()
        self.items_failed = items.filter(error__isnull=False).count()
        self.revenue_impact = sum(
            (item.revenue_impact for item in items if item.revenue_impact),
            Decimal('0.00'),
        )
        self.profit_impact = sum(
            (item.profit_impact for item in items if item.profit_impact),
            Decimal('0.00'),
        )
        self.save(update_fields=[
            'items_count',
            'items_applied',
            'items_failed',
            'revenue_impact',
            'profit_impact',
        ])


class CorrectionItem(models.Model):
    """
    A single field correction within a batch.
    
    Example:
        - Entity: "sale" (InventoryItem)
        - Object ID: 12345
        - Field: "selling_price"
        - Old Value: "50000"
        - New Value: "55000"
    """
    
    batch = models.ForeignKey(
        CorrectionBatch,
        on_delete=models.CASCADE,
        related_name='items',
        help_text='Batch this item belongs to',
    )
    
    # What is being corrected
    entity_label = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Entity label from vertical adapter (e.g., "sale", "accessory", "member")',
    )
    model_name = models.CharField(
        max_length=100,
        help_text='Full model name (e.g., "inventory.InventoryItem")',
    )
    object_id = models.PositiveIntegerField(
        db_index=True,
        help_text='ID of the object being corrected',
    )
    
    # Field correction
    field_name = models.CharField(
        max_length=100,
        help_text='Field being corrected (e.g., "selling_price")',
    )
    old_value = models.JSONField(
        help_text='Original value (JSON-serialized)',
    )
    new_value = models.JSONField(
        help_text='New value (JSON-serialized)',
    )
    
    # Application tracking
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this correction was applied (null if not yet applied)',
    )
    error = models.TextField(
        null=True,
        blank=True,
        help_text='Error message if application failed',
    )
    
    # Impact (computed during preview)
    revenue_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue impact of this correction (null if not applicable)',
    )
    profit_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Profit impact of this correction (null if not applicable)',
    )
    
    # Rollback tracking
    rolled_back_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['batch', 'entity_label']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['applied_at']),
        ]
        verbose_name = 'Correction Item'
        verbose_name_plural = 'Correction Items'
    
    def __str__(self):
        return f"{self.entity_label} #{self.object_id} · {self.field_name}: {self.old_value} → {self.new_value}"
    
    @property
    def is_applied(self) -> bool:
        """Check if this correction has been applied."""
        return self.applied_at is not None and self.error is None
    
    @property
    def is_failed(self) -> bool:
        """Check if this correction failed to apply."""
        return self.error is not None
    
    @property
    def is_rolled_back(self) -> bool:
        """Check if this correction has been rolled back."""
        return self.rolled_back_at is not None


class CorrectionAuditLog(models.Model):
    """
    Audit trail for all correction actions.
    
    Logs every action taken on batches and items:
    - Batch created
    - Batch previewed
    - Batch applied
    - Batch rolled back
    - Item added to batch
    - Item removed from batch
    """
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='correction_audit_logs',
        db_index=True,
    )
    
    batch = models.ForeignKey(
        CorrectionBatch,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    
    item = models.ForeignKey(
        CorrectionItem,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    
    # Who and when
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='correction_audit_logs',
    )
    performed_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )
    
    # What action was performed
    action = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Action performed (e.g., "batch_created", "batch_applied", "item_applied")',
    )
    
    # Details
    details = models.JSONField(
        default=dict,
        help_text='Additional details about this action (JSON)',
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        default='',
    )
    
    class Meta:
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['business', '-performed_at']),
            models.Index(fields=['batch', '-performed_at']),
            models.Index(fields=['action', '-performed_at']),
        ]
        verbose_name = 'Correction Audit Log'
        verbose_name_plural = 'Correction Audit Logs'
    
    def __str__(self):
        return f"{self.action} by {self.performed_by} at {self.performed_at}"
    
    @classmethod
    def log_action(
        cls,
        business,
        performed_by,
        action: str,
        details: Dict[str, Any] = None,
        batch=None,
        item=None,
        request=None,
    ) -> 'CorrectionAuditLog':
        """
        Convenience method to create an audit log entry.
        """
        ip_address = None
        user_agent = ''
        
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        
        return cls.objects.create(
            business=business,
            batch=batch,
            item=item,
            performed_by=performed_by,
            action=action,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )


# Export models
__all__ = [
    'CorrectionStatus',
    'CorrectionBatch',
    'CorrectionItem',
    'CorrectionAuditLog',
]

