# inventory/models_welding.py
"""
Welding Manager vertical models.
Tracks materials, quotes, jobs, and estimator learning/tuning.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


User = settings.AUTH_USER_MODEL


# ==============================================================================
# WELDING MATERIALS CATALOG
# ==============================================================================


class WeldingMaterialCategory(models.TextChoices):
    """Categories for welding materials - split for clarity"""
    # Structural Steel
    TUBE = "tube", "Tubes (Square/Round)"
    FLAT_BAR = "flat_bar", "Flat Bar"
    ANGLE_IRON = "angle_iron", "Angle Iron"
    SHEET = "sheet", "Sheet Metal"
    # Boards & Panels
    BOARD = "board", "Boards & Panels"
    ALUMINUM = "aluminum", "Aluminum Profiles"
    # Consumables (split)
    ELECTRODE = "electrode", "Electrodes"
    DISC = "disc", "Discs (Cutting/Grinding)"
    SANDING = "sanding", "Sanding Discs"
    # Finishes
    PAINT = "paint", "Paint & Finishes"
    # Hardware
    HARDWARE = "hardware", "Hardware"
    # Other
    OTHER = "other", "Other"


class WeldingMaterialUnit(models.TextChoices):
    """Unit types for welding materials"""
    LENGTH_6M = "length_6m", "6m Length"
    LENGTH_5_8M = "length_5_8m", "5.8m Length"
    METRE = "metre", "Metre"
    LITRE = "litre", "Litre"
    PIECE = "piece", "Piece"
    KG = "kg", "Kilogram"
    PACKET = "packet", "Packet"
    SHEET = "sheet", "Sheet (2.4x1.2m)"
    BOARD = "board", "Board (8ft x 4ft)"


class WeldingMaterial(models.Model):
    """
    Catalog of welding materials with pricing.
    Seeded with common materials but user can add/edit.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="welding_materials",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="welding_materials",
    )
    
    # Material identification
    name = models.CharField(
        max_length=150,
        help_text="e.g. 'Square Tube 40x40 (6m)', 'Red Oxide 5L'",
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Optional SKU/code for quick reference",
    )
    category = models.CharField(
        max_length=20,
        choices=WeldingMaterialCategory.choices,
        default=WeldingMaterialCategory.OTHER,
        db_index=True,
    )
    unit = models.CharField(
        max_length=20,
        choices=WeldingMaterialUnit.choices,
        default=WeldingMaterialUnit.PIECE,
    )
    
    # Specifications (optional, for filtering)
    specifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON with specs like {thickness: 1.5, width: 40, height: 40}",
    )
    
    # Barcode support
    has_barcode = models.BooleanField(default=False)
    barcode = models.CharField(max_length=50, blank=True, default="")
    
    # Pricing
    price_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Current price per unit in MWK",
    )
    
    # Stock tracking (optional, simple count)
    quantity_in_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    low_stock_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    
    # System flags
    is_seeded = models.BooleanField(
        default=False,
        help_text="True if this was created by system seeding",
    )
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["business", "category"]),
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "barcode"]),
        ]
        unique_together = [("business", "code")]
        verbose_name = "Welding Material"
        verbose_name_plural = "Welding Materials"
    
    def __str__(self):
        return f"{self.name} @ {self.price_mwk} MWK/{self.get_unit_display()}"
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below threshold."""
        if self.low_stock_threshold is None:
            return False
        return self.quantity_in_stock <= self.low_stock_threshold


class WeldingMaterialStockMove(models.Model):
    """
    Records stock movements for welding materials.
    Supports stock-in (purchases), stock-out (usage), and adjustments.
    """
    
    class MoveType(models.TextChoices):
        IN = "in", "Stock In (Purchase)"
        OUT = "out", "Stock Out (Usage)"
        ADJUST = "adjust", "Adjustment"
    
    material = models.ForeignKey(
        WeldingMaterial,
        on_delete=models.CASCADE,
        related_name="stock_moves",
    )
    
    move_type = models.CharField(
        max_length=10,
        choices=MoveType.choices,
        db_index=True,
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_cost_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Purchase cost per unit (for IN moves)",
    )
    
    # Reference to job that consumed material
    job = models.ForeignKey(
        "WeldingJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="material_usage",
    )
    
    date = models.DateField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welding_stock_moves_created",
    )
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["material", "-date"]),
            models.Index(fields=["material", "move_type"]),
        ]
        verbose_name = "Welding Material Stock Move"
        verbose_name_plural = "Welding Material Stock Moves"
    
    def __str__(self):
        return f"{self.get_move_type_display()}: {self.quantity} of {self.material.name}"
    
    @property
    def total_cost_mwk(self) -> Decimal | None:
        """Calculate total cost for IN moves."""
        if self.unit_cost_mwk:
            return self.quantity * self.unit_cost_mwk
        return None


# ==============================================================================
# PRODUCT TEMPLATES
# ==============================================================================


class WeldingTemplate(models.Model):
    """
    Product templates for common welded items.
    Contains base BOM formulas and configurable parameters.
    """
    # Global templates (business=null) or business-specific
    business = models.ForeignKey(
        Business,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="welding_templates",
    )
    
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Template code, e.g. 'BED_4x6', 'DOOR_STANDARD'",
    )
    name = models.CharField(
        max_length=150,
        help_text="Display name, e.g. 'Bed Frame (4ft x 6ft)'",
    )
    description = models.TextField(blank=True, default="")
    
    # Parameters schema (JSON) - defines what inputs user must provide
    params_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text='JSON schema for required params, e.g. {"width": "number", "height": "number"}',
    )
    
    # Base BOM formula (JSON) - defines material requirements
    base_bom = models.JSONField(
        default=dict,
        help_text="Base BOM formulas keyed by material code/category",
    )
    
    # Default pricing parameters
    default_labour_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    default_overhead_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Default overhead/wastage percentage",
    )
    default_margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("25.0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Default profit margin percentage",
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
        verbose_name = "Welding Template"
        verbose_name_plural = "Welding Templates"
    
    def __str__(self):
        return f"{self.code}: {self.name}"


# ==============================================================================
# QUOTES & JOBS
# ==============================================================================


class WeldingQuoteStatus(models.TextChoices):
    """Quote lifecycle status"""
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent to Customer"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"


class WeldingQuote(models.Model):
    """
    Quote/estimate for a welding job.
    Generated from templates with customizations.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="welding_quotes",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="welding_quotes",
    )
    
    # Quote number
    quote_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Auto-generated or manual quote number",
    )
    
    # Customer
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_email = models.CharField(max_length=254, blank=True, default="")
    
    # Template reference (may be null for custom quotes)
    template = models.ForeignKey(
        WeldingTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotes",
    )
    
    # Customized specs (snapshot of user inputs)
    specs = models.JSONField(
        default=dict,
        help_text="User-provided specifications for this quote",
    )
    
    # Generated BOM (snapshot at quote time)
    bom = models.JSONField(
        default=list,
        help_text="Generated bill of materials",
    )
    
    # Cost breakdown (snapshot)
    cost_breakdown = models.JSONField(
        default=dict,
        help_text="Detailed cost breakdown",
    )
    
    # Totals
    materials_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    labour_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    overhead_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    
    # Min price (break-even)
    min_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Minimum acceptable price (break-even)",
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=WeldingQuoteStatus.choices,
        default=WeldingQuoteStatus.DRAFT,
        db_index=True,
    )
    valid_until = models.DateField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    terms = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welding_quotes_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "customer_phone"]),
        ]
        verbose_name = "Welding Quote"
        verbose_name_plural = "Welding Quotes"
    
    def __str__(self):
        return f"Quote {self.quote_number or self.pk} - {self.customer_name}"
    
    def save(self, *args, **kwargs):
        if not self.quote_number:
            # Auto-generate quote number
            self.quote_number = f"WQ-{timezone.now().strftime('%Y%m%d')}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)
        # Update quote number with actual PK if it was NEW
        if "NEW" in self.quote_number:
            self.quote_number = f"WQ-{timezone.now().strftime('%Y%m%d')}-{self.pk}"
            super().save(update_fields=["quote_number"])
    
    @property
    def computed_total(self) -> Decimal:
        """Compute total from line items + costs dynamically."""
        materials_total = sum(
            (item.line_total for item in self.line_items.all()),
            Decimal("0")
        )
        labour_total = self.costs.filter(cost_type="labour").aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")
        transport_total = self.costs.filter(cost_type="transport").aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")
        other_total = self.costs.filter(cost_type="other").aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")
        profit_total = self.costs.filter(cost_type="profit").aggregate(
            models.Sum("amount")
        )["amount__sum"] or Decimal("0")
        
        return materials_total + labour_total + transport_total + other_total + profit_total


