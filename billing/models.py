# billing/models.py
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum, F
from django.utils import timezone

CURRENCY_DEFAULT = getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK")
TRIAL_DAYS_DEFAULT = getattr(settings, "BILLING_TRIAL_DAYS", 30)   # default 30-day trial
GRACE_DAYS_DEFAULT = getattr(settings, "BILLING_GRACE_DAYS", 30)   # default 30-day grace


# ======================================================================
# Plans
# ======================================================================
class SubscriptionPlan(models.Model):
    """
    Definition of a pricing plan. Tie feature limits here.
    """
    class Interval(models.TextChoices):
        MONTH = "month", "Monthly"
        YEAR = "year", "Yearly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=50, unique=True)  # e.g., starter, growth, pro
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    interval = models.CharField(max_length=10, choices=Interval.choices, default=Interval.MONTH)

    # Feature limits (set -1 for unlimited)
    max_stores = models.IntegerField(default=1)
    max_agents = models.IntegerField(default=3)
    features = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "amount", "name"]

    def __str__(self):
        interval = self.get_interval_display().lower()
        return f"{self.name} — {self.currency} {self.amount} / {interval}"


# ======================================================================
# Subscriptions
# ======================================================================
class BusinessSubscription(models.Model):
    """
    One subscription per Business (current), describing status + billing cycle.
    """
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        GRACE = "grace", "Grace"
        PAST_DUE = "past_due", "Past Due"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    class Method(models.TextChoices):
        NONE = "none", "None"
        AIRTEL = "airtel", "Airtel Money"
        STANDARD_BANK = "standard_bank", "Standard Bank"
        CARD = "card", "Card (VISA/Mastercard)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.OneToOneField("tenants.Business", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    started_at = models.DateTimeField(default=timezone.now)
    trial_end = models.DateTimeField(null=True, blank=True)

    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)

    payment_method = models.CharField(max_length=20, choices=Method.choices, default=Method.NONE)
    cancel_at_period_end = models.BooleanField(default=False)
    last_payment_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---- Convenience constructors -------------------------------------
    @classmethod
    def start_trial(cls, *, business, plan: SubscriptionPlan, days: int = TRIAL_DAYS_DEFAULT) -> "BusinessSubscription":
        """
        Seed a brand-new subscription with a configurable trial and set
        the initial next_billing_date = trial_end.
        """
        now = timezone.now()
        trial_end = now + timedelta(days=days)
        return cls.objects.create(
            business=business,
            plan=plan,
            status=cls.Status.TRIAL,
            started_at=now,
            trial_end=trial_end,
            current_period_start=now,
            current_period_end=trial_end,
            next_billing_date=trial_end,
        )

    # ---- Status helpers ------------------------------------------------
    def days_left_in_trial(self) -> int:
        if self.status != self.Status.TRIAL or not self.trial_end:
            return 0
        delta = self.trial_end.date() - timezone.localdate()
        return max(delta.days, 0)

    def _grace_anchor(self):
        """
        Anchor for grace: next_billing_date if present, else trial_end,
        else current_period_end.
        """
        return self.next_billing_date or self.trial_end or self.current_period_end

    def in_grace(self) -> bool:
        """
        True from anchor (inclusive) until anchor + GRACE_DAYS (exclusive).
        """
        anchor = self._grace_anchor()
        if not anchor:
            return False
        now = timezone.now()
        return anchor <= now < (anchor + timedelta(days=GRACE_DAYS_DEFAULT))

    def is_expired(self) -> bool:
        """
        True when now >= anchor + GRACE_DAYS or explicitly marked expired.
        """
        if self.status == self.Status.EXPIRED:
            return True
        anchor = self._grace_anchor()
        if not anchor:
            # No anchor => treat as expired to be safe
            return True
        return timezone.now() >= (anchor + timedelta(days=GRACE_DAYS_DEFAULT))

    def is_active_now(self) -> bool:
        """
        Allowed when trial remaining, ACTIVE, or within grace.
        """
        if self.status == self.Status.ACTIVE:
            return True
        if self.status == self.Status.TRIAL and self.days_left_in_trial() > 0:
            return True
        if self.in_grace():
            return True
        return False

    # ---- Billing helpers -----------------------------------------------
    def advance_period(self):
        """
        Move current billing period forward based on plan interval.
        (Simplified month = 30 days, year = 365 days.)
        """
        if not self.current_period_end:
            self.current_period_start = timezone.now()
        else:
            self.current_period_start = self.current_period_end

        if self.plan.interval == SubscriptionPlan.Interval.MONTH:
            self.current_period_end = self.current_period_start + timedelta(days=30)
        else:
            self.current_period_end = self.current_period_start + timedelta(days=365)

        self.next_billing_date = self.current_period_end
        self.save(update_fields=["current_period_start", "current_period_end", "next_billing_date", "updated_at"])

    def __str__(self):
        return f"{self.business} — {self.plan} ({self.get_status_display()})"


