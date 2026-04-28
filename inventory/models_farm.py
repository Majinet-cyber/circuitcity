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


class FarmLivestockSubType(models.TextChoices):
    """Practical subtypes for batches — quick-picks in the UI, not free-text only."""

    UNSPECIFIED = "unspecified", "Select subtype (use quick-picks below)"
    CHICKEN_BROILERS = "chicken_broilers", "Broilers"
    CHICKEN_LAYERS = "chicken_layers", "Layers"
    CHICKEN_INDIGENOUS = "chicken_indigenous", "Indigenous / local chickens"
    CHICKEN_HYBRID = "chicken_hybrid", "Hybrid chickens"
    CHICKEN_CHICKS = "chicken_chicks", "Chicks"
    CHICKEN_POL = "chicken_point_of_lay", "Point-of-lay birds"
    PIG_LOCAL = "pig_local", "Local pigs"
    PIG_HYBRID = "pig_hybrid", "Hybrid / improved pigs"
    PIG_PIGLETS = "pig_piglets", "Piglets"
    PIG_GROWERS = "pig_growers", "Growers / fattening"
    PIG_SOWS = "pig_sows", "Sows"
    PIG_BOARS = "pig_boars", "Boars"
    GOAT_LOCAL = "goat_local", "Local goats"
    GOAT_BOER = "goat_boer", "Boer / improved breeds"
    GOAT_KIDS = "goat_kids", "Kids (young goats)"
    GOAT_BREEDING_MALE = "goat_breeding_male", "Breeding males"
    GOAT_BREEDING_FEMALE = "goat_breeding_female", "Breeding females"
    CATTLE_LOCAL = "cattle_local", "Local cattle"
    CATTLE_DAIRY = "cattle_dairy", "Dairy cattle"
    CATTLE_BEEF = "cattle_beef", "Beef cattle"
    CATTLE_CALVES = "cattle_calves", "Calves"
    CATTLE_HEIFERS = "cattle_heifers", "Heifers"
    CATTLE_BULLS = "cattle_bulls", "Bulls"
    DUCKS_DEFAULT = "ducks_default", "Ducks"
    DUCKS_LAYER = "ducks_layer", "Layer ducks"
    RABBITS_BROILER = "rabbits_broiler", "Rabbits (meat)"
    RABBITS_BREEDING = "rabbits_breeding", "Rabbits (breeding)"
    SHEEP_BREEDING = "sheep_breeding", "Sheep (breeding)"
    SHEEP_LAMBS = "sheep_lambs", "Lambs"
    FISH_POND = "fish_pond", "General pond fish"
    FISH_TILAPIA = "fish_tilapia", "Tilapia"
    FISH_CATFISH = "fish_catfish", "Catfish"
    OTHER_GENERIC = "other_generic", "Other / custom"


# Quick-pick subtypes by animal (values must exist on FarmLivestockSubType)
FARM_SUBTYPES_BY_ANIMAL: dict[str, list[str]] = {
    FarmAnimalType.CHICKENS: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.CHICKEN_BROILERS,
        FarmLivestockSubType.CHICKEN_LAYERS,
        FarmLivestockSubType.CHICKEN_INDIGENOUS,
        FarmLivestockSubType.CHICKEN_HYBRID,
        FarmLivestockSubType.CHICKEN_CHICKS,
        FarmLivestockSubType.CHICKEN_POL,
    ],
    FarmAnimalType.PIGS: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.PIG_LOCAL,
        FarmLivestockSubType.PIG_HYBRID,
        FarmLivestockSubType.PIG_PIGLETS,
        FarmLivestockSubType.PIG_GROWERS,
        FarmLivestockSubType.PIG_SOWS,
        FarmLivestockSubType.PIG_BOARS,
    ],
    FarmAnimalType.GOATS: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.GOAT_LOCAL,
        FarmLivestockSubType.GOAT_BOER,
        FarmLivestockSubType.GOAT_KIDS,
        FarmLivestockSubType.GOAT_BREEDING_MALE,
        FarmLivestockSubType.GOAT_BREEDING_FEMALE,
    ],
    FarmAnimalType.CATTLE: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.CATTLE_LOCAL,
        FarmLivestockSubType.CATTLE_DAIRY,
        FarmLivestockSubType.CATTLE_BEEF,
        FarmLivestockSubType.CATTLE_CALVES,
        FarmLivestockSubType.CATTLE_HEIFERS,
        FarmLivestockSubType.CATTLE_BULLS,
    ],
    FarmAnimalType.DUCKS: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.DUCKS_DEFAULT,
        FarmLivestockSubType.DUCKS_LAYER,
    ],
    FarmAnimalType.RABBITS: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.RABBITS_BROILER,
        FarmLivestockSubType.RABBITS_BREEDING,
    ],
    FarmAnimalType.SHEEP: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.SHEEP_BREEDING,
        FarmLivestockSubType.SHEEP_LAMBS,
    ],
    FarmAnimalType.FISH: [
        FarmLivestockSubType.UNSPECIFIED,
        FarmLivestockSubType.FISH_POND,
        FarmLivestockSubType.FISH_TILAPIA,
        FarmLivestockSubType.FISH_CATFISH,
    ],
    FarmAnimalType.OTHER: [FarmLivestockSubType.OTHER_GENERIC, FarmLivestockSubType.UNSPECIFIED],
}