class WeldingQuoteLineItem(models.Model):
    """
    Individual line item in a quote - manually added by manager.
    Replaces auto-generated BOM approach with manager-driven selection.
    """
    quote = models.ForeignKey(
        WeldingQuote,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    material = models.ForeignKey(
        WeldingMaterial,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Reference to material (optional, snapshots name/unit)",
    )
    
    # Snapshot fields (so quote is immutable even if material changes)
    material_name = models.CharField(max_length=150)
    material_unit = models.CharField(max_length=20, default="piece")
    
    # Quantity and pricing (manager enters these manually)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Unit price in MWK - left blank until manager enters",
    )
    
    # Notes
    notes = models.CharField(max_length=255, blank=True, default="")
    
    # Position for ordering
    position = models.PositiveIntegerField(default=0)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["position", "created_at"]
        indexes = [
            models.Index(fields=["quote", "position"]),
        ]
        verbose_name = "Welding Quote Line Item"
        verbose_name_plural = "Welding Quote Line Items"
    
    def __str__(self):
        return f"{self.material_name} x {self.quantity} @ {self.unit_price or 'TBD'}"
    
    @property
    def line_total(self) -> Decimal:
        """Calculate line total."""
        if self.unit_price is None:
            return Decimal("0")
        return self.quantity * self.unit_price


