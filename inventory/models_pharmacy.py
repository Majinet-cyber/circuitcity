# inventory/models_pharmacy.py
"""
Pharmacy-specific models for batch tracking, expiry management, and sales.
Premium, business-aware features for pharmacy vertical.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ==============================================================================
# ENUMS
# ==============================================================================

class PharmacyProductForm(models.TextChoices):
    """Pharmaceutical forms"""
    TABLET = "tablet", "Tablet"
    CAPSULE = "capsule", "Capsule"
    SYRUP = "syrup", "Syrup"
    SUSPENSION = "suspension", "Suspension"
    INJECTION = "injection", "Injection"
    CREAM = "cream", "Cream"
    OINTMENT = "ointment", "Ointment"
    DROPS = "drops", "Drops"
    INHALER = "inhaler", "Inhaler"
    POWDER = "powder", "Powder"
    OTHER = "other", "Other"


class PharmacyCategory(models.TextChoices):
    """Drug categories"""
    ANALGESIC = "analgesic", "Analgesic (Pain Relief)"
    ANTIBIOTIC = "antibiotic", "Antibiotic"
    ANTIFUNGAL = "antifungal", "Antifungal"
    ANTIVIRAL = "antiviral", "Antiviral"
    ANTIHISTAMINE = "antihistamine", "Antihistamine"
    ANTIPYRETIC = "antipyretic", "Antipyretic (Fever)"
    ANTIHYPERTENSIVE = "antihypertensive", "Antihypertensive (Blood Pressure)"
    ANTIDIABETIC = "antidiabetic", "Antidiabetic"
    VITAMIN = "vitamin", "Vitamin/Supplement"
    ANTIPARASITIC = "antiparasitic", "Antiparasitic"
    RESPIRATORY = "respiratory", "Respiratory"
    GASTROINTESTINAL = "gastrointestinal", "Gastrointestinal"
    DERMATOLOGICAL = "dermatological", "Dermatological"
    CONTRACEPTIVE = "contraceptive", "Contraceptive"
    OTHER = "other", "Other"


# ==============================================================================
# PHARMACY PRODUCT (extends base MerchProduct concept)
# ==============================================================================

class PharmacyProductInfo(models.Model):
    """
    Extended info for pharmacy products (1-to-1 with MerchProduct where kind=PHARMACY).
    This allows us to add pharmacy-specific fields without cluttering the base model.
    """
    merch_product = models.OneToOneField(
        "inventory.MerchProduct",
        on_delete=models.CASCADE,
        related_name="pharmacy_info",
        help_text="Base product reference"
    )
    
    # Pharmaceutical details
    strength = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="e.g. 500mg, 10ml, 250mg/5ml"
    )
    form = models.CharField(
        max_length=20,
        choices=PharmacyProductForm.choices,
        default=PharmacyProductForm.TABLET,
        help_text="Dosage form"
    )
    category = models.CharField(
        max_length=30,
        choices=PharmacyCategory.choices,
        blank=True,
        default="",
        help_text="Drug category"
    )
    
    # Prescription requirement
    requires_prescription = models.BooleanField(
        default=False,
        help_text="True if this drug requires a prescription"
    )
    
    # Generic vs Brand
    is_generic = models.BooleanField(
        default=False,
        help_text="True if this is a generic (non-branded) drug"
    )
    active_ingredient = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Active pharmaceutical ingredient (API)"
    )
    
    # Storage requirements
    storage_notes = models.TextField(
        blank=True,
        default="",
        help_text="Special storage requirements (e.g. refrigerate, keep dry)"
    )
    
    class Meta:
        verbose_name = "Pharmacy Product Info"
        verbose_name_plural = "Pharmacy Product Info"
    
    def __str__(self):
        return f"{self.merch_product.name} ({self.strength})"


# ==============================================================================
# PHARMACY BATCH (expiry tracking, FIFO)
# ==============================================================================

class PharmacyBatch(models.Model):
    """
    Batch-level tracking for pharmacy products with expiry dates.
    Essential for FIFO (first-in-first-out) and expiry management.
    """
    merch_product = models.ForeignKey(
        "inventory.MerchProduct",
        on_delete=models.CASCADE,
        related_name="pharmacy_batches",
        help_text="Product this batch belongs to"
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="pharmacy_batches"
    )
    
    # Batch identification
    batch_number = models.CharField(
        max_length=100,
        help_text="Manufacturer batch/lot number"
    )
    expiry_date = models.DateField(
        db_index=True,
        help_text="Expiry date (day/month/year)"
    )
    
    # Stock levels
    quantity = models.PositiveIntegerField(
        default=0,
        help_text="Current quantity in stock"
    )
    reorder_level = models.PositiveIntegerField(
        default=10,
        help_text="Alert when stock drops to or below this level"
    )
    
    # Pricing
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost per unit"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit"
    )
    
    # Supplier info
    supplier = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Supplier name"
    )
    
    # Timestamps
    received_date = models.DateField(
        default=timezone.now,
        help_text="Date batch was received"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Archive (for depleted or expired batches)
    is_archived = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        ordering = ["expiry_date", "batch_number"]  # FIFO: oldest expiry first
        indexes = [
            models.Index(fields=["business", "merch_product", "expiry_date"]),
            models.Index(fields=["business", "expiry_date"]),
            models.Index(fields=["is_archived"]),
        ]
        unique_together = ("business", "merch_product", "batch_number", "expiry_date")
        verbose_name = "Pharmacy Batch"
        verbose_name_plural = "Pharmacy Batches"
    
    def __str__(self):
        return f"{self.merch_product.name} - Batch {self.batch_number} (Exp: {self.expiry_date})"
    
    @property
    def is_expired(self) -> bool:
        """Check if batch has expired."""
        return self.expiry_date < timezone.now().date()
    
    @property
    def days_to_expiry(self) -> int:
        """Days until expiry (negative if already expired)."""
        delta = self.expiry_date - timezone.now().date()
        return delta.days
    
    @property
    def is_near_expiry(self, days: int = 30) -> bool:
        """Check if batch expires within the next N days."""
        return 0 <= self.days_to_expiry <= days
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is at or below reorder level."""
        return self.quantity <= self.reorder_level
    
    @property
    def stock_value_cost(self) -> Decimal:
        """Total value at cost price."""
        return Decimal(self.quantity) * self.cost_price
    
    @property
    def stock_value_selling(self) -> Decimal:
        """Total value at selling price."""
        return Decimal(self.quantity) * self.selling_price
    
    def decrement_stock(self, qty: int) -> None:
        """Decrement stock by quantity (for sales)."""
        if qty > self.quantity:
            raise ValueError(f"Insufficient stock: requested {qty}, available {self.quantity}")
        self.quantity -= qty
        self.save(update_fields=["quantity", "updated_at"])
        
        # Auto-archive if depleted
        if self.quantity == 0 and not self.is_archived:
            self.is_archived = True
            self.save(update_fields=["is_archived", "updated_at"])