def subtype_choices_for_animal_type(animal_type: str) -> list[tuple[str, str]]:
    """Return (value, label) tuples for the guided UI for this animal type."""
    keys = FARM_SUBTYPES_BY_ANIMAL.get(
        animal_type,
        [FarmLivestockSubType.UNSPECIFIED, FarmLivestockSubType.OTHER_GENERIC],
    )
    label_by_val = {c.value: c.label for c in FarmLivestockSubType}
    return [(k, label_by_val.get(k, k)) for k in keys]


class FarmAnimalGender(models.TextChoices):
    NA = "na", "Not specified"
    MIXED = "mixed", "Mixed flock / herd"
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class FarmHealthStatus(models.TextChoices):
    UNKNOWN = "unknown", "Not recorded"
    GOOD = "good", "Good"
    WATCH = "watch", "Under observation"
    TREATING = "treating", "Under treatment / vet care"


class FarmVaccinationStatus(models.TextChoices):
    UNKNOWN = "unknown", "Not recorded"
    CURRENT = "current", "Vaccination current"
    PARTIAL = "partial", "Partial / needs booster"
    NONE = "none", "None on record"


class FarmSaleAvailability(models.TextChoices):
    """Marketplace / trade readiness for a batch or crop line."""
    AVAILABLE_NOW = "available_now", "Available now"
    PREORDER = "preorder", "Preorder / future date"
    RESERVED = "reserved", "Reserved (spoken for)"


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
    animal_subtype = models.CharField(
        max_length=40,
        choices=FarmLivestockSubType.choices,
        default=FarmLivestockSubType.UNSPECIFIED,
        db_index=True,
        help_text="Practical subtype (broilers, layers, piglets, etc.)",
    )
    breed_text = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Breed or strain (optional, free text)",
    )
    gender = models.CharField(
        max_length=12,
        choices=FarmAnimalGender.choices,
        default=FarmAnimalGender.NA,
        blank=True,
    )
    age_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Typical or average age in months (for the batch)",
    )
    health_status = models.CharField(
        max_length=20,
        choices=FarmHealthStatus.choices,
        default=FarmHealthStatus.UNKNOWN,
    )
    vaccination_status = models.CharField(
        max_length=20,
        choices=FarmVaccinationStatus.choices,
        default=FarmVaccinationStatus.UNKNOWN,
    )
    feed_growth_stage = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Feed or growth stage (e.g. starter, grower, finisher)",
    )
    egg_production_status = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="For layers: production level or status",
    )
    dairy_output_note = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="For dairy: output note (e.g. litres per day)",
    )
    cost_basis_per_head_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Your cost per head (for margin checks)",
    )
    expected_sale_price_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Asking or expected sale price per head (marketplace & margin)",
    )
    sale_availability = models.CharField(
        max_length=20,
        choices=FarmSaleAvailability.choices,
        default=FarmSaleAvailability.AVAILABLE_NOW,
    )
    is_featured_listing = models.BooleanField(
        default=False,
        help_text="Highlight on internal dashboard and metadata for marketplace",
    )
    marketplace_listing = models.OneToOneField(
        "inventory.MarketplaceListing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_livestock_batch",
    )
    last_marketplace_sync_at = models.DateTimeField(null=True, blank=True)
    primary_image = models.ImageField(
        upload_to="farm/batch/%Y/%m/",
        null=True,
        blank=True,
        help_text="Primary photo for this batch (used for marketplace cover)",
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
            models.Index(fields=["business", "animal_subtype"]),
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

    @property
    def effective_asking_price_per_head_mwk(self) -> Decimal | None:
        """Price used for marketplace & margin (explicit ask, else valuation per head)."""
        if self.expected_sale_price_mwk is not None:
            return self.expected_sale_price_mwk
        return self.price_per_animal_mwk

    @property
    def margin_pct_vs_cost(self) -> Decimal | None:
        """
        Return margin % = (ask - cost) / ask * 100 when both cost and ask are set.
        """
        ask = self.effective_asking_price_per_head_mwk
        if ask is None or self.cost_basis_per_head_mwk is None or ask <= 0:
            return None
        return (ask - self.cost_basis_per_head_mwk) / ask * Decimal("100")

    @property
    def margin_band(self) -> str:
        """
        healthy | caution | risky | unknown
        """
        m = self.margin_pct_vs_cost
        if m is None:
            return "unknown"
        if m < Decimal("0"):
            return "risky"
        if m < Decimal("10"):
            return "caution"
        return "healthy"


class FarmBatchImage(models.Model):
    """Extra photos for a livestock batch (synced to marketplace when publishing)."""

    batch = models.ForeignKey(
        FarmLivestockBatch,
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )
    image = models.ImageField(upload_to="farm/batch_gallery/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["sort_order", "uploaded_at"]

    def __str__(self) -> str:
        return f"Batch image {self.batch_id} #{self.sort_order}"


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


# ==============================================================================
# FARM CROP STOCK (for "sell only what is recorded" enforcement)
# ==============================================================================


class FarmCropCategory(models.TextChoices):
    """Categories for Malawi crops"""
    STAPLES = "staples", "Staples"
    CASH_CROPS = "cash_crops", "Cash Crops"
    LEGUMES = "legumes", "Legumes"
    ROOTS_TUBERS = "roots_tubers", "Roots & Tubers"
    VEGETABLES = "vegetables", "Vegetables"
    EGGS = "eggs", "Eggs"
    MILK = "milk", "Milk & dairy"
    ANIMAL_FEED = "animal_feed", "Animal feed"
    FERTILIZER = "fertilizer", "Fertilizer / manure"
    FRESH_PRODUCE = "fresh_produce", "Fresh produce"
    SEEDLINGS = "seedlings", "Seedlings & saplings"


# Malawi crop catalog - used for seeding and display
MALAWI_CROP_CATALOG = {
    "staples": [
        {"name": "Maize", "emoji": "🌽", "unit": "bag"},
        {"name": "Rice", "emoji": "🍚", "unit": "bag"},
        {"name": "Sorghum", "emoji": "🌾", "unit": "bag"},
        {"name": "Millet", "emoji": "🌾", "unit": "bag"},
    ],
    "cash_crops": [
        {"name": "Tobacco", "emoji": "🍂", "unit": "kg"},
        {"name": "Cotton", "emoji": "🧶", "unit": "kg"},
        {"name": "Tea", "emoji": "🍵", "unit": "kg"},
        {"name": "Sugarcane", "emoji": "🎋", "unit": "kg"},
        {"name": "Sunflower", "emoji": "🌻", "unit": "kg"},
    ],
    "legumes": [
        {"name": "Groundnuts", "emoji": "🥜", "unit": "bag"},
        {"name": "Soybean", "emoji": "🫘", "unit": "bag"},
        {"name": "Beans", "emoji": "🫘", "unit": "bag"},
        {"name": "Pigeon Peas", "emoji": "🫛", "unit": "bag"},
    ],
    "roots_tubers": [
        {"name": "Cassava", "emoji": "🥔", "unit": "kg"},
        {"name": "Sweet Potato", "emoji": "🍠", "unit": "kg"},
        {"name": "Irish Potato", "emoji": "🥔", "unit": "kg"},
    ],
    "vegetables": [
        {"name": "Tomato", "emoji": "🍅", "unit": "kg"},
        {"name": "Onion", "emoji": "🧅", "unit": "kg"},
        {"name": "Cabbage", "emoji": "🥬", "unit": "head"},
        {"name": "Okra", "emoji": "🥒", "unit": "kg"},
        {"name": "Rape/Leafy Greens", "emoji": "🥬", "unit": "bundle"},
    ],
    "eggs": [
        {"name": "Tray (30 eggs)", "emoji": "🥚", "unit": "item"},
        {"name": "Crate (large)", "emoji": "🥚", "unit": "item"},
    ],
    "milk": [
        {"name": "Fresh milk", "emoji": "🥛", "unit": "litre"},
    ],
    "animal_feed": [
        {"name": "Layer mash", "emoji": "🌾", "unit": "kg"},
        {"name": "Broiler starter", "emoji": "🌾", "unit": "kg"},
        {"name": "Pig grower", "emoji": "🌾", "unit": "kg"},
    ],
    "fertilizer": [
        {"name": "Organic manure (bulk)", "emoji": "🪴", "unit": "item"},
    ],
    "fresh_produce": [
        {"name": "Tomatoes (fresh)", "emoji": "🍅", "unit": "kg"},
    ],
    "seedlings": [
        {"name": "Maize seedlings (tray)", "emoji": "🌱", "unit": "item"},
    ],
}


class FarmCrop(models.Model):
    """
    Tracks crops recorded/available for a farm business.
    Used for "sell only what is recorded" validation.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_crops",
        db_index=True,
    )
    name = models.CharField(max_length=100, help_text="Crop name, e.g. 'Maize'")
    category = models.CharField(
        max_length=20,
        choices=FarmCropCategory.choices,
        default=FarmCropCategory.STAPLES,
        db_index=True,
    )
    emoji = models.CharField(max_length=10, default="🌾", blank=True)
    unit = models.CharField(
        max_length=20,
        choices=FarmUnit.choices,
        default=FarmUnit.BAG,
    )
    
    # Stock tracking (optional, for quantity validation)
    quantity_available = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Current available quantity (updated by harvests/sales)",
    )
    cost_basis_per_unit_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Unit cost (for margin estimation)",
    )
    list_price_per_unit_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Asking price per unit for marketplace & margin",
    )
    sale_availability = models.CharField(
        max_length=20,
        choices=FarmSaleAvailability.choices,
        default=FarmSaleAvailability.AVAILABLE_NOW,
    )
    is_featured_listing = models.BooleanField(default=False)
    primary_image = models.ImageField(
        upload_to="farm/crop/%Y/%m/",
        null=True,
        blank=True,
    )
    marketplace_listing = models.OneToOneField(
        "inventory.MarketplaceListing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_crop_line",
    )
    last_marketplace_sync_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["category", "name"]
        unique_together = [("business", "name")]
        indexes = [
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "category"]),
        ]
        verbose_name = "Farm Crop"
        verbose_name_plural = "Farm Crops"
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def margin_pct_vs_cost(self) -> Decimal | None:
        if (
            self.list_price_per_unit_mwk is None
            or self.cost_basis_per_unit_mwk is None
            or self.list_price_per_unit_mwk <= 0
        ):
            return None
        return (
            (self.list_price_per_unit_mwk - self.cost_basis_per_unit_mwk)
            / self.list_price_per_unit_mwk
            * Decimal("100")
        )

    @property
    def margin_band(self) -> str:
        m = self.margin_pct_vs_cost
        if m is None:
            return "unknown"
        if m < Decimal("0"):
            return "risky"
        if m < Decimal("10"):
            return "caution"
        return "healthy"


class FarmCropSale(models.Model):
    """
    Tracks individual crop sales linked to a recorded crop.
    Ensures sales only happen for crops that exist.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_crop_sales",
        db_index=True,
    )
    crop = models.ForeignKey(
        FarmCrop,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    ledger_entry = models.OneToOneField(
        FarmLedgerEntry,
        on_delete=models.CASCADE,
        related_name="crop_sale",
        null=True,
        blank=True,
    )
    
    # Sale details
    date = models.DateField(default=timezone.now, db_index=True)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_price_mwk = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    
    # Buyer info (optional)
    buyer_name = models.CharField(max_length=100, blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_crop_sales_created",
    )
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-date"]),
        ]
        verbose_name = "Farm Crop Sale"
        verbose_name_plural = "Farm Crop Sales"
    
    def __str__(self):
        return f"{self.crop.name} - {self.quantity} @ MWK {self.unit_price_mwk}"
    
    @property
    def total_mwk(self) -> Decimal:
        return self.quantity * self.unit_price_mwk


# ==============================================================================
# FARM ASSETS
# ==============================================================================


class FarmAssetCondition(models.TextChoices):
    """Asset condition status"""
    NEW = "new", "New"
    GOOD = "good", "Good"
    FAIR = "fair", "Fair"
    POOR = "poor", "Poor"


class FarmAsset(models.Model):
    """
    Tracks farm assets: equipment, tools, infrastructure, land.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_assets",
        db_index=True,
    )
    
    # Asset details
    asset_type = models.CharField(max_length=50, help_text="Asset type code, e.g. 'tractor'")
    name = models.CharField(max_length=150, help_text="Display name")
    quantity = models.PositiveIntegerField(default=1)
    value_mwk = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    purchase_date = models.DateField(null=True, blank=True)
    condition = models.CharField(
        max_length=10,
        choices=FarmAssetCondition.choices,
        default=FarmAssetCondition.GOOD,
    )
    notes = models.TextField(blank=True, default="")
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_assets_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "asset_type"]),
        ]
        verbose_name = "Farm Asset"
        verbose_name_plural = "Farm Assets"
    
    def __str__(self):
        return f"{self.name} ({self.get_condition_display()})"


# ==============================================================================
# POULTRY MANAGEMENT (Broilers / Layers)
# ==============================================================================


class PoultryType(models.TextChoices):
    """Types of poultry birds"""
    BROILERS = "broilers", "Broilers"
    LAYERS = "layers", "Layers"
    INDIGENOUS = "indigenous", "Indigenous/Village Chickens"
    DUCKS = "ducks", "Ducks"
    TURKEYS = "turkeys", "Turkeys"
    OTHER = "other", "Other"


class PoultryBatch(models.Model):
    """
    A batch/flock of poultry birds.
    Tracks bird count, mortality, feed usage, and production (eggs for layers).
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="poultry_batches",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="poultry_batches",
    )
    
    # Batch identification
    name = models.CharField(
        max_length=100,
        help_text="Batch name, e.g. 'Broilers Batch 1 - Jan 2026'",
    )
    poultry_type = models.CharField(
        max_length=20,
        choices=PoultryType.choices,
        default=PoultryType.BROILERS,
        db_index=True,
    )
    
    # Initial setup
    start_date = models.DateField(
        default=timezone.now,
        help_text="Date batch was started/received",
    )
    initial_birds = models.PositiveIntegerField(
        default=0,
        help_text="Initial number of birds in batch",
    )
    
    # Current state (updated by daily records)
    current_birds = models.PositiveIntegerField(
        default=0,
        help_text="Current number of birds alive",
    )
    total_deaths = models.PositiveIntegerField(
        default=0,
        help_text="Total deaths to date",
    )
    total_feed_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Total feed consumed in kg",
    )
    total_eggs = models.PositiveIntegerField(
        default=0,
        help_text="Total eggs collected (for layers)",
    )
    
    # Financial tracking
    total_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Total costs incurred (feed, meds, chicks, etc.)",
    )
    total_sales = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Total sales revenue",
    )
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    closed_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="poultry_batches_created",
    )
    
    class Meta:
        ordering = ["-start_date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "poultry_type"]),
        ]
        verbose_name = "Poultry Batch"
        verbose_name_plural = "Poultry Batches"
    
    def __str__(self):
        return f"{self.name} ({self.current_birds} birds)"
    
    @property
    def mortality_rate(self) -> Decimal:
        """Calculate mortality rate as percentage."""
        if self.initial_birds == 0:
            return Decimal("0")
        return (Decimal(self.total_deaths) / Decimal(self.initial_birds)) * Decimal("100")
    
    @property
    def feed_per_bird_kg(self) -> Decimal:
        """Calculate average feed per bird."""
        if self.current_birds == 0:
            return Decimal("0")
        return self.total_feed_kg / Decimal(self.current_birds)
    
    @property
    def profit(self) -> Decimal:
        """Calculate profit/loss."""
        return self.total_sales - self.total_cost