class WeldingQuoteCost(models.Model):
    """
    Additional costs for a quote (labour, transport, other, profit).
    Manager adds these manually.
    """
    
    class CostType(models.TextChoices):
        LABOUR = "labour", "Labour"
        TRANSPORT = "transport", "Transport"
        OTHER = "other", "Other"
        PROFIT = "profit", "Profit/Markup"
    
    quote = models.ForeignKey(
        WeldingQuote,
        on_delete=models.CASCADE,
        related_name="costs",
    )
    cost_type = models.CharField(
        max_length=20,
        choices=CostType.choices,
        db_index=True,
    )
    description = models.CharField(max_length=150, blank=True, default="")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.CharField(max_length=255, blank=True, default="")
    
    # Position for ordering
    position = models.PositiveIntegerField(default=0)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["cost_type", "position", "created_at"]
        indexes = [
            models.Index(fields=["quote", "cost_type"]),
        ]
        verbose_name = "Welding Quote Cost"
        verbose_name_plural = "Welding Quote Costs"
    
    def __str__(self):
        desc = f" - {self.description}" if self.description else ""
        return f"{self.get_cost_type_display()}{desc}: MWK {self.amount:,.0f}"


class WeldingJobStatus(models.TextChoices):
    """Job lifecycle status"""
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    READY = "ready", "Ready for Pickup"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class WeldingJob(models.Model):
    """
    Tracks execution of a welding job.
    May be linked to a quote or created directly.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="welding_jobs",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="welding_jobs",
    )
    
    # Job number
    job_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Auto-generated or manual job number",
    )
    
    # Source quote (optional)
    quote = models.ForeignKey(
        WeldingQuote,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
    )
    
    # Customer (copied from quote or entered directly)
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    
    # Template/product info
    template = models.ForeignKey(
        WeldingTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    product_description = models.CharField(max_length=255, blank=True, default="")
    
    # Estimated vs Actual BOM
    estimated_bom = models.JSONField(
        default=list,
        help_text="BOM from quote/estimate",
    )
    actual_bom = models.JSONField(
        default=list,
        help_text="Actual materials used (updated after completion)",
    )
    
    # Labour
    estimated_labour_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
    )
    actual_labour_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    
    # Pricing
    quoted_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=WeldingJobStatus.choices,
        default=WeldingJobStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    correction_reason = models.TextField(
        blank=True,
        default="",
        help_text="Reason for BOM/labour corrections (for learning)",
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welding_jobs_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "status"]),
        ]
        verbose_name = "Welding Job"
        verbose_name_plural = "Welding Jobs"
    
    def __str__(self):
        return f"Job {self.job_number or self.pk} - {self.customer_name}"
    
    def save(self, *args, **kwargs):
        if not self.job_number:
            self.job_number = f"WJ-{timezone.now().strftime('%Y%m%d')}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)
        if "NEW" in self.job_number:
            self.job_number = f"WJ-{timezone.now().strftime('%Y%m%d')}-{self.pk}"
            super().save(update_fields=["job_number"])


# ==============================================================================
# ESTIMATOR TUNING (LEARNING)
# ==============================================================================


class WeldingEstimatorTuning(models.Model):
    """
    Per-template tuning multipliers for improving estimates.
    Updated based on actual vs estimated comparisons.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="welding_tuning",
    )
    template = models.ForeignKey(
        WeldingTemplate,
        on_delete=models.CASCADE,
        related_name="tuning",
    )
    
    # Multipliers (bounded: 0.5 to 2.0 to prevent wild swings)
    tube_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("2.0"))],
    )
    paint_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("2.0"))],
    )
    consumable_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("2.0"))],
    )
    labour_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("2.0"))],
    )
    
    # Learning stats
    samples_count = models.PositiveIntegerField(default=0)
    last_updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [("business", "template")]
        verbose_name = "Welding Estimator Tuning"
        verbose_name_plural = "Welding Estimator Tunings"
    
    def __str__(self):
        return f"Tuning for {self.template.code} @ {self.business.name}"


