# inventory/models_butchery.py
"""
Butchery vertical models.

Workflow:
  Supplier → Intake (carcass/live animal) → Processing/Cutting → Cuts/Products → Sale

A butchery tracks meat intake by weight, allocates cost across cuts, and sells
by kg or by quantity. Each intake batch can be partially converted to multiple
named cuts. Daily ledgers can be locked to finalise books.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Payment method choices
# ---------------------------------------------------------------------------

class ButcheryPaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    AIRTEL_MONEY = "airtel_money", "Airtel Money"
    TNM_MPAMBA = "tnm_mpamba", "TNM Mpamba"
    BANK = "bank", "Bank Transfer"
    CREDIT = "credit", "Credit / Balance"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# Meat Type choices
# ---------------------------------------------------------------------------

class MeatType(models.TextChoices):
    BEEF = "beef", "Beef"
    GOAT = "goat", "Goat"
    CHICKEN = "chicken", "Chicken"
    PORK = "pork", "Pork"
    LAMB = "lamb", "Lamb"
    FISH = "fish", "Fish"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# Product Category choices
# ---------------------------------------------------------------------------

class ButcheryCategory(models.TextChoices):
    PORK = "pork", "Pork"
    SAUSAGE = "sausage", "Sausage"
    BEEF = "beef", "Beef"
    GOAT = "goat", "Goat"
    CHICKEN = "chicken", "Chicken / Zinziri"
    LAMB = "lamb", "Lamb"
    FISH = "fish", "Fish"
    DRINKS = "drinks", "Drinks"
    SIDES = "sides", "Sides & Other"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# Cut / Product
# ---------------------------------------------------------------------------

class ButcheryProduct(models.Model):
    """
    A named cut or product sold by the butchery (e.g. Beef Steak, Goat Ribs, Mince).
    Stock is tracked in the product's unit (kg, pcs, pack, bottle, etc.).
    """

    UNIT_KG = "kg"
    UNIT_PIECE = "pcs"
    UNIT_PACK = "pack"
    UNIT_PORTION = "portion"
    UNIT_BOTTLE = "bottle"
    UNIT_BOX = "box"
    UNIT_BIRD = "bird"
    UNIT_SERVICE = "service"
    UNIT_OTHER = "other"

    UNIT_CHOICES = [
        (UNIT_KG, "kg"),
        (UNIT_PIECE, "Pieces"),
        (UNIT_PACK, "Pack"),
        (UNIT_PORTION, "Portion"),
        (UNIT_BOTTLE, "Bottle"),
        (UNIT_BOX, "Box"),
        (UNIT_BIRD, "Bird"),
        (UNIT_SERVICE, "Service"),
        (UNIT_OTHER, "Other"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_products",
    )
    name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=20,
        choices=ButcheryCategory.choices,
        default=ButcheryCategory.OTHER,
        db_index=True,
    )
    meat_type = models.CharField(max_length=20, choices=MeatType.choices, default=MeatType.BEEF)
    description = models.TextField(blank=True)

    # Pricing
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_KG)

    # Stock
    stock_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("2.000"))

    # Meta
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Butchery Product"
        verbose_name_plural = "Butchery Products"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.stock_quantity <= self.reorder_level

    @property
    def is_out_of_stock(self) -> bool:
        return self.stock_quantity <= 0

    @property
    def margin_pct(self) -> float:
        if self.selling_price > 0:
            return float((self.selling_price - self.cost_price) / self.selling_price * 100)
        return 0.0

    @property
    def stock_value(self) -> Decimal:
        return (self.stock_quantity * self.cost_price).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Intake (carcass / live animal purchase)
# ---------------------------------------------------------------------------

class ButcheryIntake(models.Model):
    """
    Records the purchase of a carcass, animal, or bulk meat from a supplier.
    The intake weight and cost are used to allocate cost-per-kg across cuts.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_intakes",
    )
    intake_date = models.DateField(default=timezone.localdate)
    meat_type = models.CharField(max_length=20, choices=MeatType.choices, default=MeatType.BEEF)
    description = models.CharField(max_length=200, blank=True)
    supplier_name = models.CharField(max_length=150, blank=True)
    batch_ref = models.CharField(max_length=60, blank=True)
    storage_location = models.CharField(max_length=120, blank=True)

    # Weight & cost
    intake_weight_kg = models.DecimalField(
        max_digits=12, decimal_places=3,
        help_text="Total weight received in kg",
    )
    total_cost = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Total amount paid for this intake",
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-intake_date", "-created_at"]
        verbose_name = "Butchery Intake"
        verbose_name_plural = "Butchery Intakes"

    def __str__(self):
        return f"{self.get_meat_type_display()} intake {self.intake_weight_kg}kg on {self.intake_date}"

    @property
    def cost_per_kg(self) -> Decimal:
        if self.intake_weight_kg > 0:
            return (self.total_cost / self.intake_weight_kg).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def allocated_kg(self) -> Decimal:
        result = self.allocations.aggregate(
            total=models.Sum("allocated_kg")
        )["total"] or Decimal("0.000")
        return Decimal(str(result))

    @property
    def remaining_kg(self) -> Decimal:
        return max(Decimal("0.000"), self.intake_weight_kg - self.allocated_kg)


# ---------------------------------------------------------------------------
# Intake Allocation (how intake is converted into named cuts)
# ---------------------------------------------------------------------------

