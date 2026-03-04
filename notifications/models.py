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
    
    # Notification types - ALL DEFAULT ON for opt-out model
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
        default=True,  # CHANGED from False to True
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
    All notifications DEFAULT ON for opt-out model (user can disable).
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
        help_text="Receive sale completion emails (for managers and agents)"
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
    
    # Commission emails (for agents) - CHANGED to default=True for opt-out model
    commission_emails_enabled = models.BooleanField(
        default=True,
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
        """
        Get or create default preferences for a user.
        Sets sale_emails_enabled based on role: True for managers, False for agents.
        """
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            # Determine if user is a manager/owner or agent
            from tenants.models import Membership
            is_manager = Membership.objects.filter(
                user=user,
                role__in=["MANAGER", "OWNER", "ADMIN"],
                status="ACTIVE"
            ).exists()
            
            return cls.objects.create(
                user=user,
                sale_emails_enabled=is_manager,  # Managers=True, Agents=False
            )


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


# ==============================================================================
# Email Delivery Log (Centralized Email Tracking)
# ==============================================================================

class EmailDeliveryLog(models.Model):
    """
    Centralized email delivery log for all outgoing emails.
    Provides audit trail, retry tracking, and failure visibility.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    
    EVENT_CHOICES = [
        ('SALE_OCCURRED', 'Sale Occurred'),
        ('USER_SIGNUP', 'User Signup'),
        ('OTP_REQUEST', 'OTP Request'),
        ('SUBSCRIPTION_SUCCESS', 'Subscription Success'),
        ('SUBSCRIPTION_CANCELLED', 'Subscription Cancelled'),
        ('AGENT_COMMISSION', 'Agent Commission'),
        ('DAILY_SUMMARY', 'Daily Summary'),
        ('WEEKLY_DIGEST', 'Weekly Digest'),
        ('IMPORTANT_ALERT', 'Important Alert'),
        ('NEW_SIGNUP_OWNER_ALERT', 'New Signup Owner Alert'),
        ('NEW_SUBSCRIPTION_OWNER_ALERT', 'New Subscription Owner Alert'),
        ('NEW_BUSINESS_OWNER_ALERT', 'New Business Owner Alert'),
        ('SALE_RECEIPT', 'Sale Receipt'),
        ('CUSTOM', 'Custom'),
    ]
    
    # Event metadata
    event = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        help_text="Type of email event being sent"
    )
    
    # Recipients
    to = models.EmailField(help_text="Primary recipient email")
    cc = models.TextField(blank=True, default='', help_text="CC recipients (comma-separated)")
    bcc = models.TextField(blank=True, default='', help_text="BCC recipients (comma-separated)")
    
    # Email content
    subject = models.CharField(max_length=255, help_text="Email subject line")
    template_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Template used (if applicable)"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    attempts = models.IntegerField(
        default=0,
        help_text="Number of send attempts"
    )
    last_error = models.TextField(
        blank=True,
        default='',
        help_text="Last error message if failed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When email was successfully sent"
    )
    
    # Optional relations
    business = models.ForeignKey(
        'tenants.Business',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        help_text="Business this email relates to (if applicable)"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        help_text="User this email relates to (if applicable)"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (sale_id, subscription_id, etc.)"
    )
    
    class Meta:
        verbose_name = "Email Delivery Log"
        verbose_name_plural = "Email Delivery Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['event', 'created_at']),
            models.Index(fields=['to', 'created_at']),
            models.Index(fields=['business', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.event} to {self.to} - {self.status}"
    
    def mark_sent(self):
        """Mark email as successfully sent."""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'updated_at'])
    
    def mark_failed(self, error_message: str):
        """Mark email as failed with error message."""
        self.status = 'failed'
        self.last_error = error_message
        self.save(update_fields=['status', 'last_error', 'updated_at'])
    
    def increment_attempts(self):
        """Increment attempt counter."""
        self.attempts += 1
        if self.attempts > 1:
            self.status = 'retrying'
        self.save(update_fields=['attempts', 'status', 'updated_at'])


# ==============================================================================
# Daily Summary Email Recipients
# ==============================================================================

class BusinessEmailRecipient(models.Model):
    """
    One row per recipient email address for a business's daily summary.
    A business can have many recipients (managers, owners, external stakeholders).
    """
    business = models.ForeignKey(
        'tenants.Business',
        on_delete=models.CASCADE,
        related_name='daily_summary_recipients',
    )
    email = models.EmailField(
        help_text="Email address to receive the daily summary.",
    )
    name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Display name (optional, for personalisation).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Uncheck to stop sending to this address without deleting it.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Daily Summary Recipient"
        verbose_name_plural = "Daily Summary Recipients"
        unique_together = [("business", "email")]
        ordering = ["email"]

    def __str__(self) -> str:
        label = f" ({self.name})" if self.name else ""
        active = "" if self.is_active else " [inactive]"
        return f"{self.email}{label}{active} — {self.business.name}"


# ==============================================================================
# Per-Business Daily Summary Settings
# ==============================================================================

COMMON_TIMEZONES = [
    ("Africa/Blantyre", "Africa/Blantyre (UTC+2)"),
    ("Africa/Nairobi", "Africa/Nairobi (UTC+3)"),
    ("Africa/Johannesburg", "Africa/Johannesburg (UTC+2)"),
    ("Africa/Lagos", "Africa/Lagos (UTC+1)"),
    ("UTC", "UTC"),
    ("Europe/London", "Europe/London"),
    ("America/New_York", "America/New_York (EST)"),
]

SEND_HOUR_CHOICES = [(h, f"{h:02d}:00") for h in range(0, 24)]


class DailySummarySettings(models.Model):
    """
    Per-business configuration for the automated daily summary email.

    One row per business (OneToOne).  Created on demand the first time
    a manager opens the settings panel; or created by a migration/signal.
    """
    business = models.OneToOneField(
        'tenants.Business',
        on_delete=models.CASCADE,
        related_name='daily_summary_settings',
    )

    # Master on/off toggle
    is_enabled = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Enable daily summary emails for this business.",
    )

    # What hour (in the business timezone) to fire the email
    send_hour = models.PositiveSmallIntegerField(
        default=7,
        choices=SEND_HOUR_CHOICES,
        help_text="Hour of day (local timezone) to send the summary (0–23).",
    )

    # Timezone used to interpret send_hour and to label report dates
    timezone = models.CharField(
        max_length=64,
        default="Africa/Blantyre",
        choices=COMMON_TIMEZONES,
        help_text="Timezone for scheduling and date labels.",
    )

    # Idempotency: track last successful send date so we never double-send
    last_sent_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date (in the business timezone) of the last successfully dispatched summary.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Daily Summary Settings"
        verbose_name_plural = "Daily Summary Settings"

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.business.name} — daily summary ({status}, {self.send_hour:02d}:00 {self.timezone})"

    @classmethod
    def for_business(cls, business) -> "DailySummarySettings":
        """Get or create settings for a business (idempotent)."""
        obj, _ = cls.objects.get_or_create(business=business)
        return obj
