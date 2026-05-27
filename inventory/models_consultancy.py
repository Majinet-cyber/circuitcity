# inventory/models_consultancy.py
"""
Consultancy & Services vertical models.

Supports: consultants, software developers, designers, engineers, accountants,
tutors, agencies, repair businesses, advisory firms, freelancers.

Core flow: Client → Project/Service → Quote → Invoice → Payment
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ConsultancyClient(models.Model):
    """A client / customer of the consultancy."""
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_clients",
    )
    name = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return self.company or self.name

    @property
    def display_name(self):
        if self.company:
            return f"{self.name} ({self.company})"
        return self.name


# ---------------------------------------------------------------------------
# Project / Service Engagement
# ---------------------------------------------------------------------------

class ProjectStatus(models.TextChoices):
    LEAD = "lead", "Lead"
    QUOTED = "quoted", "Quoted"
    APPROVED = "approved", "Approved"
    IN_PROGRESS = "in_progress", "In Progress"
    DELIVERED = "delivered", "Delivered"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class ConsultancyProject(models.Model):
    """
    A service engagement or project for a client.
    Can be a one-off project, ongoing retainer, or single service.
    """
    PROJECT_TYPE_CHOICES = [
        ("project", "Project"),
        ("retainer", "Retainer"),
        ("service", "One-off Service"),
        ("repair", "Repair"),
        ("advisory", "Advisory"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_projects",
    )
    client = models.ForeignKey(
        ConsultancyClient, on_delete=models.CASCADE, related_name="projects",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project_type = models.CharField(
        max_length=20, choices=PROJECT_TYPE_CHOICES, default="project",
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.LEAD,
    )

    # Dates
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    # Budget / value
    agreed_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Agreed contract/project value",
    )

    # Retainer fields
    monthly_retainer = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Monthly retainer fee (for retainer projects)",
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_consultancy_projects",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Project"
        verbose_name_plural = "Projects"

    def __str__(self):
        return f"{self.title} — {self.client}"

    @property
    def is_overdue(self):
        if self.deadline and self.status not in [
            ProjectStatus.PAID, ProjectStatus.CANCELLED, ProjectStatus.DELIVERED
        ]:
            return self.deadline < timezone.localdate()
        return False

    @property
    def total_invoiced(self) -> Decimal:
        return self.invoices.filter(is_void=False).aggregate(
            total=models.Sum("total_amount")
        ).get("total") or Decimal("0")

    @property
    def total_paid(self) -> Decimal:
        return self.invoices.filter(is_void=False).aggregate(
            total=models.Sum("amount_paid")
        ).get("total") or Decimal("0")

    @property
    def outstanding_balance(self) -> Decimal:
        return self.total_invoiced - self.total_paid


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------

class ConsultancyQuote(models.Model):
    """A quote/proposal sent to a client."""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_quotes",
    )
    client = models.ForeignKey(
        ConsultancyClient, on_delete=models.CASCADE, related_name="quotes",
    )
    project = models.ForeignKey(
        ConsultancyProject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="quotes",
    )

    quote_number = models.CharField(max_length=50, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_consultancy_quotes",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Quote"

    def __str__(self):
        return f"Quote #{self.quote_number or self.pk} — {self.client}"

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new and not self.quote_number:
            super().save(*args, **kwargs)
            self.quote_number = f"Q{self.pk:04d}"
            kwargs.pop("force_insert", None)
            kwargs.pop("force_update", None)
            kwargs['update_fields'] = ['quote_number']
        self.total_amount = self.subtotal - self.discount + self.tax
        if not is_new or self.quote_number:
            kwargs.pop("force_insert", None)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Quote Line Item
# ---------------------------------------------------------------------------

class ConsultancyQuoteItem(models.Model):
    """A line item in a quote."""
    quote = models.ForeignKey(
        ConsultancyQuote, on_delete=models.CASCADE, related_name="line_items",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        self.total = self.quantity * self.unit_price
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class ConsultancyInvoice(models.Model):
    """An invoice issued to a client."""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("partial", "Partially Paid"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_invoices",
    )
    client = models.ForeignKey(
        ConsultancyClient, on_delete=models.CASCADE, related_name="invoices",
    )
    project = models.ForeignKey(
        ConsultancyProject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
    )
    quote = models.ForeignKey(
        ConsultancyQuote, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
        help_text="Quote this invoice was generated from",
    )

    invoice_number = models.CharField(max_length=50, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_void = models.BooleanField(default=False)

    issued_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_consultancy_invoices",
    )

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "Invoice"

    def __str__(self):
        return f"Invoice #{self.invoice_number or self.pk} — {self.client}"

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new and not self.invoice_number:
            # First save to get pk (always an INSERT for new records).
            super().save(*args, **kwargs)
            self.invoice_number = f"INV{self.pk:04d}"
            # Strip force_insert/force_update so the follow-up save is a plain UPDATE.
            kwargs.pop("force_insert", None)
            kwargs.pop("force_update", None)
            kwargs['update_fields'] = ['invoice_number']
        self.total_amount = self.subtotal - self.discount + self.tax
        # Update status based on payment
        if not self.is_void:
            if self.amount_paid >= self.total_amount and self.total_amount > 0:
                self.status = "paid"
            elif self.amount_paid > 0:
                self.status = "partial"
            elif self.due_date and self.due_date < timezone.localdate() and self.status not in ("paid",):
                self.status = "overdue"
        if not is_new or self.invoice_number:
            # Strip force_insert for subsequent saves on existing objects.
            kwargs.pop("force_insert", None)
        super().save(*args, **kwargs)

    @property
    def balance_due(self) -> Decimal:
        return max(Decimal("0"), self.total_amount - self.amount_paid)

    @property
    def is_overdue(self) -> bool:
        return (
            self.due_date is not None
            and self.due_date < timezone.localdate()
            and self.status not in ("paid", "void")
            and not self.is_void
        )


# ---------------------------------------------------------------------------
# Invoice Line Item
# ---------------------------------------------------------------------------

class ConsultancyInvoiceItem(models.Model):
    """A line item in an invoice."""
    invoice = models.ForeignKey(
        ConsultancyInvoice, on_delete=models.CASCADE, related_name="line_items",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]

    def save(self, *args, **kwargs):
        self.total = self.quantity * self.unit_price
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class ConsultancyPayment(models.Model):
    """A payment received against an invoice."""
    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
        ("airtel_money", "Airtel Money"),
        ("tnm_mpamba", "TNM Mpamba"),
        ("cheque", "Cheque"),
        ("other", "Other"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_payments",
    )
    invoice = models.ForeignKey(
        ConsultancyInvoice, on_delete=models.CASCADE, related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="cash")
    reference = models.CharField(max_length=100, blank=True, help_text="Reference / transaction number")
    notes = models.TextField(blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "Payment"

    def __str__(self):
        return f"Payment MWK {self.amount:,.0f} for {self.invoice}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update invoice amount_paid
        total_paid = self.invoice.payments.aggregate(
            total=models.Sum("amount")
        ).get("total") or Decimal("0")
        self.invoice.amount_paid = total_paid
        self.invoice.save(update_fields=["amount_paid", "status", "total_amount"])


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class ConsultancyExpense(models.Model):
    """Operating expenses for a consultancy business."""
    CATEGORY_CHOICES = [
        ("salaries", "Salaries"),
        ("rent", "Rent / Office"),
        ("software", "Software & Tools"),
        ("transport", "Transport"),
        ("utilities", "Utilities"),
        ("marketing", "Marketing"),
        ("subcontract", "Subcontracting"),
        ("training", "Training"),
        ("other", "Other"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="consultancy_expenses",
    )
    project = models.ForeignKey(
        ConsultancyProject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses",
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date"]
        verbose_name = "Expense"

    def __str__(self):
        return f"{self.description} — MWK {self.amount:,.0f}"
