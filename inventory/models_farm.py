# inventory/models_farm.py
"""
Farm Manager vertical models.
Tracks ledger entries, livestock batches, events, and crop seasons.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


User = settings.AUTH_USER_MODEL


# ==============================================================================
# FARM LEDGER
# ==============================================================================


class FarmEntryType(models.TextChoices):
    """Type of ledger entry"""
    EXPENSE = "expense", "Expense"
    SALE = "sale", "Sale"
    OTHER_INCOME = "other_income", "Other Income"


class FarmEnterpriseType(models.TextChoices):
    """Type of farm enterprise/activity"""
    LIVESTOCK = "livestock", "Livestock"
    CROP = "crop", "Crop"
    GENERAL = "general", "General"
    PIGS = "pigs", "Pigs"
    CATTLE = "cattle", "Cattle"
    GOATS = "goats", "Goats"
    CHICKENS = "chickens", "Chickens"
    MAIZE = "maize", "Maize"
    SOYA = "soya", "Soya"
    GROUNDNUTS = "groundnuts", "Groundnuts"
    TOBACCO = "tobacco", "Tobacco"


class FarmExpenseCategory(models.TextChoices):
    """Common expense categories for farms"""
    FERTILISER = "fertiliser", "Fertiliser"
    FEED = "feed", "Animal Feed"
    LABOUR = "labour", "Labour"
    VET = "vet", "Veterinary Services"
    TRANSPORT = "transport", "Transport"
    RENTALS = "rentals", "Equipment Rentals"
    SEEDS = "seeds", "Seeds & Seedlings"
    CHEMICALS = "chemicals", "Pesticides & Chemicals"
    EQUIPMENT = "equipment", "Equipment Purchase"
    FUEL = "fuel", "Fuel & Diesel"
    UTILITIES = "utilities", "Utilities (Water/Electricity)"
    OTHER = "other", "Other"


class FarmUnit(models.TextChoices):
    """Unit types for farm transactions"""
    KG = "kg", "Kilogram"
    BAG = "bag", "Bag (50kg)"
    LITRE = "litre", "Litre"
    DAY = "day", "Day"
    ITEM = "item", "Item/Piece"
    HEAD = "head", "Head (Animal)"
    ACRE = "acre", "Acre"
    HA = "ha", "Hectare"


class FarmPaymentMethod(models.TextChoices):
    """Payment methods"""
    CASH = "cash", "Cash"
    BANK = "bank", "Bank Transfer"
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    CREDIT = "credit", "Credit/On Account"
    BARTER = "barter", "Barter/Exchange"


class FarmLedgerEntry(models.Model):
    """
    Core ledger entry for tracking farm income and expenses.
    This is the primary table for farm profitability analysis.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_ledger_entries",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="farm_ledger_entries",
    )
    
    # Entry details
    date = models.DateField(default=timezone.now, db_index=True)
    entry_type = models.CharField(
        max_length=20,
        choices=FarmEntryType.choices,
        default=FarmEntryType.EXPENSE,
        db_index=True,
    )
    enterprise_type = models.CharField(
        max_length=20,
        choices=FarmEnterpriseType.choices,
        default=FarmEnterpriseType.GENERAL,
        db_index=True,
    )
    category = models.CharField(
        max_length=50,
        choices=FarmExpenseCategory.choices,
        default=FarmExpenseCategory.OTHER,
    )
    description = models.CharField(max_length=255, blank=True, default="")
    
    # Financial details
    amount_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Amount in MWK (Malawian Kwacha)",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField(
        max_length=20,
        choices=FarmUnit.choices,
        default=FarmUnit.ITEM,
        blank=True,
    )
    payment_method = models.CharField(
        max_length=20,
        choices=FarmPaymentMethod.choices,
        default=FarmPaymentMethod.CASH,
    )
    
    # Optional linked season for crop entries
    crop_season = models.ForeignKey(
        "FarmCropSeason",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    
    # Optional linked livestock batch
    livestock_batch = models.ForeignKey(
        "FarmLivestockBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    
    # Audit fields
    notes = models.TextField(blank=True, default="")
    attachment = models.FileField(
        upload_to="farm/ledger/attachments/%Y/%m/",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_ledger_entries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-date"]),
            models.Index(fields=["business", "entry_type", "-date"]),
            models.Index(fields=["business", "enterprise_type", "-date"]),
        ]
        verbose_name = "Farm Ledger Entry"
        verbose_name_plural = "Farm Ledger Entries"
    
    def __str__(self):
        return f"{self.get_entry_type_display()} - {self.amount_mwk} MWK ({self.date})"
    
    @property
    def is_expense(self) -> bool:
        return self.entry_type == FarmEntryType.EXPENSE
    
    @property
    def is_income(self) -> bool:
        return self.entry_type in (FarmEntryType.SALE, FarmEntryType.OTHER_INCOME)
    
    @property
    def signed_amount(self) -> Decimal:
        """Return positive for income, negative for expense (for summation)."""
        if self.is_expense:
            return -self.amount_mwk
        return self.amount_mwk


# ==============================================================================
# LIVESTOCK MANAGEMENT
# ==============================================================================


class FarmAnimalType(models.TextChoices):
    """Types of livestock animals"""
    PIGS = "pigs", "Pigs"
    CATTLE = "cattle", "Cattle"
    GOATS = "goats", "Goats"
    CHICKENS = "chickens", "Chickens"
    DUCKS = "ducks", "Ducks"
    RABBITS = "rabbits", "Rabbits"
    SHEEP = "sheep", "Sheep"
    FISH = "fish", "Fish"
    OTHER = "other", "Other"


class FarmLivestockBatch(models.Model):
    """
    Tracks a batch/group of livestock animals.
    Counts are updated based on FarmLivestockEvent entries.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_livestock_batches",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="farm_livestock_batches",
    )
    
    # Batch identification
    animal_type = models.CharField(
        max_length=20,
        choices=FarmAnimalType.choices,
        default=FarmAnimalType.PIGS,
        db_index=True,
    )
    name = models.CharField(
        max_length=100,
        help_text="Batch name, e.g. 'Gilts Batch 1', 'Layer Chickens Group A'",
    )
    
    # Current state (updated from events)
    count_current = models.PositiveIntegerField(
        default=0,
        help_text="Current count of animals in this batch",
    )
    
    # Valuation settings (optional)
    valuation_enabled = models.BooleanField(
        default=False,
        help_text="Enable estimated valuation for this batch",
    )
    avg_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Average weight per animal in kg",
    )
    price_per_kg_mwk = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Price per kg for valuation",
    )
    price_per_animal_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Fixed price per animal for valuation",
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_livestock_batches_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "animal_type"]),
            models.Index(fields=["business", "is_active"]),
        ]
        verbose_name = "Farm Livestock Batch"
        verbose_name_plural = "Farm Livestock Batches"
    
    def __str__(self):
        return f"{self.name} ({self.get_animal_type_display()}) - {self.count_current} head"
    
    @property
    def estimated_value_mwk(self) -> Decimal | None:
        """Calculate estimated batch value if valuation is enabled."""
        if not self.valuation_enabled or self.count_current == 0:
            return None
        
        # Prefer per-animal pricing if set
        if self.price_per_animal_mwk:
            return self.count_current * self.price_per_animal_mwk
        
        # Otherwise use per-kg pricing
        if self.price_per_kg_mwk and self.avg_weight_kg:
            return self.count_current * self.avg_weight_kg * self.price_per_kg_mwk
        
        return None


class FarmLivestockEventType(models.TextChoices):
    """Types of livestock events that affect count"""
    BIRTH = "birth", "Birth"
    DEATH = "death", "Death"
    PURCHASE = "purchase", "Purchase"
    SALE = "sale", "Sale"
    TRANSFER_IN = "transfer_in", "Transfer In"
    TRANSFER_OUT = "transfer_out", "Transfer Out"
    SLAUGHTER = "slaughter", "Slaughter"


class FarmLivestockEvent(models.Model):
    """
    Records events that change livestock batch counts.
    Each event updates the parent batch's count_current.
    """
    batch = models.ForeignKey(
        FarmLivestockBatch,
        on_delete=models.CASCADE,
        related_name="events",
    )
    
    # Event details
    event_type = models.CharField(
        max_length=20,
        choices=FarmLivestockEventType.choices,
        db_index=True,
    )
    date = models.DateField(default=timezone.now, db_index=True)
    count = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Number of animals affected",
    )
    
    # Financial details (for purchase/sale)
    unit_price_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Price per animal for purchases/sales",
    )
    
    # Transfer details
    transfer_batch = models.ForeignKey(
        FarmLivestockBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transfers_to",
        help_text="Target batch for transfers",
    )
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_livestock_events_created",
    )
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["batch", "-date"]),
            models.Index(fields=["batch", "event_type"]),
        ]
        verbose_name = "Farm Livestock Event"
        verbose_name_plural = "Farm Livestock Events"
    
    def __str__(self):
        return f"{self.get_event_type_display()}: {self.count} ({self.date})"
    
    @property
    def count_delta(self) -> int:
        """
        Return the signed count change for this event.
        Positive = adds animals, Negative = removes animals.
        """
        if self.event_type in (
            FarmLivestockEventType.BIRTH,
            FarmLivestockEventType.PURCHASE,
            FarmLivestockEventType.TRANSFER_IN,
        ):
            return self.count
        return -self.count
    
    @property
    def total_value_mwk(self) -> Decimal | None:
        """Calculate total value for purchases/sales."""
        if self.unit_price_mwk:
            return self.count * self.unit_price_mwk
        return None


# ==============================================================================
# CROP SEASONS
# ==============================================================================


class FarmCropType(models.TextChoices):
    """Common crop types"""
    MAIZE = "maize", "Maize"
    SOYA = "soya", "Soya Beans"
    GROUNDNUTS = "groundnuts", "Groundnuts"
    TOBACCO = "tobacco", "Tobacco"
    COTTON = "cotton", "Cotton"
    RICE = "rice", "Rice"
    BEANS = "beans", "Beans"
    CASSAVA = "cassava", "Cassava"
    SWEET_POTATO = "sweet_potato", "Sweet Potato"
    VEGETABLES = "vegetables", "Vegetables"
    OTHER = "other", "Other"


class FarmSeasonStatus(models.TextChoices):
    """Status of a crop season"""
    PLANNING = "planning", "Planning"
    ACTIVE = "active", "Active (Growing)"
    HARVESTED = "harvested", "Harvested"
    CLOSED = "closed", "Closed"


class FarmCropSeason(models.Model):
    """
    Tracks a single crop season with planned vs actual metrics.
    Links to ledger entries for cost/income tracking.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_crop_seasons",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="farm_crop_seasons",
    )
    
    # Season identification
    crop_type = models.CharField(
        max_length=20,
        choices=FarmCropType.choices,
        default=FarmCropType.MAIZE,
        db_index=True,
    )
    name = models.CharField(
        max_length=100,
        help_text="Season name, e.g. 'Maize 2026 Main Season'",
    )
    
    # Timing
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Area
    area_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Area planted",
    )
    area_unit = models.CharField(
        max_length=10,
        choices=[(u.value, u.label) for u in FarmUnit if u in (FarmUnit.ACRE, FarmUnit.HA)],
        default=FarmUnit.ACRE,
    )
    
    # Projections
    projected_yield = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Expected yield (total)",
    )
    yield_unit = models.CharField(
        max_length=10,
        choices=[(u.value, u.label) for u in FarmUnit if u in (FarmUnit.BAG, FarmUnit.KG)],
        default=FarmUnit.BAG,
        blank=True,
    )
    projected_price_per_unit_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Expected selling price per yield unit",
    )
    
    # Actual results (updated after harvest/sales)
    actual_yield = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    actual_price_per_unit_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=FarmSeasonStatus.choices,
        default=FarmSeasonStatus.PLANNING,
        db_index=True,
    )
    
    # Audit
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_crop_seasons_created",
    )
    
    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["business", "-start_date"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "crop_type"]),
        ]
        verbose_name = "Farm Crop Season"
        verbose_name_plural = "Farm Crop Seasons"
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    @property
    def projected_income_mwk(self) -> Decimal | None:
        """Calculate projected total income."""
        if self.projected_yield and self.projected_price_per_unit_mwk:
            return self.projected_yield * self.projected_price_per_unit_mwk
        return None
    
    @property
    def actual_income_mwk(self) -> Decimal | None:
        """Calculate actual income from sales."""
        if self.actual_yield and self.actual_price_per_unit_mwk:
            return self.actual_yield * self.actual_price_per_unit_mwk
        return None

