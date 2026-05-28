"""
Support app models.

SupportTicket  — issue/request raised by any authenticated user
TicketComment  — threaded comments on a ticket (some internal-only)
BugEvent       — system-level failure events captured by the platform
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class SupportTicket(models.Model):
    # ── categories ──────────────────────────────────────────────────────────
    CAT_PAYMENT         = "payment"
    CAT_ACCESS          = "access"
    CAT_MERCHANT_ONBOARD = "merchant_onboarding"
    CAT_UNDERWRITER     = "underwriter"
    CAT_DEVICE_LOCK     = "device_lock"
    CAT_APP_ERROR       = "app_error"
    CAT_CONTRACT        = "contract"
    CAT_PAYOUT          = "payout"
    CAT_DATA_CORRECTION = "data_correction"
    CAT_OTHER           = "other"

    CATEGORY_CHOICES = [
        (CAT_PAYMENT,          "Payment issue"),
        (CAT_ACCESS,           "Login / access issue"),
        (CAT_MERCHANT_ONBOARD, "Merchant onboarding issue"),
        (CAT_UNDERWRITER,      "Underwriter issue"),
        (CAT_DEVICE_LOCK,      "Device lock issue"),
        (CAT_APP_ERROR,        "Application error"),
        (CAT_CONTRACT,         "Contract issue"),
        (CAT_PAYOUT,           "Payout issue"),
        (CAT_DATA_CORRECTION,  "Data correction request"),
        (CAT_OTHER,            "Other"),
    ]

    # ── priorities ───────────────────────────────────────────────────────────
    PRI_LOW      = "low"
    PRI_MEDIUM   = "medium"
    PRI_HIGH     = "high"
    PRI_CRITICAL = "critical"

    PRIORITY_CHOICES = [
        (PRI_LOW,      "Low"),
        (PRI_MEDIUM,   "Medium"),
        (PRI_HIGH,     "High"),
        (PRI_CRITICAL, "Critical"),
    ]

    # ── statuses ─────────────────────────────────────────────────────────────
    STATUS_OPEN           = "open"
    STATUS_ASSIGNED       = "assigned"
    STATUS_IN_PROGRESS    = "in_progress"
    STATUS_WAITING_USER   = "waiting_user"
    STATUS_WAITING_PROV   = "waiting_provider"
    STATUS_ESCALATED      = "escalated"
    STATUS_RESOLVED       = "resolved"
    STATUS_CLOSED         = "closed"

    STATUS_CHOICES = [
        (STATUS_OPEN,         "Open"),
        (STATUS_ASSIGNED,     "Assigned"),
        (STATUS_IN_PROGRESS,  "In Progress"),
        (STATUS_WAITING_USER, "Waiting on User"),
        (STATUS_WAITING_PROV, "Waiting on Provider"),
        (STATUS_ESCALATED,    "Escalated to HQ"),
        (STATUS_RESOLVED,     "Resolved"),
        (STATUS_CLOSED,       "Closed"),
    ]

    title       = models.CharField(max_length=200)
    description = models.TextField()
    category    = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=CAT_OTHER)
    priority    = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRI_MEDIUM)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_tickets",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )

    # Optional context links
    related_merchant    = models.ForeignKey(
        "website.MerchantLead", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    related_application = models.ForeignKey(
        "applications.FinancingApplication", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    related_contract    = models.ForeignKey(
        "contracts.Contract", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    related_payment_ref = models.CharField(max_length=100, blank=True)
    related_device_imei = models.CharField(max_length=50, blank=True)

    screenshot      = models.FileField(upload_to="support/screenshots/", blank=True, null=True)
    internal_notes  = models.TextField(blank=True)
    resolution_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"

    def __str__(self):
        return f"#{self.pk} — {self.title}"

    @property
    def ticket_number(self):
        return f"TS-{self.pk:05d}"


class TicketComment(models.Model):
    ticket     = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="comments")
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    body       = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal notes are visible only to HQ, Tech Support, and Merchant Administrators.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ticket Comment"

    def __str__(self):
        return f"Comment on #{self.ticket_id} by {self.author_id}"


class BugEvent(models.Model):
    # ── sources ──────────────────────────────────────────────────────────────
    SRC_PAYMENT     = "payment"
    SRC_SMS         = "sms"
    SRC_DEVICE_LOCK = "device_lock"
    SRC_WEBHOOK     = "webhook"
    SRC_EMAIL       = "email"
    SRC_PDF         = "pdf"
    SRC_CONTRACT    = "contract"
    SRC_PAYOUT      = "payout"
    SRC_APP_ERROR   = "app_error"
    SRC_AUTH        = "auth"
    SRC_OTHER       = "other"

    SOURCE_CHOICES = [
        (SRC_PAYMENT,     "Payment failure"),
        (SRC_SMS,         "SMS / notification failure"),
        (SRC_DEVICE_LOCK, "Device lock / unlock failure"),
        (SRC_WEBHOOK,     "Webhook failure"),
        (SRC_EMAIL,       "Email failure"),
        (SRC_PDF,         "PDF generation failure"),
        (SRC_CONTRACT,    "Contract creation failure"),
        (SRC_PAYOUT,      "Payout failure"),
        (SRC_APP_ERROR,   "Application error"),
        (SRC_AUTH,        "Permission / auth error"),
        (SRC_OTHER,       "Other"),
    ]

    # ── severities ───────────────────────────────────────────────────────────
    SEV_LOW      = "low"
    SEV_MEDIUM   = "medium"
    SEV_HIGH     = "high"
    SEV_CRITICAL = "critical"

    SEVERITY_CHOICES = [
        (SEV_LOW,      "Low"),
        (SEV_MEDIUM,   "Medium"),
        (SEV_HIGH,     "High"),
        (SEV_CRITICAL, "Critical"),
    ]

    # ── statuses ─────────────────────────────────────────────────────────────
    STAT_NEW          = "new"
    STAT_INVESTIGATING = "investigating"
    STAT_FIXED        = "fixed"
    STAT_IGNORED      = "ignored"
    STAT_ESCALATED    = "escalated"

    BUG_STATUS_CHOICES = [
        (STAT_NEW,           "New"),
        (STAT_INVESTIGATING, "Investigating"),
        (STAT_FIXED,         "Fixed"),
        (STAT_IGNORED,       "Ignored"),
        (STAT_ESCALATED,     "Escalated"),
    ]

    source           = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SRC_OTHER)
    severity         = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEV_MEDIUM)
    status           = models.CharField(max_length=20, choices=BUG_STATUS_CHOICES, default=STAT_NEW)
    message          = models.TextField()
    traceback_safe_summary = models.TextField(blank=True)

    related_user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="bug_events"
    )
    related_contract    = models.CharField(max_length=50, blank=True)
    related_application = models.CharField(max_length=50, blank=True)
    related_payment     = models.CharField(max_length=100, blank=True)
    related_device      = models.CharField(max_length=50, blank=True)

    metadata         = models.JSONField(default=dict, blank=True)
    first_seen_at    = models.DateTimeField(default=timezone.now)
    last_seen_at     = models.DateTimeField(default=timezone.now)
    occurrence_count = models.PositiveIntegerField(default=1)

    resolved_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_bugs"
    )
    resolved_at      = models.DateTimeField(null=True, blank=True)
    resolution_note  = models.TextField(blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "Bug Event"
        verbose_name_plural = "Bug Events"

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.source}: {self.message[:80]}"

    @classmethod
    def record(cls, source, message, severity=SEV_MEDIUM, metadata=None, **kwargs):
        """
        Create or update a BugEvent.  Deduplicates by (source, message[:200]).
        Metadata is automatically sanitized before storage.
        """
        from .utils import sanitize_error_metadata
        safe_meta = sanitize_error_metadata(metadata or {})
        key_msg = message[:200]
        existing = cls.objects.filter(source=source, message__startswith=key_msg, status=cls.STAT_NEW).first()
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = timezone.now()
            existing.metadata = safe_meta
            existing.save(update_fields=["occurrence_count", "last_seen_at", "metadata"])
            return existing
        return cls.objects.create(
            source=source,
            message=message,
            severity=severity,
            metadata=safe_meta,
            **kwargs,
        )