# ======================================================================
# Invoices
# ======================================================================
def _next_invoice_number() -> str:
    today = timezone.localdate().strftime("%Y%m%d")
    return f"INV-{today}-{uuid.uuid4().hex[:6].upper()}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=64, unique=True, default=_next_invoice_number)

    # Who is being billed?
    business = models.ForeignKey("tenants.Business", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    # Recipient overrides (fallback to business manager contact if blank)
    to_name = models.CharField(max_length=200, blank=True, default="")
    to_email = models.EmailField(blank=True, default="")
    to_phone = models.CharField(max_length=40, blank=True, default="")

    # Subscription context (optional)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
        ]

    def __str__(self):
        return f"{self.number} ({self.get_status_display()})"

    # -------- Contacts (fallback to business profile) -------------------
    @property
    def manager_email(self) -> str:
        if self.to_email:
            return self.to_email
        try:
            # Adjust these fields if your Business model differs
            return getattr(self.business, "manager_email", "") or getattr(self.business, "email", "")
        except Exception:
            return ""

    @property
    def manager_whatsapp(self) -> str:
        if self.to_phone:
            return self.to_phone
        try:
            return getattr(self.business, "whatsapp_number", "") or getattr(self.business, "phone", "")
        except Exception:
            return ""

    # -------- Money -----------------------------------------------------
    def recalc_totals(self, *, save: bool = False):
        agg = self.items.aggregate(subtotal=Sum(F("qty") * F("unit_price")))
        subtotal = agg["subtotal"] or Decimal("0.00")
        # Basic tax hook: look for business.tax_rate (0-100)
        tax_rate = Decimal(getattr(self.business, "tax_rate", 0) or 0) / Decimal(100)
        tax = (subtotal * tax_rate).quantize(Decimal("0.01")) if tax_rate else Decimal("0.00")
        total = (subtotal + tax).quantize(Decimal("0.01"))
        self.subtotal, self.tax_amount, self.total = subtotal, tax, total
        if save:
            self.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])

    def mark_sent(self):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at", "updated_at"])

    def mark_paid(self):
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])

    def save(self, *args, **kwargs):
        # Auto default due date (7 days) if missing
        if not self.due_date:
            try:
                self.due_date = self.issue_date + timedelta(days=7)
            except Exception:
                pass
        # Keep money fields in sync
        self.recalc_totals(save=False)
        super().save(*args, **kwargs)


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=16, default="ea")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.description} x{self.qty}"

    @property
    def line_total(self) -> Decimal:
        return (self.qty * self.unit_price).quantize(Decimal("0.01"))


# ======================================================================
# Payments
# ======================================================================
class Payment(models.Model):
    class Provider(models.TextChoices):
        AIRTEL = "airtel", "Airtel Money"
        STANDARD_BANK = "standard_bank", "Standard Bank"
        CARD = "card", "Card (VISA/Mastercard)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")

    provider = models.CharField(max_length=20, choices=Provider.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # External references returned by gateways
    reference = models.CharField(max_length=64, blank=True, default="")
    external_id = models.CharField(max_length=128, blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["provider", "status"]),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} {self.amount} {self.currency} ({self.get_status_display()})"

    def mark_succeeded(self):
        self.status = self.Status.SUCCEEDED
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at", "updated_at"])
        # Cascade: mark invoice paid + subscription active
        if self.invoice and self.invoice.status != Invoice.Status.PAID:
            self.invoice.mark_paid()
        try:
            sub = getattr(self.business, "subscription", None)
            if sub:
                sub.status = BusinessSubscription.Status.ACTIVE
                sub.last_payment_at = timezone.now()
                sub.advance_period()
                sub.save(update_fields=["status", "last_payment_at", "updated_at"])
        except Exception:
            # don't blow up payment flow if subscription update fails
            pass


# ======================================================================
# Optional models to satisfy existing imports in admin/views
# ======================================================================
class PaymentMethod(models.Model):
    """
    Simple stored method pointer (e.g., default Airtel account label, masked card).
    Extend in the future as needed.
    """
    KIND_CHOICES = (
        ("airtel", "Airtel Money"),
        ("standard_bank", "Standard Bank"),
        ("card", "Card"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("tenants.Business", on_delete=models.CASCADE, related_name="payment_methods")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    label = models.CharField(max_length=120, blank=True, default="")
    is_default = models.BooleanField(default=False)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business} • {self.get_kind_display()} • {self.label or ''}"


class WebhookEvent(models.Model):
    """
    Store raw webhook posts for auditing/idempotency.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32)       # e.g., 'airtel'
    event_type = models.CharField(max_length=64, blank=True, default="")
    external_id = models.CharField(max_length=128, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["provider", "external_id"]),
            models.Index(fields=["processed"]),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_type or '?'} @ {self.received_at:%Y-%m-%d %H:%M}"


# ======================================================================
# Signals to keep Invoice totals correct on every item change
# ======================================================================
from django.db.models.signals import post_save, post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_save, sender=InvoiceItem)
def _recalc_invoice_on_item_save(sender, instance: InvoiceItem, **kwargs):
    with transaction.atomic():
        inv = instance.invoice
        inv.recalc_totals(save=True)


@receiver(post_delete, sender=InvoiceItem)
def _recalc_invoice_on_item_delete(sender, instance: InvoiceItem, **kwargs):
    with transaction.atomic():
        inv = instance.invoice
        inv.recalc_totals(save=True)


# ======================================================================
# Backwards-compatibility aliases so existing imports keep working
# ======================================================================
Plan = SubscriptionPlan
Subscription = BusinessSubscription
