# integrations/models.py
"""
Integration foundation for Emajinet:
- DeveloperIntegration  — registered external integrations per business
- WebhookEvent          — audit log for every inbound webhook payload
- CreditSignal          — credit-intelligence events for future scoring
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class IntegrationType(models.TextChoices):
    IOT = "iot", "IoT Monitoring"
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    CREDIT = "credit", "Credit / Lending"
    POS = "pos", "Point of Sale"
    ACCOUNTING = "accounting", "Accounting"
    CUSTOM = "custom", "Custom"


class WebhookStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class CreditSignalType(models.TextChoices):
    REPAYMENT = "repayment", "Repayment"
    MISSED_PAYMENT = "missed_payment", "Missed Payment"
    PARTIAL_PAYMENT = "partial_payment", "Partial Payment"
    STOCK_TURNOVER = "stock_turnover", "Stock Turnover"
    SALES_VELOCITY = "sales_velocity", "Sales Velocity"
    MOBILE_MONEY_ACTIVITY = "mobile_money_activity", "Mobile Money Activity"
    ASSET_USAGE = "asset_usage", "Asset Usage"
    MANUAL_ADJUSTMENT = "manual_adjustment", "Manual Adjustment"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# DeveloperIntegration
# ---------------------------------------------------------------------------

class DeveloperIntegration(models.Model):
    """A registered integration for a business (or global for HQ-level integrations)."""

    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="developer_integrations",
    )
    name = models.CharField(max_length=200)
    integration_type = models.CharField(
        max_length=30, choices=IntegrationType.choices, default=IntegrationType.CUSTOM
    )
    # Store a hash or opaque reference — never the raw token
    api_key_hint = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Last 8 chars of token for UI display only — never the full key",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Developer Integration"
        verbose_name_plural = "Developer Integrations"

    def __str__(self) -> str:
        biz = self.business.name if self.business_id else "Global"
        return f"{self.name} ({self.get_integration_type_display()}) — {biz}"


# ---------------------------------------------------------------------------
# WebhookEvent
# ---------------------------------------------------------------------------

class WebhookEvent(models.Model):
    """Immutable audit record for every inbound webhook payload."""

    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
    )
    integration = models.ForeignKey(
        DeveloperIntegration,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    source = models.CharField(max_length=200, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True, default="generic")
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=WebhookStatus.choices, default=WebhookStatus.RECEIVED, db_index=True
    )
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Webhook Event"
        verbose_name_plural = "Webhook Events"
        indexes = [
            models.Index(fields=["source", "-received_at"]),
            models.Index(fields=["event_type", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.status}] {self.source} / {self.event_type} @ {self.received_at:%Y-%m-%d %H:%M}"

    def mark_processed(self) -> None:
        self.status = WebhookStatus.PROCESSED
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at"])

    def mark_failed(self, reason: str) -> None:
        self.status = WebhookStatus.FAILED
        self.error_message = reason[:2000]
        self.save(update_fields=["status", "error_message"])


# ---------------------------------------------------------------------------
# CreditSignal
# ---------------------------------------------------------------------------

class CreditSignal(models.Model):
    """
    A single credit-intelligence event. Used to build future credit profiles.

    No FK to a Customer model (none exists) — uses customer_ref CharField.
    """

    business = models.ForeignKey(
        "tenants.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_signals",
    )
    customer_ref = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
        help_text="External customer identifier (e.g. CUST-001, phone number)",
    )
    source = models.CharField(max_length=200, db_index=True)
    signal_type = models.CharField(
        max_length=40, choices=CreditSignalType.choices, default=CreditSignalType.OTHER, db_index=True
    )
    score_impact = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional numeric impact on credit score (positive = good, negative = bad)",
    )
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "Credit Signal"
        verbose_name_plural = "Credit Signals"
        indexes = [
            models.Index(fields=["customer_ref", "-occurred_at"]),
            models.Index(fields=["signal_type", "-occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_signal_type_display()} / {self.customer_ref or 'anon'} @ {self.occurred_at:%Y-%m-%d}"
