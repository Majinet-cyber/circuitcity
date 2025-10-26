# billing/models.py
from __future__ import annotations

import uuid
from datetime import timedelta, datetime
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum, F
from django.utils import timezone

# ----------------------------------------------------------------------
# Config defaults (overridable in settings.py)
# ----------------------------------------------------------------------
CURRENCY_DEFAULT = getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK")
TRIAL_DAYS_DEFAULT = getattr(settings, "BILLING_TRIAL_DAYS", 30)   # default 30-day trial
GRACE_DAYS_DEFAULT = getattr(settings, "BILLING_GRACE_DAYS", 30)   # default 30-day grace


# ======================================================================
# Plans
# ======================================================================
class SubscriptionPlan(models.Model):
    """
    Definition of a pricing plan. Attach feature limits here.
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
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        interval = self.get_interval_display().lower()
        return f"{self.name} â€” {self.currency} {self.amount} / {interval}"


# ======================================================================
# Subscriptions
# ======================================================================
class BusinessSubscription(models.Model):
    """
    One subscription per Business (tenant), describing status + billing cycle.
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
    business = models.OneToOneField(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
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

    # Light audit when revoking/canceling via HQ
    canceled_at = models.DateTimeField(null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["business"]),
            models.Index(fields=["plan", "status"]),
        ]

    # ---- Convenience constructors -------------------------------------
    @classmethod
    def start_trial(
        cls,
        *,
        business,
        plan: SubscriptionPlan,
        days: int = TRIAL_DAYS_DEFAULT,
    ) -> "BusinessSubscription":
        """
        Seed a brand-new subscription with a configurable trial and set
        initial billing anchors to the trial end.
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

    @classmethod
    def ensure_trial_for_business(cls, business) -> "BusinessSubscription":
        """
        Ensure a subscription exists; if missing, seed a trial on the cheapest active plan.
        """
        sub = getattr(business, "subscription", None)
        if sub:
            return sub
        plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
        if not plan:
            plan = SubscriptionPlan.objects.create(code="starter", name="Starter", amount=Decimal("0.00"))
        return cls.start_trial(business=business, plan=plan)

    # ---- Status helpers ------------------------------------------------
    @property
    def is_trial(self) -> bool:
        return self.status == self.Status.TRIAL and self.trial_end and timezone.now() < self.trial_end

    def days_left_in_trial(self) -> int:
        if not self.trial_end or self.status != self.Status.TRIAL:
            return 0
        delta = self.trial_end.date() - timezone.localdate()
        return max(delta.days, 0)

    def days_left_current_period(self) -> int:
        if not self.current_period_end:
            return 0
        delta = self.current_period_end.date() - timezone.localdate()
        return max(delta.days, 0)

    def period_overdue_days(self) -> int:
        if not self.current_period_end:
            return 0
        delta = timezone.localdate() - self.current_period_end.date()
        return max(delta.days, 0)

    def _grace_anchor(self) -> Optional[datetime]:
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

    # ---- Admin-facing helpers (extend/revoke) --------------------------
    def extend_trial(self, extra_days: int, save: bool = True):
        """
        Extend or shorten the trial by +/- days.
        Keeps current_period_end aligned and normalizes status.
        """
        if extra_days == 0:
            return
        # If trial_end missing, anchor on now so +/- works predictably
        anchor = self.trial_end or timezone.now()
        new_end = anchor + timedelta(days=int(extra_days))
        self.trial_end = new_end
        self.current_period_end = new_end

        now = timezone.now()
        if new_end > now and self.status in (self.Status.GRACE, self.Status.PAST_DUE, self.Status.EXPIRED, self.Status.CANCELED):
            # We extended back into the future â†’ make it an active trial
            self.status = self.Status.TRIAL
        elif new_end <= now and self.status == self.Status.TRIAL:
            # Trial now in the past â†’ grace
            self.status = self.Status.GRACE

        if save:
            self.save(update_fields=["trial_end", "current_period_end", "status", "updated_at"])

    def revoke_trial_now(self, by_user=None, save: bool = True):
        """
        Immediately end the trial and cancel access (HQ action).
        """
        now = timezone.now()
        self.trial_end = now
        self.current_period_end = now
        self.status = self.Status.CANCELED
        self.canceled_at = now
        if by_user:
            self.canceled_by = by_user
        if save:
            self.save(
                update_fields=[
                    "trial_end",
                    "current_period_end",
                    "status",
                    "canceled_at",
                    "canceled_by",
                    "updated_at",
                ]
            )

    # Back-compat alias (some views may call end_trial_now)
    def end_trial_now(self, to_grace: bool = True, by_user=None, save: bool = True):
        """
        Alias to keep older code working. If to_grace is True we move to GRACE;
        otherwise we fully cancel (CANCELED). We prefer cancel for explicit revoke.
        """
        if to_grace:
            self.trial_end = timezone.now()
            self.current_period_end = self.trial_end
            self.status = self.Status.GRACE
            if save:
                self.save(update_fields=["trial_end", "current_period_end", "status", "updated_at"])
            return
        # else behave like revoke
        self.revoke_trial_now(by_user=by_user, save=save)

    # ---- State transitions --------------------------------------------
    def enter_grace(self, save: bool = True):
        self.status = self.Status.GRACE
        if save:
            self.save(update_fields=["status", "updated_at"])

    def expire(self, save: bool = True):
        self.status = self.Status.EXPIRED
        if save:
            self.save(update_fields=["status", "updated_at"])

    def activate_now(self, period_days: int | None = None):
        """
        Immediately activate and start a paid period.
        If period_days is None, uses plan interval (30d/365d).
        """
        now = timezone.now()
        self.status = self.Status.ACTIVE
        self.current_period_start = now
        if period_days is None:
            period_days = 30 if self.plan.interval == SubscriptionPlan.Interval.MONTH else 365
        self.current_period_end = now + timedelta(days=period_days)
        self.next_billing_date = self.current_period_end
        self.last_payment_at = now
        self.save(
            update_fields=[
                "status",
                "current_period_start",
                "current_period_end",
                "next_billing_date",
                "last_payment_at",
                "updated_at",
            ]
        )

    def cancel_now(self, at_period_end: bool = True):
        """
        Cancel immediately or at period end.
        """
        self.cancel_at_period_end = at_period_end
        if not at_period_end:
            self.status = self.Status.CANCELED
            self.canceled_at = timezone.now()
        self.save(update_fields=["cancel_at_period_end", "status", "canceled_at", "updated_at"])

    def mark_past_due(self):
        self.status = self.Status.PAST_DUE
        self.save(update_fields=["status", "updated_at"])

    def refresh_status(self) -> None:
        """
        Normalize status based on time anchors.
        - TRIAL â†’ GRACE when trial_end passes (but within grace window)
        - Any (trial/active) â†’ EXPIRED after grace window elapses
        - ACTIVE and past current_period_end â†’ GRACE unless cancel_at_period_end=True (then CANCELED)
        """
        now = timezone.now()
        changed = False

        # Trial logic
        if self.status == self.Status.TRIAL:
            if self.trial_end and now >= self.trial_end:
                # Trial ended: enter grace
                self.enter_grace(save=False)
                changed = True

        # Active period end
        if self.status == self.Status.ACTIVE and self.current_period_end and now > self.current_period_end:
            if self.cancel_at_period_end:
                self.status = self.Status.CANCELED
            else:
                self.enter_grace(save=False)
            changed = True

        # Grace / expiration check
        if self.status in (self.Status.GRACE, self.Status.TRIAL, self.Status.ACTIVE):
            if self.is_expired():
                self.status = self.Status.EXPIRED
                changed = True

        if changed:
            self.save(update_fields=["status", "updated_at"])

    # ---- Billing helpers -----------------------------------------------
    def advance_period(self):
        """
        Move current billing period forward based on plan interval.
        (Simplified month = 30 days, year = 365 days to avoid external deps.)
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
        return f"{self.business} â€” {self.plan} ({self.get_status_display()})"


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

    # -------- State helpers on success ---------------------------------
    def mark_succeeded(self):
        """
        Mark payment succeeded, cascade invoice & subscription updates.
        """
        self.status = self.Status.SUCCEEDED
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at", "updated_at"])

        # Invoice
        if self.invoice and self.invoice.status != Invoice.Status.PAID:
            self.invoice.mark_paid()

        # Subscription
        try:
            sub = getattr(self.business, "subscription", None)
            if sub:
                sub.status = BusinessSubscription.Status.ACTIVE
                sub.last_payment_at = timezone.now()
                sub.advance_period()
                sub.save(update_fields=["status", "last_payment_at", "updated_at"])
        except Exception:
            # Donâ€™t blow up payment flow if subscription update fails
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
        return f"{self.business} â€¢ {self.get_kind_display()} â€¢ {self.label or ''}"


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


# (Optional) Seed a trial automatically when a Business is created.
# Wrapped in a try/import guard so it won't break during initial bootstrap.
try:
    from django.db.models.signals import post_save as _post_save_business
    from tenants.models import Business as _BusinessModel  # type: ignore

    @_post_save_business.connect(sender=_BusinessModel)
    def _auto_seed_trial_on_business_create(sender, instance, created, **kwargs):
        if created:
            try:
                BusinessSubscription.ensure_trial_for_business(instance)
            except Exception:
                # Avoid crashing tenant creation path
                pass
except Exception:
    # No tenants model yet (e.g., during first migration)
    pass


# ======================================================================
# Backwards-compatibility aliases so existing imports keep working
# ======================================================================
Plan = SubscriptionPlan
Subscription = BusinessSubscription


