# inventory/models_data_correction.py
"""
Data Correction models for auditing and tracking all corrections made to
sales, stock-in records, and inventory items.

This is a CRITICAL feature for the Phones vertical (and eventually other verticals)
that allows managers to fix wrong data safely with full audit trail.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business


class CorrectionType(models.TextChoices):
    """Types of corrections that can be made across all verticals."""
    
    # Phones vertical
    EDIT_SALE = "EDIT_SALE", "Edit Sale"
    EDIT_STOCK_IN = "EDIT_STOCK_IN", "Edit Stock-In"
    EDIT_ACCESSORY = "EDIT_ACCESSORY", "Edit Accessory"
    VOID_SALE = "VOID_SALE", "Void Sale"
    VOID_STOCK_IN = "VOID_STOCK_IN", "Void Stock-In"
    VOID_ACCESSORY = "VOID_ACCESSORY", "Void Accessory"
    RESTORE = "RESTORE", "Restore Voided Record"
    
    # Liquor vertical
    EDIT_LIQUOR_SALE = "EDIT_LIQUOR_SALE", "Edit Liquor Sale"
    VOID_LIQUOR_SALE = "VOID_LIQUOR_SALE", "Void Liquor Sale"
    EDIT_LIQUOR_STOCK = "EDIT_LIQUOR_STOCK", "Edit Liquor Stock"
    VOID_LIQUOR_STOCK = "VOID_LIQUOR_STOCK", "Void Liquor Stock"
    
    # Welding vertical
    EDIT_WELDING_QUOTE = "EDIT_WELDING_QUOTE", "Edit Welding Quote"
    VOID_WELDING_QUOTE = "VOID_WELDING_QUOTE", "Void Welding Quote"
    EDIT_WELDING_JOB = "EDIT_WELDING_JOB", "Edit Welding Job"
    VOID_WELDING_JOB = "VOID_WELDING_JOB", "Void Welding Job"
    EDIT_WELDING_INVOICE = "EDIT_WELDING_INVOICE", "Edit Welding Invoice"
    
    # Farm vertical
    EDIT_FARM_ENTRY = "EDIT_FARM_ENTRY", "Edit Farm Entry"
    VOID_FARM_ENTRY = "VOID_FARM_ENTRY", "Void Farm Entry"
    EDIT_POULTRY_RECORD = "EDIT_POULTRY_RECORD", "Edit Poultry Record"
    EDIT_PIG_RECORD = "EDIT_PIG_RECORD", "Edit Pig Record"
    
    # Car Hire vertical
    EDIT_CAR_HIRE_TRIP = "EDIT_CAR_HIRE_TRIP", "Edit Trip/Booking"
    VOID_CAR_HIRE_TRIP = "VOID_CAR_HIRE_TRIP", "Void Trip/Booking"
    EDIT_VEHICLE = "EDIT_VEHICLE", "Edit Vehicle"
    
    # Generic
    EDIT_EXPENSE = "EDIT_EXPENSE", "Edit Expense"
    VOID_EXPENSE = "VOID_EXPENSE", "Void Expense"
    EDIT_COST = "EDIT_COST", "Edit Cost"
    VOID_COST = "VOID_COST", "Void Cost"


class DataCorrectionLog(models.Model):
    """
    Comprehensive audit log for all data corrections.
    
    Every edit or void action requires:
    - Reason for correction (required)
    - Old values → New values (JSON)
    - User who made the change
    - Timestamp
    
    This is the SINGLE SOURCE OF TRUTH for accountability.
    """
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="data_correction_logs",
        db_index=True,
        help_text="Business where correction was made",
    )
    
    # What was corrected
    model_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Model name (e.g., 'InventoryItem', 'AccessoryStock', 'LiquorSale')",
    )
    object_id = models.PositiveIntegerField(
        db_index=True,
        help_text="ID of the corrected object",
    )
    
    # Type of correction
    correction_type = models.CharField(
        max_length=32,
        choices=CorrectionType.choices,
        db_index=True,
        help_text="Type of correction made",
    )
    
    # Who made the correction (required, must be manager)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # Never delete corrections
        related_name="data_corrections",
        help_text="Manager who made the correction",
    )
    
    # When
    corrected_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the correction was made",
    )
    
    # REQUIRED: Reason for correction
    reason = models.TextField(
        help_text="Required: Reason for making this correction",
    )
    
    # Field changes (JSON): {"field_name": {"old": value, "new": value}, ...}
    field_changes = models.JSONField(
        default=dict,
        help_text="JSON dict of field changes: {field: {old: val, new: val}}",
    )
    
    # Computed impact (for dashboard display)
    revenue_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Change in revenue caused by this correction",
    )
    profit_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Change in profit caused by this correction",
    )
    
    # Optional metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request",
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="User agent string",
    )
    
    # For voided records: track if it was later restored
    is_restoration = models.BooleanField(
        default=False,
        help_text="True if this log entry is a restoration of a voided record",
    )
    
    class Meta:
        ordering = ["-corrected_at"]
        indexes = [
            models.Index(fields=["business", "-corrected_at"]),
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["corrected_by", "-corrected_at"]),
            models.Index(fields=["correction_type", "-corrected_at"]),
        ]
        verbose_name = "Data Correction Log"
        verbose_name_plural = "Data Correction Logs"
    
    def __str__(self):
        return f"{self.get_correction_type_display()} by {self.corrected_by} on {self.model_name}#{self.object_id}"
    
    @property
    def changes_summary(self) -> str:
        """Return a human-readable summary of changes."""
        if not self.field_changes:
            return "No field changes recorded"
        
        parts = []
        for field, change in self.field_changes.items():
            old_val = change.get("old", "N/A")
            new_val = change.get("new", "N/A")
            parts.append(f"{field}: {old_val} → {new_val}")
        
        return "; ".join(parts)
    
    @classmethod
    def log_correction(
        cls,
        business,
        model_name: str,
        object_id: int,
        correction_type: str,
        corrected_by,
        reason: str,
        field_changes: Dict[str, Dict[str, Any]],
        revenue_impact: Decimal = Decimal("0.00"),
        profit_impact: Decimal = Decimal("0.00"),
        request=None,
    ) -> "DataCorrectionLog":
        """
        Convenience method to create a correction log entry.
        
        Args:
            business: Business instance
            model_name: Name of the model being corrected
            object_id: ID of the object being corrected
            correction_type: One of CorrectionType choices
            corrected_by: User who made the correction
            reason: Required reason for the correction
            field_changes: Dict of {field: {old: val, new: val}}
            revenue_impact: Change in revenue (can be negative)
            profit_impact: Change in profit (can be negative)
            request: Optional HTTP request for IP/UA extraction
        """
        ip_address = None
        user_agent = ""
        
        if request:
            # Extract IP address
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")
            
            # Extract user agent
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
        
        return cls.objects.create(
            business=business,
            model_name=model_name,
            object_id=object_id,
            correction_type=correction_type,
            corrected_by=corrected_by,
            reason=reason,
            field_changes=field_changes,
            revenue_impact=revenue_impact,
            profit_impact=profit_impact,
            ip_address=ip_address,
            user_agent=user_agent,
        )


class VoidedRecord(models.Model):
    """
    Tracks records that have been voided (soft-deleted) for audit purposes.
    
    Rather than hard-deleting, we mark records as voided and store
    their snapshot here for historical reference and potential restoration.
    """
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="voided_records",
        db_index=True,
    )
    
    # What was voided
    model_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Model name of the voided record",
    )
    object_id = models.PositiveIntegerField(
        db_index=True,
        help_text="ID of the voided object",
    )
    
    # Snapshot of the record at time of voiding
    record_snapshot = models.JSONField(
        default=dict,
        help_text="JSON snapshot of the record before voiding",
    )
    
    # Who and when
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="voided_records",
        help_text="Manager who voided the record",
    )
    voided_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )
    
    # Required reason
    reason = models.TextField(
        help_text="Required: Reason for voiding",
    )
    
    # Financial impact (for reporting)
    revenue_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Revenue removed from totals by this void",
    )
    profit_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Profit removed from totals by this void",
    )
    
    # Restoration tracking
    is_restored = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this record was later restored",
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restored_records",
    )
    restored_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    class Meta:
        ordering = ["-voided_at"]
        indexes = [
            models.Index(fields=["business", "-voided_at"]),
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["is_restored", "-voided_at"]),
        ]
        # Prevent duplicate void entries for the same object
        constraints = [
            models.UniqueConstraint(
                fields=["model_name", "object_id"],
                condition=models.Q(is_restored=False),
                name="unique_active_void_per_object",
            ),
        ]
        verbose_name = "Voided Record"
        verbose_name_plural = "Voided Records"
    
    def __str__(self):
        status = "restored" if self.is_restored else "voided"
        return f"{self.model_name}#{self.object_id} ({status})"
    
    @classmethod
    def void_record(
        cls,
        business,
        model_name: str,
        obj,
        voided_by,
        reason: str,
        revenue_impact: Decimal = Decimal("0.00"),
        profit_impact: Decimal = Decimal("0.00"),
    ) -> "VoidedRecord":
        """
        Create a void entry for a record.
        
        Args:
            business: Business instance
            model_name: Name of the model
            obj: The object being voided (used to create snapshot)
            voided_by: User who voided the record
            reason: Required reason
            revenue_impact: Revenue being removed
            profit_impact: Profit being removed
        """
        # Create snapshot of the object
        snapshot = {}
        for field in obj._meta.fields:
            value = getattr(obj, field.name)
            # Convert non-serializable types
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, Decimal):
                value = str(value)
            elif hasattr(value, "pk"):
                value = value.pk
            snapshot[field.name] = value
        
        return cls.objects.create(
            business=business,
            model_name=model_name,
            object_id=obj.pk,
            record_snapshot=snapshot,
            voided_by=voided_by,
            reason=reason,
            revenue_impact=revenue_impact,
            profit_impact=profit_impact,
        )


# Export models
__all__ = [
    "CorrectionType",
    "DataCorrectionLog",
    "VoidedRecord",
]