class PoultryDailyRecord(models.Model):
    """
    Daily record for a poultry batch.
    Tracks mortality, feed, medication, eggs, and remarks.
    """
    batch = models.ForeignKey(
        PoultryBatch,
        on_delete=models.CASCADE,
        related_name="daily_records",
    )
    
    # Date
    date = models.DateField(default=timezone.now, db_index=True)
    
    # Bird count
    birds_alive = models.PositiveIntegerField(
        help_text="Number of birds alive at end of day",
    )
    deaths = models.PositiveIntegerField(
        default=0,
        help_text="Number of deaths today",
    )
    
    # Feed
    feed_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Feed given today in kg",
    )
    
    # For layers: egg production
    eggs_collected = models.PositiveIntegerField(
        default=0,
        help_text="Eggs collected today (for layers)",
    )
    
    # Health
    medication = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Medication/vaccination given today",
    )
    
    # Notes
    remarks = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="poultry_daily_records_created",
    )
    
    class Meta:
        ordering = ["-date"]
        unique_together = [("batch", "date")]
        indexes = [
            models.Index(fields=["batch", "-date"]),
        ]
        verbose_name = "Poultry Daily Record"
        verbose_name_plural = "Poultry Daily Records"
    
    def __str__(self):
        return f"{self.batch.name} - {self.date}: {self.birds_alive} birds"
    
    def save(self, *args, **kwargs):
        """Update batch totals on save."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Update batch stats
        if is_new:
            self.batch.current_birds = self.birds_alive
            self.batch.total_deaths += self.deaths
            self.batch.total_feed_kg += self.feed_kg
            self.batch.total_eggs += self.eggs_collected
            self.batch.save(update_fields=[
                "current_birds", "total_deaths", "total_feed_kg", "total_eggs", "updated_at"
            ])


# ==============================================================================
# PIG MANAGEMENT
# ==============================================================================


class PigPen(models.Model):
    """
    A pig pen/sty for organizing pigs.
    Pens can contain different pig categories (sows, boars, growers, finishers).
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="pig_pens",
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pig_pens",
    )
    
    # Pen identification
    name = models.CharField(
        max_length=100,
        help_text="Pen name, e.g. 'Pen A', 'Farrowing 1', 'Grower House 2'",
    )
    pen_type = models.CharField(
        max_length=50,
        choices=[
            ("farrowing", "Farrowing (Sows with piglets)"),
            ("grower", "Grower"),
            ("finisher", "Finisher"),
            ("boar", "Boar"),
            ("gilt", "Gilt (Young females)"),
            ("general", "General"),
        ],
        default="general",
        db_index=True,
    )
    
    # Capacity
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum pigs this pen can hold",
    )
    
    # Current state (updated by daily records)
    current_pigs = models.PositiveIntegerField(
        default=0,
        help_text="Current number of pigs in pen",
    )
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pig_pens_created",
    )
    
    class Meta:
        ordering = ["name"]
        unique_together = [("business", "name")]
        indexes = [
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "pen_type"]),
        ]
        verbose_name = "Pig Pen"
        verbose_name_plural = "Pig Pens"
    
    def __str__(self):
        return f"{self.name} ({self.current_pigs} pigs)"
    
    @property
    def utilization_pct(self) -> Decimal | None:
        """Calculate pen utilization percentage."""
        if not self.capacity or self.capacity == 0:
            return None
        return (Decimal(self.current_pigs) / Decimal(self.capacity)) * Decimal("100")


