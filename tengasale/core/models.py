from decimal import Decimal

from django.conf import settings
from django.db import models


class BusinessSetting(models.Model):
    merchant_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
    )
    manager_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.00"),
    )
    loan_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.50"),
    )
    spin_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business setting"
        verbose_name_plural = "Business settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "TengaSale business settings"


class QueueRule(models.Model):
    """Per-country queue configuration for the sales/underwriter claim system."""

    country = models.CharField(max_length=10, default="MW", unique=True)
    cooldown_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Minutes a rep must wait between claiming applications.",
    )
    max_active_applications = models.PositiveIntegerField(
        default=5,
        help_text="Maximum applications a rep can have active at once.",
    )
    polling_interval_seconds = models.PositiveIntegerField(
        default=30,
        help_text="How often the home page polls for queue status (seconds).",
    )
    inactive_pause_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes of inactivity before polling pauses.",
    )
    waiting_edit_grace_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutes an application can wait for customer edits before it stops counting toward the rep's active limit.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Queue rule"
        verbose_name_plural = "Queue rules"

    def save(self, *args, **kwargs):
        self.country = self.country.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Queue rules ({self.country})"

    @classmethod
    def for_country(cls, country="MW"):
        rule, _ = cls.objects.get_or_create(country=country.upper())
        return rule


class AuditLog(models.Model):
    """Immutable audit trail for sensitive actions."""

    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"
    ACTION_PAYMENT = "payment"
    ACTION_PAYMENT_STATUS = "payment_status_change"
    ACTION_DEVICE_LOCK = "device_lock"
    ACTION_DEVICE_UNLOCK = "device_unlock"
    ACTION_DEVICE_ENROLL = "device_enroll"
    ACTION_KYC_CHANGE = "kyc_change"
    ACTION_CONTRACT_CREATE = "contract_create"
    ACTION_CLAIM = "claim_application"
    ACTION_PAYOUT = "payout_request"
    ACTION_WEBHOOK = "webhook_received"

    ACTION_CHOICES = [
        (ACTION_APPROVE, "Application Approved"),
        (ACTION_REJECT, "Application Rejected"),
        (ACTION_PAYMENT, "Payment Applied"),
        (ACTION_PAYMENT_STATUS, "Payment Status Changed"),
        (ACTION_DEVICE_LOCK, "Device Locked"),
        (ACTION_DEVICE_UNLOCK, "Device Unlocked"),
        (ACTION_DEVICE_ENROLL, "Device Enrolled"),
        (ACTION_KYC_CHANGE, "KYC Document Changed"),
        (ACTION_CONTRACT_CREATE, "Contract Created"),
        (ACTION_CLAIM, "Application Claimed"),
        (ACTION_PAYOUT, "Payout Requested"),
        (ACTION_WEBHOOK, "Webhook Received"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.user_id} at {self.timestamp}"