# ==============================================================================
# INVOICES (Simple, reuses quote data)
# ==============================================================================


class WeldingInvoiceStatus(models.TextChoices):
    """Invoice status"""
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    PAID = "paid", "Paid"
    PARTIAL = "partial", "Partially Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class WeldingInvoice(models.Model):
    """
    Invoice generated from a quote or job.
    Keeps a snapshot of all financial details.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="welding_invoices",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="welding_invoices",
    )
    
    # Invoice number
    invoice_number = models.CharField(max_length=50, blank=True)
    
    # Source
    quote = models.ForeignKey(
        WeldingQuote,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    job = models.ForeignKey(
        WeldingJob,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    
    # Customer
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_email = models.CharField(max_length=254, blank=True, default="")
    customer_address = models.TextField(blank=True, default="")
    
    # Line items (snapshot)
    line_items = models.JSONField(
        default=list,
        help_text="Invoice line items",
    )
    
    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=WeldingInvoiceStatus.choices,
        default=WeldingInvoiceStatus.DRAFT,
        db_index=True,
    )
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    terms = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="welding_invoices_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "status"]),
        ]
        verbose_name = "Welding Invoice"
        verbose_name_plural = "Welding Invoices"
    
    def __str__(self):
        return f"Invoice {self.invoice_number or self.pk} - {self.customer_name}"
    
    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid
    
    @property
    def is_paid(self) -> bool:
        return self.balance_due <= Decimal("0")
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"WI-{timezone.now().strftime('%Y%m%d')}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)
        if "NEW" in self.invoice_number:
            self.invoice_number = f"WI-{timezone.now().strftime('%Y%m%d')}-{self.pk}"
            super().save(update_fields=["invoice_number"])

