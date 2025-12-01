# inventory/models_approval.py
"""
Manager-approved edit requests for phone stock (InventoryItem).
Agents must get approval for stock edits; managers can edit directly.
"""
from __future__ import annotations

from typing import Optional
from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business


class PhoneStockEditRequest(models.Model):
    """
    Pending stock edit request from an agent that requires manager approval.
    When approved, the changes are applied to the actual InventoryItem.
    """
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="stock_edit_requests",
        db_index=True,
        help_text="Business this edit request belongs to"
    )
    
    stock = models.ForeignKey(
        "InventoryItem",
        on_delete=models.CASCADE,
        related_name="edit_requests",
        help_text="The stock item to be edited"
    )
    
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stock_edit_requests",
        help_text="Agent who requested the edit"
    )
    
    payload = models.JSONField(
        help_text="Proposed changes as a dict of field: new_value"
    )
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )
    
    # Review tracking
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_stock_edits",
        help_text="Manager who approved/rejected this request"
    )
    
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the request was approved/rejected"
    )
    
    reason = models.TextField(
        blank=True,
        help_text="Optional reason for rejection or notes"
    )
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["requested_by", "status"]),
            models.Index(fields=["stock", "status"]),
        ]
    
    def __str__(self):
        return f"Edit request #{self.pk} for {self.stock} by {self.requested_by.username} ({self.status})"
    
    def approve(self, manager_user, reason: str = "") -> None:
        """
        Apply the proposed changes to the stock item and mark as approved.
        """
        if self.status != "PENDING":
            raise ValueError("Can only approve pending requests")
        
        # Apply changes to the stock item
        for field, value in self.payload.items():
            if hasattr(self.stock, field):
                setattr(self.stock, field, value)
        
        self.stock.save()
        
        # Mark as approved
        self.status = "APPROVED"
        self.reviewed_by = manager_user
        self.reviewed_at = timezone.now()
        self.reason = reason
        self.save()
    
    def reject(self, manager_user, reason: str = "") -> None:
        """
        Reject the edit request with an optional reason.
        """
        if self.status != "PENDING":
            raise ValueError("Can only reject pending requests")
        
        self.status = "REJECTED"
        self.reviewed_by = manager_user
        self.reviewed_at = timezone.now()
        self.reason = reason
        self.save()
    
    def get_changes_display(self) -> list[dict]:
        """
        Return a human-readable list of proposed changes.
        """
        changes = []
        for field, new_value in self.payload.items():
            old_value = getattr(self.stock, field, None)
            changes.append({
                "field": field,
                "field_display": field.replace("_", " ").title(),
                "old_value": str(old_value) if old_value is not None else "(none)",
                "new_value": str(new_value) if new_value is not None else "(none)",
            })
        return changes

