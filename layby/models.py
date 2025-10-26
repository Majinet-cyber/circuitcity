# layby/models.py
from __future__ import annotations

import random
from decimal import Decimal
from django.apps import apps
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


def _generate_ref() -> str:
    """
    Generate a unique human-friendly reference like AH1234.
    Retries a few times to avoid collisions.
    """
    Model = apps.get_model("layby", "LaybyOrder")
    for _ in range(16):
        ref = f"AH{random.randint(0, 9999):04d}"
        if not Model.objects.filter(ref=ref).exists():  # type: ignore[arg-type]
            return ref
    # Ultra-rare fallback
    return f"AH{random.randint(0, 9999):04d}"


PHONE_RE = RegexValidator(r"^[0-9+\-\s]{7,20}$", "Enter a valid phone number.")
ID8_RE = RegexValidator(r"^\d{8}$", "ID number must be exactly 8 digits.")


class LaybyOrder(models.Model):
    # Public identifier
    ref = models.CharField(
        max_length=16,
        unique=True,
        default=_generate_ref,
        editable=False,
    )

    # Owner/creator (views may check agent/created_by)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="layby_orders",
        null=True,
        blank=True,
    )

    # Customer
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=32, blank=True, validators=[PHONE_RE])

    # National ID â€” exactly 8 digits
    id_number = models.CharField(
        max_length=8,
        validators=[ID8_RE],
        help_text="Enter exactly 8 digits",
    )
    id_photo = models.ImageField(upload_to="layby/id_photos/", null=True, blank=True)

    # Next of kin
    kin1_name = models.CharField(max_length=120, blank=True)
    kin1_phone = models.CharField(max_length=32, blank=True, validators=[PHONE_RE])
    kin2_name = models.CharField(max_length=120, blank=True)
    kin2_phone = models.CharField(max_length=32, blank=True, validators=[PHONE_RE])

    # Product (chosen from stock UI)
    item_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64)

    # Terms & pricing
    term_months = models.PositiveIntegerField(default=3)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["ref"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["status", "created_by"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(term_months__gte=1) & Q(term_months__lte=12), name="layby_term_1_to_12"),
            models.CheckConstraint(check=Q(total_price__gte=0), name="layby_total_price_nonneg"),
            models.CheckConstraint(check=Q(deposit_amount__gte=0), name="layby_deposit_nonneg"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.ref} Â· {self.customer_name}"

    # --------- convenience (not stored in DB) ---------
    @property
    def amount_paid(self) -> Decimal:
        extra = (
            self.payments.aggregate(s=models.Sum("amount")).get("s")
            if hasattr(self, "payments")
            else None
        ) or Decimal("0.00")
        return (self.deposit_amount or Decimal("0.00")) + extra

    @property
    def balance(self) -> Decimal:
        try:
            return max((self.total_price or Decimal("0.00")) - self.amount_paid, Decimal("0.00"))
        except Exception:
            return Decimal("0.00")


class LaybyPayment(models.Model):
    """
    Payments against a layby order.
    """
    order = models.ForeignKey(LaybyOrder, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=24, default="cash")
    tx_ref = models.CharField(max_length=64, blank=True)

    # Who/when
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["received_at"]),
            models.Index(fields=["order", "received_at"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(amount__gt=0), name="layby_payment_amount_positive"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.order.ref} Â· {self.amount}"