# ==============================================================================
# PHARMACY SALE
# ==============================================================================

class PharmacySale(models.Model):
    """
    Records individual pharmacy sales with batch tracking.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="pharmacy_sales"
    )
    batch = models.ForeignKey(
        PharmacyBatch,
        on_delete=models.PROTECT,
        related_name="sales",
        help_text="Batch sold from"
    )
    
    # Sale details
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantity sold"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit"
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost price per unit (for profit calculation)"
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total sale amount (quantity * unit_price)"
    )
    
    # Payment
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("BANK", "Bank Transfer"),
        ("CREDIT", "Credit"),
    ]
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="CASH"
    )
    
    # Customer (optional)
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Customer name (optional)"
    )
    customer_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Customer phone (optional)"
    )
    
    # Prescription (if required)
    prescription_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Prescription reference (if applicable)"
    )
    
    # Who made the sale
    sold_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pharmacy_sales"
    )
    
    # Timestamps
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    class Meta:
        ordering = ["-sold_at"]
        indexes = [
            models.Index(fields=["business", "-sold_at"]),
            models.Index(fields=["batch", "-sold_at"]),
            models.Index(fields=["sold_by", "-sold_at"]),
        ]
        verbose_name = "Pharmacy Sale"
        verbose_name_plural = "Pharmacy Sales"
    
    def __str__(self):
        product_name = self.batch.merch_product.name
        return f"{product_name} x{self.quantity} @ {self.sold_at:%Y-%m-%d %H:%M}"
    
    @property
    def profit(self) -> Decimal:
        """Calculate profit for this sale."""
        total_cost = self.unit_cost * Decimal(self.quantity)
        return self.total_amount - total_cost
    
    def save(self, *args, **kwargs):
        # Auto-calculate total_amount
        self.total_amount = self.unit_price * Decimal(self.quantity)
        super().save(*args, **kwargs)


# ==============================================================================
# HELPER QUERYSETS / MANAGERS
# ==============================================================================

class PharmacyBatchQuerySet(models.QuerySet):
    """Custom queryset for common pharmacy batch queries."""
    
    def active(self):
        """Non-archived batches."""
        return self.filter(is_archived=False)
    
    def expired(self):
        """Batches past expiry date."""
        return self.filter(expiry_date__lt=timezone.now().date())
    
    def near_expiry(self, days: int = 30):
        """Batches expiring within N days."""
        today = timezone.now().date()
        future = today + timedelta(days=days)
        return self.filter(expiry_date__gte=today, expiry_date__lte=future)
    
    def low_stock(self):
        """Batches at or below reorder level."""
        return self.filter(quantity__lte=models.F("reorder_level"))
    
    def in_stock(self):
        """Batches with quantity > 0."""
        return self.filter(quantity__gt=0)


# Attach custom manager
PharmacyBatch.objects = PharmacyBatchQuerySet.as_manager()