class PigDailyRecord(models.Model):
    """
    Daily record for a pig pen.
    Tracks count, feed, health, weights, and events.
    """
    pen = models.ForeignKey(
        PigPen,
        on_delete=models.CASCADE,
        related_name="daily_records",
    )
    
    # Date
    date = models.DateField(default=timezone.now, db_index=True)
    
    # Pig count
    pigs_count = models.PositiveIntegerField(
        help_text="Number of pigs in pen at end of day",
    )
    
    # Feed
    feed_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Total feed given to pen today in kg",
    )
    
    # Weight tracking (optional, for monitoring growth)
    average_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average weight per pig in kg (if weighed)",
    )
    
    # Health
    treatment = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Treatment/medication given today",
    )
    
    # Events (births, deaths, transfers)
    births = models.PositiveIntegerField(
        default=0,
        help_text="Number of piglets born today",
    )
    deaths = models.PositiveIntegerField(
        default=0,
        help_text="Number of deaths today",
    )
    transfers_in = models.PositiveIntegerField(
        default=0,
        help_text="Pigs transferred into this pen",
    )
    transfers_out = models.PositiveIntegerField(
        default=0,
        help_text="Pigs transferred out of this pen",
    )
    sales = models.PositiveIntegerField(
        default=0,
        help_text="Pigs sold from this pen today",
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
        related_name="pig_daily_records_created",
    )
    
    class Meta:
        ordering = ["-date"]
        unique_together = [("pen", "date")]
        indexes = [
            models.Index(fields=["pen", "-date"]),
        ]
        verbose_name = "Pig Daily Record"
        verbose_name_plural = "Pig Daily Records"
    
    def __str__(self):
        return f"{self.pen.name} - {self.date}: {self.pigs_count} pigs"
    
    def save(self, *args, **kwargs):
        """Update pen count on save."""
        super().save(*args, **kwargs)
        
        # Update pen current count
        self.pen.current_pigs = self.pigs_count
        self.pen.save(update_fields=["current_pigs", "updated_at"])


