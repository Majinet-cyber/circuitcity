# billing/models.py
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Sum
from django.utils import timezone

# ----------------------------------------------------------------------
# Config defaults (overridable in settings.py)
# ----------------------------------------------------------------------
CURRENCY_DEFAULT = getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK")
TRIAL_DAYS_DEFAULT = getattr(settings, "BILLING_TRIAL_DAYS", 30)  # default 30-day trial
GRACE_DAYS_DEFAULT = getattr(settings, "BILLING_GRACE_DAYS", 30)  # default 30-day grace


# ======================================================================
# Pending Checkout (tracks plan selection before payment confirmation)
# ======================================================================
class PendingCheckout(models.Model):
    """
    Tracks plan selection and checkout attempts BEFORE payment is confirmed.
    This avoids creating invoices or locking in plans until payment succeeds.
    """
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="pending_checkouts",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    
    selected_plan = models.ForeignKey(
        "SubscriptionPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_checkouts",
    )
    selected_plan_code = models.CharField(
        max_length=50,
        help_text="Plan code user selected",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Plan amount at time of selection",
    )
    currency = models.CharField(max_length=10, default="MWK")
    
    tx_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Payment provider transaction reference",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (payment method, provider, etc.)",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pending checkout expires",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["tx_ref"]),
        ]
    
    def __str__(self):
        return f"{self.business.name} - {self.selected_plan_code} - {self.status}"
    
    def mark_succeeded(self):
        """Mark this checkout as succeeded."""
        self.status = self.Status.SUCCEEDED
        self.save(update_fields=["status", "updated_at"])
    
    def mark_failed(self, reason: str = ""):
        """Mark this checkout as failed."""
        self.status = self.Status.FAILED
        if reason:
            self.metadata["failure_reason"] = reason
        self.save(update_fields=["status", "metadata", "updated_at"])


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
        TRIALING = "trialing", "Trialing"
        TRIAL = "trial", "Trial"  # Legacy alias
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        GRACE = "grace", "Grace"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"
        CANCELLED = "cancelled", "Cancelled"  # Legacy alias
        EXPIRED = "expired", "Expired"

    class Method(models.TextChoices):
        NONE = "none", "None"
        AIRTEL = "airtel", "Airtel Money"
        STANDARD_BANK = "standard_bank", "Standard Bank"
        CARD = "card", "Card (VISA/Mastercard)"
        STRIPE = "stripe", "Stripe"
        PESAPAL = "pesapal", "Pesapal"

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

    # Provider-specific identifiers
    provider_customer_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Payment provider customer ID (PayChangu customer, Stripe customer, etc.)",
    )
    provider_subscription_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Payment provider subscription ID (if provider manages recurring billing)",
    )

    # Legacy provider fields (kept for backward compatibility)
    stripe_subscription_id = models.CharField(
        max_length=255, blank=True, default="", help_text="Stripe subscription ID"
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="", help_text="Stripe customer ID")
    pesapal_order_tracking_id = models.CharField(
        max_length=255, blank=True, default="", help_text="Pesapal order tracking ID"
    )
    pesapal_merchant_reference = models.CharField(
        max_length=255, blank=True, default="", help_text="Pesapal merchant reference"
    )

    # Light audit when revoking/canceling via HQ
    canceled_at = models.DateTimeField(null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # Dunning & auto-billing fields
    billing_phone = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Phone number (MSISDN) for automated billing prompts. Format: +265991234567",
    )
    grace_until = models.DateTimeField(
        null=True, blank=True, help_text="Grace period end (period_end + 2 days when renewal unpaid)"
    )
    past_due_since = models.DateTimeField(null=True, blank=True, help_text="When subscription became past_due")
    suspended_at = models.DateTimeField(null=True, blank=True, help_text="When subscription was suspended")

    # Cancellation tracking
    cancel_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When cancel_at_period_end was set (user requested cancellation)",
    )

    # HQ notification tracking (idempotency)
    hq_notified_cancel_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When HQ was notified of cancellation request (idempotency)",
    )
    hq_notified_canceled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When HQ was notified of effective cancellation (idempotency)",
    )
    hq_notified_suspended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When HQ was notified of suspension (idempotency)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["business"]),
            models.Index(fields=["plan", "status"]),
            models.Index(fields=["provider_customer_ref"]),
            models.Index(fields=["provider_subscription_ref"]),
            models.Index(fields=["stripe_subscription_id"]),
            models.Index(fields=["pesapal_order_tracking_id"]),
            models.Index(fields=["status", "current_period_end"]),
            models.Index(fields=["status", "trial_end"]),
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
        Ensure a subscription exists; if missing, seed a trial using SSOT plan resolver.
        
        This method is idempotent - calling it multiple times is safe.
        It uses the centralized plan resolver to guarantee a valid plan.
        """
        # Check if subscription already exists
        sub = getattr(business, "subscription", None)
        if sub:
            return sub
        
        # Also check via direct query (more reliable)
        existing = cls.objects.filter(business=business).first()
        if existing:
            return existing
        
        # Use SSOT plan resolver (guaranteed to return a valid plan)
        try:
            from billing.services.plan_resolver import get_default_trial_plan
            plan = get_default_trial_plan(
                business_kind=getattr(business, "business_kind", None),
                create_if_missing=True,
            )
        except Exception:
            # Fallback if resolver fails (should never happen)
            plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
            if not plan:
                plan = SubscriptionPlan.objects.create(
                    code="starter", 
                    name="Starter", 
                    amount=Decimal("0.00"),
                    is_active=True,
                )
        
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
        if new_end > now and self.status in (
            self.Status.GRACE,
            self.Status.PAST_DUE,
            self.Status.EXPIRED,
            self.Status.CANCELED,
        ):
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

    def suspend(self, save: bool = True):
        """Suspend subscription (block access, but preserve data)."""
        self.status = self.Status.SUSPENDED
        if save:
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
    """
    Generate atomic, year-based invoice number: INV-YYYY-000123
    Uses database-level locking to ensure uniqueness and sequential numbering.
    """
    from django.db import transaction

    year = timezone.now().year

    with transaction.atomic():
        # Use select_for_update to lock the row during increment
        # Find the highest invoice number for this year
        last_invoice = (
            Invoice.objects.filter(number__startswith=f"INV-{year}-").order_by("-number").select_for_update().first()
        )

        if last_invoice:
            # Extract the sequence number from last invoice
            try:
                # Format: INV-YYYY-000123
                parts = last_invoice.number.split("-")
                if len(parts) == 3 and parts[0] == "INV" and parts[1] == str(year):
                    sequence = int(parts[2])
                    next_sequence = sequence + 1
                else:
                    next_sequence = 1
            except (ValueError, IndexError):
                next_sequence = 1
        else:
            next_sequence = 1

        # Format with 6-digit zero-padded sequence
        invoice_number = f"INV-{year}-{next_sequence:06d}"

        # Double-check uniqueness (race condition protection)
        if Invoice.objects.filter(number=invoice_number).exists():
            # If collision, try next number
            next_sequence += 1
            invoice_number = f"INV-{year}-{next_sequence:06d}"

        return invoice_number


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        VOID = "void", "Void"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=64, unique=True, default=_next_invoice_number)

    # Who is being billed?
    business = models.ForeignKey(
        "tenants.Business", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    subscription = models.ForeignKey(
        "BusinessSubscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
        help_text="Associated subscription if this is a recurring billing invoice",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    # Recipient overrides (fallback to business manager contact if blank)
    to_name = models.CharField(max_length=200, blank=True, default="")
    to_email = models.EmailField(blank=True, default="")
    to_phone = models.CharField(max_length=40, blank=True, default="")

    # Billing period (for subscription invoices)
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)

    # Legacy fields (kept for backward compatibility)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Dates
    issue_date = models.DateField(default=timezone.localdate)
    issued_at = models.DateTimeField(null=True, blank=True, help_text="When invoice was issued/finalized")
    due_date = models.DateField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, help_text="When payment is due (with time)")
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Dunning / Auto-billing retry fields
    next_attempt_at = models.DateTimeField(
        null=True, blank=True, help_text="When to attempt next billing retry (dunning)"
    )
    attempt_count = models.PositiveIntegerField(default=0, help_text="Number of billing attempts made")
    locked_for_dunning = models.BooleanField(default=False, help_text="Lock to prevent concurrent dunning processing")

    # Email notification tracking (idempotency)
    email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When invoice confirmation email was sent (idempotency)",
    )
    email_send_attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of email send attempts",
    )
    
    # HQ notification tracking (idempotency)
    hq_notified_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When HQ was notified of payment (idempotency)",
    )

    # Money
    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), help_text="Tax amount (alias for tax_amount)"
    )
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Payment provider reference
    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Payment provider transaction reference (PayChangu tx_ref, Stripe payment_intent, etc.)",
    )

    # PDF generation
    pdf_file = models.FileField(
        upload_to="invoices/pdfs/%Y/%m/", blank=True, null=True, help_text="Generated PDF invoice file"
    )
    pdf_generated_at = models.DateTimeField(null=True, blank=True, help_text="When PDF was last generated")

    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["subscription"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
            models.Index(fields=["provider_reference"]),
            models.Index(fields=["status", "due_date"]),
        ]

    def __str__(self):
        return f"{self.number} ({self.get_status_display()})"

    def mark_issued(self):
        """Mark invoice as issued (finalized and ready to send)."""
        self.status = self.Status.ISSUED
        self.issued_at = timezone.now()
        self.save(update_fields=["status", "issued_at", "updated_at"])

    def mark_void(self, reason: str = ""):
        """Mark invoice as void (cancelled after payment or refund)."""
        self.status = self.Status.VOID
        if reason:
            self.meta["void_reason"] = reason
            self.meta["voided_at"] = timezone.now().isoformat()
        self.save(update_fields=["status", "meta", "updated_at"])

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

    @property
    def tax_total(self) -> Decimal:
        """
        Alias for tax_amount to maintain template compatibility.
        """
        return self.tax_amount

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
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)]
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.description} x{self.qty}"

    @property
    def line_total(self) -> Decimal:
        return (self.qty * self.unit_price).quantize(Decimal("0.01"))


# ======================================================================
# Billing Attempts (Dunning Audit Trail)
# ======================================================================
class BillingAttempt(models.Model):
    """
    Records each attempt to bill a subscription renewal invoice.
    Used for dunning retries and audit trail (idempotent + auditable).
    """

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        FAILED = "failed", "Failed"
        SUCCEEDED = "succeeded", "Succeeded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="billing_attempts")
    subscription = models.ForeignKey(
        BusinessSubscription, on_delete=models.CASCADE, related_name="billing_attempts", null=True, blank=True
    )

    attempt_no = models.PositiveIntegerField(default=1, help_text="Attempt number (1-6 for dunning retries)")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIATED)

    # Payment session details
    provider_ref = models.CharField(
        max_length=255, blank=True, default="", help_text="Payment provider reference (tx_ref, etc.)"
    )
    payment_session_id = models.CharField(
        max_length=255, blank=True, default="", help_text="Payment session/checkout ID"
    )
    error_message = models.TextField(blank=True, default="", help_text="Error message if failed")

    # Metadata
    meta = models.JSONField(default=dict, blank=True, help_text="Additional metadata (method, amount, etc.)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice", "attempt_no"]),
            models.Index(fields=["subscription", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Attempt #{self.attempt_no} for {self.invoice} - {self.get_status_display()}"

    def mark_succeeded(self, provider_ref: str = "", save: bool = True):
        """Mark this attempt as succeeded."""
        self.status = self.Status.SUCCEEDED
        if provider_ref:
            self.provider_ref = provider_ref
        if save:
            self.save(update_fields=["status", "provider_ref", "updated_at"])

    def mark_failed(self, error_message: str = "", save: bool = True):
        """Mark this attempt as failed."""
        self.status = self.Status.FAILED
        if error_message:
            self.error_message = error_message
        if save:
            self.save(update_fields=["status", "error_message", "updated_at"])


# ======================================================================
# Payments
# ======================================================================
class Payment(models.Model):
    class Provider(models.TextChoices):
        AIRTEL = "airtel", "Airtel Money"
        STANDARD_BANK = "standard_bank", "Standard Bank"
        CARD = "card", "Card (VISA/Mastercard)"
        STRIPE = "stripe", "Stripe"
        PESAPAL = "pesapal", "Pesapal"
        PAYCHANGU = "paychangu", "PayChangu"

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

    # Payment failure details
    failure_reason = models.TextField(
        blank=True, null=True, help_text="Reason for payment failure (if status is FAILED)"
    )

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

    def mark_failed(self, failure_reason: str = "", save: bool = True):
        """
        Mark payment as failed with optional failure reason.

        Args:
            failure_reason: Reason for failure (e.g., "Insufficient funds", "Card declined")
            save: Whether to save the model (default True)
        """
        self.status = self.Status.FAILED
        if failure_reason:
            self.failure_reason = failure_reason
        if save:
            self.save(update_fields=["status", "failure_reason", "updated_at"])


# ======================================================================
# Payment Event Audit (Webhook Event Store with Idempotency)
# ======================================================================
class PaymentEvent(models.Model):
    """
    Immutable audit log of all payment-related events (webhooks, API callbacks).
    Ensures idempotency and provides full audit trail for reconciliation.

    Each event is stored exactly once based on idempotency_key.
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    class Provider(models.TextChoices):
        PAYCHANGU = "paychangu", "PayChangu"
        STRIPE = "stripe", "Stripe"
        PESAPAL = "pesapal", "Pesapal"
        AIRTEL = "airtel", "Airtel Money"
        TNM = "tnm", "TNM Mpamba"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Provider and event identification
    provider = models.CharField(max_length=32, choices=Provider.choices, db_index=True)
    event_id = models.CharField(
        max_length=255, blank=True, default="", db_index=True, help_text="Provider's event ID if available"
    )
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Computed hash: provider + tx_ref + event_type + amount + currency",
    )

    # Transaction references
    reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Transaction reference (tx_ref, payment_id, etc.)",
    )
    transaction_id = models.CharField(
        max_length=255, blank=True, default="", db_index=True, help_text="Alternative transaction identifier"
    )

    # Event data
    event_type = models.CharField(max_length=64, blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True, help_text="Raw webhook payload")

    # Security
    signature_valid = models.BooleanField(default=False, help_text="Whether webhook signature was verified")

    # Processing status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    error_message = models.TextField(blank=True, default="")

    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["provider", "reference"]),
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["status", "received_at"]),
            models.Index(fields=["idempotency_key"]),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_type or 'webhook'} @ {self.received_at:%Y-%m-%d %H:%M}"

    def mark_processed(self, save: bool = True):
        """Mark event as successfully processed."""
        self.status = self.Status.PROCESSED
        self.processed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "processed_at"])

    def mark_failed(self, error: str, save: bool = True):
        """Mark event as failed with error message."""
        self.status = self.Status.FAILED
        self.error_message = error
        self.processed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "error_message", "processed_at"])

    def mark_ignored(self, reason: str = "", save: bool = True):
        """Mark event as ignored (e.g., already processed, unknown tx_ref)."""
        self.status = self.Status.IGNORED
        if reason:
            self.error_message = reason
        self.processed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "error_message", "processed_at"])


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
        ("stripe", "Stripe"),
        ("pesapal", "Pesapal"),
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
    provider = models.CharField(max_length=32)  # e.g., 'airtel'
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
from django.db.models.signals import post_delete, post_save  # noqa: E402
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


