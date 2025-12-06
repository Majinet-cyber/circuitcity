# notifications/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    LEVELS = (
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    )
    AUDIENCE = (
        ("ADMIN", "Admin"),
        ("AGENT", "Agent"),
    )
    CATEGORIES = (
        ("general", "General"),
        ("payslip_reminder", "Payslip Reminder"),
        ("commission", "Commission"),
        ("stock", "Stock"),
        ("sale", "Sale"),
        ("system", "System"),
    )

    audience = models.CharField(max_length=10, choices=AUDIENCE)
    # For agent notifications, target user (nullable for admin-wide notices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    business = models.ForeignKey(
        "tenants.Business",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Business this notification belongs to (for multi-tenant support)"
    )

    message = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORIES, default="general")
    level = models.CharField(max_length=10, choices=LEVELS, default="info")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["audience", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["read_at"]),
            models.Index(fields=["business", "category", "created_at"]),
            models.Index(fields=["user", "category", "read_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        who = self.user or self.audience
        return f"[{self.audience}] {who}: {self.message[:60]}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])


# ==============================================================================
# WhatsApp Notification Preferences
# ==============================================================================

class WhatsAppPreference(models.Model):
    """
    WhatsApp notification preferences for managers and agents.
    Allows opt-in/opt-out for real-time alerts via WhatsApp.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whatsapp_preference"
    )
    
    # Contact info
    phone_number = models.CharField(
        max_length=20,
        help_text="International format (e.g. +265888123456)"
    )
    
    # Global toggle
    is_enabled = models.BooleanField(
        default=True,
        help_text="Master switch for all WhatsApp notifications"
    )
    
    # Notification types
    receive_sale_alerts = models.BooleanField(
        default=True,
        help_text="Notify on sales (for managers)"
    )
    receive_profit_milestones = models.BooleanField(
        default=True,
        help_text="Notify when profit milestones are reached (for managers)"
    )
    receive_low_stock_alerts = models.BooleanField(
        default=True,
        help_text="Notify when stock is low (for managers)"
    )
    receive_commission_alerts = models.BooleanField(
        default=False,
        help_text="Notify on commission earnings (for agents)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "WhatsApp Preference"
        verbose_name_plural = "WhatsApp Preferences"
        indexes = [
            models.Index(fields=["user", "is_enabled"]),
        ]
    
    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.user.username} WhatsApp ({status})"
    
    @classmethod
    def get_or_default(cls, user):
        """
        Get preference for user or return a default (unsaved) instance.
        """
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return cls(user=user, phone_number="", is_enabled=False)