# ==============================================================================
# FARM CASHBOOK
# ==============================================================================


class FarmCashbookCategory(models.TextChoices):
    """Categories for farm cashbook entries"""
    FEED = "feed", "Feed"
    MEDICATION = "medication", "Medication/Vaccines"
    CHICKS = "chicks", "Day-old Chicks/Piglets"
    LABOUR = "labour", "Labour/Wages"
    UTILITIES = "utilities", "Utilities (Water/Electricity)"
    TRANSPORT = "transport", "Transport"
    EQUIPMENT = "equipment", "Equipment/Tools"
    SALES_BIRDS = "sales_birds", "Sales - Birds"
    SALES_EGGS = "sales_eggs", "Sales - Eggs"
    SALES_PIGS = "sales_pigs", "Sales - Pigs"
    SALES_CROPS = "sales_crops", "Sales - Crops"
    OTHER_INCOME = "other_income", "Other Income"
    OTHER_EXPENSE = "other_expense", "Other Expense"


class FarmCashbook(models.Model):
    """
    Farm cashbook for tracking all financial transactions.
    Links optionally to poultry batches or pig pens for attribution.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="farm_cashbook_entries",
        db_index=True,
    )
    
    # Transaction details
    date = models.DateField(default=timezone.now, db_index=True)
    category = models.CharField(
        max_length=30,
        choices=FarmCashbookCategory.choices,
        default=FarmCashbookCategory.OTHER_EXPENSE,
        db_index=True,
    )
    description = models.CharField(max_length=255)
    
    # Amount (positive for income, negative for expense)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Amount in MWK (positive for income, negative for expense)",
    )
    
    # Optional links to livestock
    poultry_batch = models.ForeignKey(
        PoultryBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cashbook_entries",
        help_text="Link to poultry batch if applicable",
    )
    pig_pen = models.ForeignKey(
        PigPen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cashbook_entries",
        help_text="Link to pig pen if applicable",
    )
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farm_cashbook_created",
    )
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-date"]),
            models.Index(fields=["business", "category"]),
        ]
        verbose_name = "Farm Cashbook Entry"
        verbose_name_plural = "Farm Cashbook Entries"
    
    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.date}: {sign}{self.amount:,.0f} MWK - {self.description}"
    
    @property
    def is_income(self) -> bool:
        """Check if this is an income entry."""
        return self.amount >= 0
    
    @property
    def is_expense(self) -> bool:
        """Check if this is an expense entry."""
        return self.amount < 0
    
    def save(self, *args, **kwargs):
        """Update linked batch/pen costs on save."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Update poultry batch total cost/sales
        if is_new and self.poultry_batch:
            if self.is_expense:
                self.poultry_batch.total_cost += abs(self.amount)
            else:
                self.poultry_batch.total_sales += self.amount
            self.poultry_batch.save(update_fields=["total_cost", "total_sales", "updated_at"])