class ButcheryIntakeAllocation(models.Model):
    """
    Records how intake weight is allocated to specific cuts.
    e.g. 50 kg beef intake → 10 kg steak, 15 kg mince, 8 kg bones, etc.
    """
    intake = models.ForeignKey(
        ButcheryIntake,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    product = models.ForeignKey(
        ButcheryProduct,
        on_delete=models.CASCADE,
        related_name="intake_allocations",
    )
    allocated_kg = models.DecimalField(max_digits=12, decimal_places=3)
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Intake Allocation"
        verbose_name_plural = "Intake Allocations"

    def __str__(self):
        return f"{self.allocated_kg} kg → {self.product.name}"


# ---------------------------------------------------------------------------
# Processing Batch (guided cutting flow)
# ---------------------------------------------------------------------------

class ButcheryProcessingBatch(models.Model):
    """
    A processing session where raw intake meat is cut into named products.
    Tracks input kg, output by cut, and waste/loss.
    """

    STATUS_DRAFT = "draft"
    STATUS_COMPLETE = "complete"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETE, "Complete"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_processing_batches",
    )
    batch_date = models.DateField(default=timezone.localdate)
    meat_type = models.CharField(max_length=20, choices=MeatType.choices, default=MeatType.BEEF)
    intake = models.ForeignKey(
        ButcheryIntake,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="processing_batches",
    )
    input_kg = models.DecimalField(
        max_digits=12, decimal_places=3,
        help_text="Total kg of raw meat going into processing",
    )
    waste_kg = models.DecimalField(
        max_digits=12, decimal_places=3,
        default=Decimal("0.000"),
        help_text="Loss/waste kg (bones, trimmings not sold, etc.)",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-batch_date", "-created_at"]
        verbose_name = "Processing Batch"
        verbose_name_plural = "Processing Batches"

    def __str__(self):
        return f"Processing {self.get_meat_type_display()} {self.input_kg}kg on {self.batch_date}"

    @property
    def output_kg(self) -> Decimal:
        result = self.lines.aggregate(total=models.Sum("output_kg"))["total"] or Decimal("0.000")
        return Decimal(str(result))

    @property
    def yield_pct(self) -> float:
        if self.input_kg > 0:
            return float(self.output_kg / self.input_kg * 100)
        return 0.0


class ButcheryProcessingLine(models.Model):
    """One cut produced from a processing batch."""
    batch = models.ForeignKey(
        ButcheryProcessingBatch,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        ButcheryProduct,
        on_delete=models.CASCADE,
        related_name="processing_lines",
    )
    output_kg = models.DecimalField(max_digits=12, decimal_places=3)
    cost_per_kg = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Processing Line"
        verbose_name_plural = "Processing Lines"

    def __str__(self):
        return f"{self.output_kg} kg {self.product.name}"


# ---------------------------------------------------------------------------
# Daily Ledger
# ---------------------------------------------------------------------------

class ButcheryDailyLedger(models.Model):
    """
    Tracks the status of a sales day.
    Draft = editable. Locked = finalised; edits require explicit unlock.
    """

    STATUS_DRAFT = "draft"
    STATUS_LOCKED = "locked"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_LOCKED, "Locked"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_daily_ledgers",
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    locked_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("business", "date")]
        ordering = ["-date"]
        verbose_name = "Daily Ledger"
        verbose_name_plural = "Daily Ledgers"

    def __str__(self):
        return f"Ledger {self.date} — {self.get_status_display()}"

    @property
    def is_locked(self) -> bool:
        return self.status == self.STATUS_LOCKED


# ---------------------------------------------------------------------------
# Sale
# ---------------------------------------------------------------------------

class ButcherySale(models.Model):
    """
    A single sale transaction (one product/cut per record; use receipt_ref to group).
    Optionally linked to a daily ledger entry for locking behaviour.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_sales",
    )
    product = models.ForeignKey(
        ButcheryProduct,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    sold_at = models.DateTimeField(default=timezone.now)
    receipt_ref = models.CharField(max_length=30, blank=True)
    sale_date = models.DateField(null=True, blank=True, db_index=True)

    # Quantities & prices
    quantity = models.DecimalField(max_digits=12, decimal_places=3, help_text="Quantity in product unit (kg or pcs)")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    cost_price_snapshot = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Discount
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Payment
    payment_method = models.CharField(
        max_length=20, choices=ButcheryPaymentMethod.choices, default=ButcheryPaymentMethod.CASH
    )
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit_due_date = models.DateField(null=True, blank=True)

    # Customer
    customer_name = models.CharField(max_length=150, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)

    notes = models.TextField(blank=True)
    is_rolled_back = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sold_at"]
        verbose_name = "Butchery Sale"
        verbose_name_plural = "Butchery Sales"

    def __str__(self):
        return f"Sale {self.receipt_ref or self.pk} — {self.product.name}"

    @property
    def total_amount(self) -> Decimal:
        return (self.quantity * self.unit_price - self.discount_amount).quantize(Decimal("0.01"))

    @property
    def profit(self) -> Decimal:
        return (self.total_amount - self.quantity * self.cost_price_snapshot).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if not self.sale_date:
            if self.sold_at:
                from django.utils.timezone import localdate
                self.sale_date = localdate(self.sold_at)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class ButcheryExpense(models.Model):
    CATEGORY_CHOICES = [
        ("supplies", "Supplies & Consumables"),
        ("staff", "Staff / Labour"),
        ("utilities", "Utilities"),
        ("equipment", "Equipment & Maintenance"),
        ("transport", "Transport / Delivery"),
        ("rent", "Rent / Premises"),
        ("other", "Other"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="butchery_expenses",
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    expense_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        verbose_name = "Butchery Expense"
        verbose_name_plural = "Butchery Expenses"

    def __str__(self):
        return f"{self.description} — MWK {self.amount}"