# NOTE: Trial subscription creation is now handled by tenants/signals.py
# using transaction.on_commit() for transaction safety. The signal there
# uses the SSOT plan resolver from billing.services.plan_resolver.
# 
# DO NOT re-add a signal here - it would create duplicate subscriptions
# and/or cause race conditions.
#
# See: tenants/signals.py:ensure_trial_on_business_creation


# ======================================================================
# PayChangu Transaction Tracking (Idempotent)
# ======================================================================
class PaymentTransaction(models.Model):
    """
    Provider-specific transaction records for PayChangu (and extensible to others).
    Tracks checkout initiation, webhook payloads, and verification results.
    Ensures no cross-tenant leakage via business + location FKs.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    # Tenant isolation
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="payment_transactions",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        related_name="payment_transactions",
        null=True,
        blank=True,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_transactions_created",
    )

    # Provider and transaction details
    provider = models.CharField(max_length=20, default="paychangu", db_index=True)
    tx_ref = models.CharField(max_length=128, unique=True, db_index=True)
    charge_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        help_text="PayChangu charge ID for mobile money direct charge",
    )
    payment_method = models.CharField(
        max_length=30, blank=True, default="", help_text="Payment method: airtel, tnm, card, etc."
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Checkout URL and payloads
    checkout_url = models.URLField(max_length=512, blank=True, default="")
    raw_init_payload = models.JSONField(default=dict, blank=True, help_text="Response from initiate API")
    raw_webhook_payload = models.JSONField(default=dict, blank=True, help_text="Webhook notification payload")
    raw_verify_payload = models.JSONField(default=dict, blank=True, help_text="Response from verify API")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["tx_ref"]),
        ]

    def __str__(self):
        return f"{self.provider} {self.tx_ref} - {self.get_status_display()}"

    def mark_success(self, verify_payload: dict = None):
        """
        Idempotently mark transaction as successful.
        Only updates if not already SUCCESS.
        """
        if self.status == self.Status.SUCCESS:
            return  # Already successful, no-op

        self.status = self.Status.SUCCESS
        if verify_payload:
            self.raw_verify_payload = verify_payload
        self.save(update_fields=["status", "raw_verify_payload", "updated_at"])

    def mark_failed(self, verify_payload: dict = None):
        """Mark transaction as failed."""
        if self.status == self.Status.SUCCESS:
            return  # Don't downgrade success to failure

        self.status = self.Status.FAILED
        if verify_payload:
            self.raw_verify_payload = verify_payload
        self.save(update_fields=["status", "raw_verify_payload", "updated_at"])


# ======================================================================
# Subscription Change Intent (Upgrade/Downgrade)
# ======================================================================
class SubscriptionChangeIntent(models.Model):
    """
    Tracks a pending subscription upgrade or downgrade.
    Created when user initiates an upgrade, applied by webhook after payment confirmed.
    Prevents duplicate upgrades on webhook retries via idempotency_key.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        APPLIED = "applied", "Applied"
        CANCELED = "canceled", "Canceled"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "tenants.Business",
        on_delete=models.CASCADE,
        related_name="subscription_change_intents",
    )
    subscription = models.ForeignKey(
        BusinessSubscription,
        on_delete=models.CASCADE,
        related_name="change_intents",
    )

    # Plan change details
    from_plan_code = models.CharField(max_length=50)
    to_plan_code = models.CharField(max_length=50)
    from_plan_amount = models.DecimalField(max_digits=12, decimal_places=2)
    to_plan_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Payment details
    amount_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Amount to pay for upgrade (difference between plans)",
    )
    currency = models.CharField(max_length=8, default=CURRENCY_DEFAULT)

    # Status tracking
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Payment provider references
    paychangu_reference = models.CharField(max_length=255, blank=True, default="", db_index=True)
    tx_ref = models.CharField(max_length=255, blank=True, default="", db_index=True)

    # Idempotency: prevents duplicate application on webhook retries
    # Format: "{business_id}:{from_plan}:{to_plan}:{period_start_timestamp}"
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["subscription", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["paychangu_reference"]),
            models.Index(fields=["tx_ref"]),
        ]

    def __str__(self):
        return f"{self.from_plan_code} → {self.to_plan_code} ({self.get_status_display()})"

    def mark_paid(self):
        """Mark intent as paid (payment confirmed)."""
        if self.status == self.Status.APPLIED:
            return  # Already applied, no-op
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])

    def mark_applied(self):
        """Mark intent as applied (plan upgraded in subscription)."""
        if self.status == self.Status.APPLIED:
            return  # Already applied, idempotent
        self.status = self.Status.APPLIED
        self.applied_at = timezone.now()
        self.save(update_fields=["status", "applied_at", "updated_at"])

    def mark_canceled(self):
        """Mark intent as canceled."""
        self.status = self.Status.CANCELED
        self.canceled_at = timezone.now()
        self.save(update_fields=["status", "canceled_at", "updated_at"])

    def mark_failed(self):
        """Mark intent as failed."""
        self.status = self.Status.FAILED
        self.save(update_fields=["status", "updated_at"])


# ======================================================================
# Backwards-compatibility aliases so existing imports keep working
# ======================================================================
Plan = SubscriptionPlan
Subscription = BusinessSubscription
InvoiceLineItem = InvoiceItem  # Alias for consistency with requirements
