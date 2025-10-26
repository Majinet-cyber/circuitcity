# inventory/models_docs.py
from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class Doc(models.Model):
    """
    Business document: INVOICE / QUOTATION (and room for others).
    Kept intentionally simple & flexible so the UI/admin can adapt.

    - type:   'INVOICE' | 'QUOTE' | 'CREDIT' ...
    - status: 'DRAFT' | 'SENT' | 'PAID' | 'VOID'
    """
    TYPE_CHOICES = (
        ("INVOICE", "Invoice"),
        ("QUOTE", "Quotation"),
    )
    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("PAID", "Paid"),
        ("VOID", "Void"),
    )

    # identity
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="INVOICE")
    reference = models.CharField(max_length=40, unique=True, help_text="Human reference/number shown to customer.")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")

    # who (keep it stringy; you can replace with a FK later)
    customer_name = models.CharField(max_length=120, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")
    customer_phone = models.CharField(max_length=40, blank=True, default="")
    customer_address = models.TextField(blank=True, default="")

    # dates
    created_at = models.DateTimeField(default=timezone.now)
    issued_at = models.DateTimeField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)        # invoices
    valid_until = models.DateField(blank=True, null=True)     # quotes

    # money
    currency = models.CharField(max_length=8, default="USD")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # ownership
    business = models.ForeignKey("tenants.Business", on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    notes = models.TextField(blank=True, default="")
    meta = models.JSONField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["type", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["reference"]),
        ]
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.type} {self.reference}"

    def compute_totals(self) -> None:
        """
        Recalculate subtotal/tax/discount/total from items.
        """
        items = list(self.items.all())  # related_name on DocItem below
        subtotal = Decimal("0.00")
        for it in items:
            line = (it.unit_price or Decimal("0.00")) * Decimal(it.qty or 0)
            subtotal += line

        tax = self.tax or Decimal("0.00")
        discount = self.discount or Decimal("0.00")
        total = subtotal + tax - discount
        self.subtotal = subtotal
        self.total = total if total >= Decimal("0.00") else Decimal("0.00")

    def save(self, *args, **kwargs):
        # If not explicitly set (e.g., during import), recompute totals
        if kwargs.pop("recompute", True):
            self.compute_totals()
        # Autopopulate issued_at when moving out of draft
        if self.issued_at is None and self.status in {"SENT", "PAID"}:
            self.issued_at = timezone.now()
        super().save(*args, **kwargs)


class DocItem(models.Model):
    """
    Line item for a Doc. Keep product optional & allow free-text description
    for full flexibility (quotes, misc services, etc.)
    """
    doc = models.ForeignKey(Doc, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.SET_NULL, null=True, blank=True)

    description = models.CharField(max_length=200, blank=True, default="")
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Optional snapshot fields to make PDF/export easier
    sku = models.CharField(max_length=64, blank=True, default="")
    meta = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.description or (self.product and str(self.product)) or 'Item'}"

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price or Decimal("0.00")) * Decimal(self.qty or 0)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep parent totals fresh
        try:
            self.doc.save(recompute=True)
        except Exception:
            pass


