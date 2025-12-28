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


# ==============================================================================
# Email Notification Preferences
# ==============================================================================

class NotificationPreference(models.Model):
    """
    Email notification preferences for users.
    Auto-created on user creation via signal.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_notification_preference"
    )
    
    # Welcome emails
    welcome_emails = models.BooleanField(
        default=True,
        help_text="Receive welcome emails"
    )
    
    # Sale notifications (for managers)
    instant_sale_email = models.BooleanField(
        default=True,
        help_text="Receive instant email notifications for completed sales"
    )
    
    # Sale emails enabled (alias for instant_sale_email, for consistency)
    sale_emails_enabled = models.BooleanField(
        default=True,
        help_text="Receive sale completion emails (for managers: True, for agents: False by default)"
    )
    
    # Daily summary (for managers)
    daily_summary_email = models.BooleanField(
        default=True,
        help_text="Receive daily sales summary emails"
    )
    
    # Important alerts
    important_alerts_email = models.BooleanField(
        default=True,
        help_text="Receive important system alerts via email"
    )
    
    # High sales alerts
    high_sales_alerts = models.BooleanField(
        default=True,
        help_text="Receive alerts when sales spike for specific products"
    )
    
    # Commission emails (for agents)
    commission_emails_enabled = models.BooleanField(
        default=False,
        help_text="Receive commission emails when completing sales (for agents)"
    )
    
    # Weekly digest (for managers)
    weekly_digest_enabled = models.BooleanField(
        default=True,
        help_text="Receive weekly sales summary emails every Friday (for managers)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Email Notification Preference"
        verbose_name_plural = "Email Notification Preferences"
        indexes = [
            models.Index(fields=["user"]),
        ]
    
    def __str__(self):
        return f"Email preferences for {self.user.username}"
    
    @classmethod
    def get_or_create_default(cls, user):
        """Get or create default preferences for a user."""
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return cls.objects.create(user=user)


# ==============================================================================
# Email Notification Events (Idempotency + Audit Trail)
# ==============================================================================

class NotificationEvent(models.Model):
    """
    Email notification events for idempotency and audit trail.
    Prevents duplicate emails and tracks delivery status.
    """
    EVENT_TYPE_CHOICES = [
        ("WELCOME_MANAGER", "Welcome Manager"),
        ("WELCOME_AGENT", "Welcome Agent"),
        ("OTP_CODE", "OTP Code"),
        ("OTP_RESET", "OTP Reset"),
        ("OTP_VERIFY", "OTP Verify"),
        ("SALE_INSTANT", "Sale Instant"),
        ("SALE_BATCH", "Sale Batch"),
        ("DAILY_SUMMARY", "Daily Summary"),
        ("HIGH_SALES_ALERT", "High Sales Alert"),
        ("IMPORTANT_ALERT", "Important Alert"),
        ("AGENT_COMMISSION", "Agent Commission"),
        ("WEEKLY_DIGEST", "Weekly Digest"),
    ]
    
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped"),  # Skipped due to user preference
    ]
    
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, db_index=True)
    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="email_notification_events",
        db_index=True
    )
    recipient_email = models.EmailField(db_index=True)
    dedupe_key = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField(default=dict, help_text="Email template context data")
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True, help_text="Error message if failed")
    
    class Meta:
        verbose_name = "Email Notification Event"
        verbose_name_plural = "Email Notification Events"
        indexes = [
            models.Index(fields=["event_type", "status"]),
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["recipient_email", "created_at"]),
            models.Index(fields=["dedupe_key"]),
        ]
        # Unique constraint to prevent duplicates
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "recipient_email", "dedupe_key"],
                name="unique_email_event"
            )
        ]
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.event_type} -> {self.recipient_email} ({self.status})"
    
    def mark_sent(self):
        """Mark this event as successfully sent."""
        from django.utils import timezone
        self.status = "SENT"
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])
    
    def mark_failed(self, error_message: str):
        """Mark this event as failed with an error message."""
        self.status = "FAILED"
        self.last_error = str(error_message)[:1000]  # Limit error length
        self.save(update_fields=["status", "last_error"])

