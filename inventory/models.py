# circuitcity/inventory/models.py
from __future__ import annotations

import json
import re
import secrets
import string
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

# --- Compatibility kwargs mixin ---
from core.models_compat_kwargs import CompatKwargsMixin

# --- Tenancy imports (explicit) ---
from tenants.models import Business, TenantManager, UnscopedManager

from .business_kinds import BusinessKind

User = get_user_model()

# ---------------------------------------------------------------------
# Attendance model — SINGLE SOURCE OF TRUTH (avoid duplicate registrations)
# ---------------------------------------------------------------------
# We only define TimeLog in models_attendance.py. Re-export it here so legacy
# imports like `from inventory.models import TimeLog` keep working.
try:
    from .models_attendance import TimeLog  # noqa: F401
except Exception:
    TimeLog = None  # safe fallback; avoids import-time crashes in edge cases

# Re-export PhoneStockEditRequest for convenient imports
try:
    from .models_approval import PhoneStockEditRequest  # noqa: F401
except Exception:
    PhoneStockEditRequest = None  # safe fallback

# Re-export PhoneProductCatalog and Electronics models for phone/electronics catalog
try:
    from .models_phone_products import (  # noqa: F401
        PhoneProductCatalog,
        ElectronicsCategory,
        ElectronicsStockItem,
    )
except Exception:
    PhoneProductCatalog = None  # safe fallback
    ElectronicsCategory = None
    ElectronicsStockItem = None

# Re-export Farm models for syncdb table creation
try:
    from .models_farm import (  # noqa: F401
        FarmLedgerEntry,
        FarmCropSeason,
        FarmLivestockBatch,
        FarmLivestockEvent,
    )
except Exception:
    FarmLedgerEntry = None
    FarmCropSeason = None
    FarmLivestockBatch = None
    FarmLivestockEvent = None

# Re-export Farm Livestock models (PART 5: Separate Poultry/Pigs modules)
try:
    from .models_farm_livestock import (  # noqa: F401
        PoultryBatch,
        PoultryDailyRecord,
        PigPen,
        PigDailyRecord,
        FarmCashbookEntry,
    )
except Exception:
    PoultryBatch = None
    PoultryDailyRecord = None
    PigPen = None
    PigDailyRecord = None
    FarmCashbookEntry = None

# Re-export Welding models for syncdb table creation
try:
    from .models_welding import (  # noqa: F401
        WeldingMaterial,
        WeldingMaterialStockMove,
        WeldingTemplate,
        WeldingQuote,
        WeldingJob,
        WeldingInvoice,
        WeldingEstimatorTuning,
    )
except Exception:
    WeldingMaterial = None
    WeldingMaterialStockMove = None
    WeldingTemplate = None
    WeldingQuote = None
    WeldingJob = None
    WeldingInvoice = None
    WeldingEstimatorTuning = None

# Re-export StockActivityLog for audit trail
try:
    from .models_audit import StockAction, StockActivityLog  # noqa: F401
except Exception:
    StockActivityLog = None  # safe fallback
    StockAction = None

# Re-export gamification models (Phase 5)
try:
    from .models_gamification import AgentBadge, AgentStreak, AgentXP, Badge, DailyLeaderboard  # noqa: F401
except Exception:
    AgentStreak = AgentXP = Badge = AgentBadge = DailyLeaderboard = None  # safe fallback

# Re-export liquor assignment models (Phase 6)
try:
    from .models_liquor_assignment import (  # noqa: F401
        LiquorAgentTarget,
        LiquorDailyReconciliation,
        LiquorStockAssignment,
    )
except Exception:
    LiquorStockAssignment = LiquorDailyReconciliation = LiquorAgentTarget = None  # safe fallback

# Re-export PharmacyBatch for cross-module references
try:
    from .models_pharmacy import PharmacyBatch  # noqa: F401
except Exception:
    PharmacyBatch = None  # safe fallback

# Re-export BarcodeRegistry for barcode management
try:
    from .models_barcodes import BarcodeRegistry  # noqa: F401
except Exception:
    BarcodeRegistry = None  # safe fallback

# Re-export Accessory models for phone accessories system
try:
    from .models_accessories import AccessoryCategory, AccessoryProduct, AccessoryStock, AccessoryStockLog  # noqa: F401
except Exception:
    AccessoryProduct = None  # safe fallback
    AccessoryStock = None
    AccessoryStockLog = None
    AccessoryCategory = None

# Re-export InventoryBarcode and ArchiveBatch for stock barcode tracking
try:
    from .models_stock_barcodes import ArchiveBatch, InventoryBarcode  # noqa: F401
except Exception:
    InventoryBarcode = None  # safe fallback
    ArchiveBatch = None

# Re-export Laptop models for laptop/electronics vertical
try:
    from .models_laptops import LaptopBrand, LaptopProduct, LaptopSerial  # noqa: F401
except Exception:
    LaptopProduct = None  # safe fallback
    LaptopSerial = None
    LaptopBrand = None


# ==========================================================
# SINGLE SOURCE OF TRUTH: IMEI normalization (15 digits)
# ==========================================================
def normalize_imei(raw: Optional[str]) -> str:
    """Keep digits only and enforce 15-digit IMEI semantics (prefer the LAST 15 digits)."""
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", str(raw))
    # Many scanners include prefixes/suffixes; keep the last 15 which is the canonical IMEI.
    return digits[-15:] if len(digits) >= 15 else digits


# =========================
# Core reference models
# =========================
class Location(CompatKwargsMixin, models.Model):
    """
    Store / warehouse, scoped to a tenant.
    """
    
    # Backwards compatibility: Map legacy kwargs to canonical fields
    COMPAT_MAP = {
        'is_active': 'is_default',  # Legacy: some tests use is_active instead of is_default
        'is_headquarters': 'is_default',  # Legacy: is_headquarters maps to is_default (HQ flag)
        'address': 'city',  # Legacy: address maps to city (partial address support)
    }

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="locations",
        db_index=True,
        null=True,  # keep nullable for smooth migration; backfill then set False if desired
        blank=True,
    )
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80, blank=True)

    # Optional GPS + geofence radius (meters)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(
        default=150, help_text="Meters around (lat, lon) considered on-site."
    )

    # ---- business default toggle ----
    is_default = models.BooleanField(
        default=False, help_text="When true, this is the default store/location for this business."
    )

    class Meta:
        unique_together = (("business", "name"),)
        indexes = [
            models.Index(fields=["business", "name"], name="loc_biz_name_idx"),
            models.Index(fields=["city"], name="loc_city_idx"),
            models.Index(fields=["business", "is_default"], name="loc_biz_isdefault_idx"),
        ]
        # Partial unique: one default per business
        constraints = [
            models.UniqueConstraint(
                fields=["business", "is_default"],
                condition=Q(is_default=True),
                name="one_default_location_per_business",
            ),
        ]

    def __str__(self):
        label = self.name
        if self.business_id:
            label = f"{label} · {getattr(self.business, 'name', self.business_id)}"
        return label

    # ── Backwards compatibility: is_active property ──
    # Many tests and views check location.is_active, but the field is is_default.
    # This property provides compatibility: all locations are considered "active" by default.
    @property
    def is_active(self):
        """Backwards compatible alias - all locations are considered active."""
        return True  # All locations are active by design

    @property
    def display_name(self):
        """
        Returns 'BusinessName · LocationName' format for UI display.
        Example: "Spears · Spears Mchinji branch"
        """
        if self.business_id:
            biz_name = getattr(self.business, "name", "Business")
            return f"{biz_name} · {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        """
        Ensure only one default per business by unsetting others BEFORE save.
        
        CRITICAL: The unique constraint fires BEFORE super().save() completes,
        so we must unset other defaults within an atomic block BEFORE saving.
        This prevents IntegrityError from the partial unique constraint.
        """
        from django.db import transaction
        
        with transaction.atomic():
            # If this location is being set as default, unset others FIRST
            if self.is_default and self.business_id:
                # Exclude self (by pk if exists) to avoid race condition
                qs = Location.objects.filter(business_id=self.business_id, is_default=True)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                qs.update(is_default=False)
            
            super().save(*args, **kwargs)

    @classmethod
    def default_for(cls, business_or_id):
        """Return the default location if set, else the first one (if any)."""
        biz_id = business_or_id.id if isinstance(business_or_id, Business) else business_or_id
        if not biz_id:
            return None
        default = cls.objects.filter(business_id=biz_id, is_default=True).first()
        if default:
            return default
        return cls.objects.filter(business_id=biz_id).order_by("name", "id").first()

    @classmethod
    def ensure_default_for_business(cls, business: Business):
        """
        Return a default location for the business; create one if none exist.
        This prevents NOT NULL errors when callers omit the location.
        """
        if not business:
            return None
        loc = cls.default_for(business.id)
        if loc:
            return loc
        # Create a sensible first store
        name = f"{getattr(business, 'name', 'Main')} Store".strip()
        try:
            loc = cls.objects.create(business=business, name=name, is_default=True)
        except Exception:
            # Fallback if the above name collides
            loc = cls.objects.create(business=business, name="Main Store", is_default=True)
        return loc


class AgentProfile(models.Model):
    """
    Per-user agent profile anchored to a home location.
    Managers may not have this.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="agent_profile")
    location = models.ForeignKey("Location", on_delete=models.PROTECT, null=True, blank=True)
    joined_on = models.DateField(null=True, blank=True)  # optional join date

    class Meta:
        indexes = [
            models.Index(fields=["joined_on"], name="agentprof_joined_on_idx"),
            models.Index(fields=["location"], name="agentprof_location_idx"),
        ]

    def __str__(self):
        return self.user.get_username()
    
    @property
    def business(self):
        """
        Backwards compatibility: return the business from the location.
        Many legacy tests/code expect agent_profile.business to exist.
        """
        if self.location_id:
            return getattr(self.location, 'business', None)
        return getattr(self, '_business', None)
    
    @business.setter
    def business(self, value):
        """
        Backwards compatibility setter: store business for later use.
        If location is set, this is a no-op (business comes from location).
        """
        self._business = value

    # ---- Convenience: balances & tenure ----
    @property
    def wallet_balance(self) -> float:
        val = WalletTxn.objects.filter(user=self.user).aggregate(s=Sum("amount"))["s"] or 0
        return float(val)

    @property
    def tenure_days(self):
        if not self.joined_on:
            return None
        return (timezone.localdate() - self.joined_on).days


class BaseUnit(models.TextChoices):
    UNIT = "unit", "Unit"  # atomic piece (bread, charger, pack, bottle if no shots)
    SHOT = "shot", "Shot"  # atomic for bars selling shots
    ML = "ml", "ml"  # reserved for future use
    G = "g", "g"  # reserved for future use


class MerchProduct(CompatKwargsMixin, models.Model):
    """
    Simple, non-IMEI product used by liquor/grocery/pharmacy/clothing, etc.
    Phones KEEP using the existing Product + InventoryItem models below.
    """
    
    # Backwards compatibility: Map legacy kwargs to canonical fields
    # CRITICAL: These mappings prevent TypeError when test fixtures use old field names
    COMPAT_MAP = {
        'model': 'name',  # Legacy: some tests/code uses 'model' instead of 'name'
        'cost': 'cost_price',  # Legacy: cost maps to cost_price
        'sell_price': 'selling_price',  # Legacy: sell_price maps to selling_price
        # Legacy kwargs from fixtures that may not exist on current schema
        'location': '_ignored_location',  # Location tracking moved elsewhere
        'quantity': 'quantity_in_stock',  # Legacy: quantity maps to quantity_in_stock
        'vertical_type': 'kind',  # Legacy: vertical_type maps to kind
        'status': '_ignored_status',  # Status may not exist on MerchProduct
        'batch_number': '_ignored_batch_number',  # Pharmacy-specific, handled elsewhere
        'expiry_date': '_ignored_expiry_date',  # Pharmacy-specific, handled elsewhere
    }

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="merch_products", db_index=True)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=BusinessKind.choices, default=BusinessKind.GROCERY)
    sku = models.CharField(max_length=64, blank=True, null=True)
    internal_sku = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Auto-generated internal SKU (business-scoped unique)",
    )
    barcode = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="",
        db_index=True,
        help_text="Product barcode (EAN, UPC, QR, etc.)",
    )
    scan_required = models.BooleanField(default=False)  # set True if you want barcode scanning for some items
    base_unit = models.CharField(max_length=10, choices=BaseUnit.choices, default=BaseUnit.UNIT)
    track_inventory = models.BooleanField(default=True)

    # Category field (used by liquor, pharmacy, and other verticals)
    category = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Product category (e.g., liquor: beer/cider/spirits; pharmacy: medicine/cosmetics)",
    )

    # Liquor: Pack handling (crates/cases for bulk stock-in and selling)
    pack_label = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Pack label: Crate, Case, Pack, Carton, Bale, Bundle (e.g., 'Crate' for beer, 'Carton' for groceries)",
    )
    bottles_per_crate = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Number of base units in a pack (default 20 for Malawi beer crates, 6 for wine/spirits cases, 24 for grocery cartons)",
    )
    supports_crates = models.BooleanField(default=False, help_text="True for beer/cider/wine; False for spirits")

    # Groceries: Wholesale pricing (optional)
    wholesale_price_per_pack = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Wholesale price per pack (carton/bale/bundle). If null, derived from retail price * pack_size",
    )

    # Groceries: Expiry tracking (optional)
    track_expiry = models.BooleanField(
        default=False, help_text="Track expiry dates for this product (optional for groceries)"
    )

    # Groceries: Category group for UI tiles
    category_group = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Category group for groceries UI tiles (drinks, water, snacks, etc.)",
    )

    # Liquor: Shot handling (spirits, whiskey)
    has_shots = models.BooleanField(default=False)
    shots_per_bottle = models.PositiveIntegerField(null=True, blank=True)
    barman_shots_reserved = models.PositiveIntegerField(
        default=2, help_text="Shots reserved for bartender (typically 2)"
    )
    price_per_bottle = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price for a full bottle"
    )
    price_per_shot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price per individual shot"
    )

    # Liquor: Glass handling (wine)
    has_glasses = models.BooleanField(default=False, help_text="True for wine products sold by glass")
    glasses_per_bottle = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of glasses per bottle (typically 5 for wine)"
    )
    price_per_glass = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price per individual glass (for wine)"
    )
    cost_per_glass = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price per glass"
    )

    # Cost price for profit calculation (nullable for backwards compatibility)
    cost_per_bottle = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price for a full bottle"
    )
    cost_per_shot = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price per shot"
    )

    # Smart stock targets (per-product) - for liquor "battery" and auto-adjust
    target_bottles = models.PositiveIntegerField(default=0, help_text="Desired full stock for this product in bottles")
    auto_adjust_enabled = models.BooleanField(default=True, help_text="Enable smart auto-adjust based on sales demand")
    auto_adjust_pct = models.PositiveIntegerField(
        default=20, help_text="Increase target by this % over observed peak demand"
    )

    # Clothing: Premium fields (optional, for premium clothing items)
    brand = models.CharField(
        max_length=100, blank=True, default="", help_text="Brand name (optional, for premium items)"
    )
    item_type = models.CharField(
        max_length=20, blank=True, default="", help_text="Item type: apparel, footwear, accessory, fragrance, other"
    )
    has_sizes = models.BooleanField(default=False, help_text="Enable size variants for this product")
    has_colors = models.BooleanField(default=False, help_text="Enable color variants for this product")

    # Pharmacy: Packaging fields (optional, for tablets/capsules)
    strip_size = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of tablets/capsules per strip (optional)"
    )
    box_size = models.PositiveIntegerField(null=True, blank=True, help_text="Number of strips per box (optional)")
    tablets_per_box = models.PositiveIntegerField(
        null=True, blank=True, help_text="Direct tablets per box (alternative to box_size, optional)"
    )

    # Clothing and general merchandise fields
    size = models.CharField(
        max_length=20, blank=True, default="", help_text="Size for clothing items (e.g., S, M, L, XL, or numeric)"
    )
    color = models.CharField(max_length=50, blank=True, default="", help_text="Color for clothing items")
    spec_label = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Product specification/size label (e.g., '5L', '10L', '9kg') - for groceries and other verticals where spec is separate from quantity",
    )
    quantity_in_stock = models.PositiveIntegerField(
        default=0, help_text="Current quantity in stock (for clothing and other inventory-tracked items)"
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price per unit (for non-liquor items)"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Selling price per unit (for non-liquor items)",
    )

    # Archive helpers (for clothing and other verticals)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="archived_merch_products"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("business", "name"),)
        ordering = ["name"]
        indexes = [
            models.Index(fields=["business", "name"], name="merchprod_biz_name_idx"),
            models.Index(fields=["business", "kind"], name="merchprod_biz_kind_idx"),
            models.Index(fields=["is_active"], name="merchprod_active_idx"),
        ]

    def __str__(self):
        return self.name

    def get_category_display(self):
        """Get human-readable category name based on product kind."""
        if not self.category:
            return ""

        # Import here to avoid circular dependencies
        if self.kind == "pharmacy":
            from .models_pharmacy import PharmacyCategory

            return dict(PharmacyCategory.choices).get(self.category, self.category)
        elif self.kind == "liquor":
            from .models_verticals import LiquorCategory

            return dict(LiquorCategory.choices).get(self.category, self.category)
        else:
            return self.category

    @property
    def pack_size(self):
        """Alias for bottles_per_crate (more generic name for all verticals)"""
        return self.bottles_per_crate

    @pack_size.setter
    def pack_size(self, value):
        """Allow setting pack_size (updates bottles_per_crate)"""
        self.bottles_per_crate = value

    # ── Backwards compatibility: quantity ──
    # Tests and legacy code access product.quantity, but canonical field is quantity_in_stock.
    @property
    def quantity(self):
        """Backwards compatible alias for quantity_in_stock."""
        return self.quantity_in_stock

    @quantity.setter
    def quantity(self, value):
        """Backwards compatible setter for quantity_in_stock."""
        self.quantity_in_stock = value

    @property
    def sellable_shots_per_bottle(self):
        """Calculate sellable shots (total - reserved for barman)"""
        if not self.has_shots or not self.shots_per_bottle:
            return 0
        return max(0, self.shots_per_bottle - self.barman_shots_reserved)

    @property
    def reorder_level(self):
        """
        Safe fallback for reorder level when templates need it.
        Returns target_bottles if set (for liquor), otherwise 0.
        This prevents template crashes when accessing product.reorder_level.
        """
        if hasattr(self, "target_bottles") and self.target_bottles:
            return self.target_bottles
        return 0

    def get_cost_for_unit(self, unit_type: str):
        """
        Get cost price based on unit type (bottle, shot, glass, or crate).

        CRITICAL FIX: For liquor, cost is stored PER BOTTLE (even when ordered by crate).
        Crate cost is computed from: cost_per_bottle * bottles_per_crate
        """
        from decimal import Decimal

        if unit_type == "bottle":
            return self.cost_per_bottle or Decimal("0.00")
        elif unit_type == "shot":
            return self.cost_per_shot or Decimal("0.00")
        elif unit_type == "glass":
            return self.cost_per_glass or Decimal("0.00")
        elif unit_type == "crate":
            # NEW: Crate cost = cost_per_bottle * bottles_per_crate
            if self.cost_per_bottle and self.bottles_per_crate:
                return self.cost_per_bottle * Decimal(self.bottles_per_crate)
            return Decimal("0.00")
        return Decimal("0.00")

    def get_price_for_unit(self, unit_type: str):
        """Get selling price based on unit type (bottle, shot, or glass)"""
        from decimal import Decimal

        if unit_type == "bottle":
            return self.price_per_bottle or Decimal("0.00")
        elif unit_type == "shot":
            return self.price_per_shot or Decimal("0.00")
        elif unit_type == "glass":
            return self.price_per_glass or Decimal("0.00")
        return Decimal("0.00")

    def clean(self):
        if self.has_shots:
            if not self.shots_per_bottle:
                raise ValidationError({"shots_per_bottle": "Required when 'has shots' is enabled."})
            # force atomic to SHOT
            self.base_unit = BaseUnit.SHOT

    def save(self, *args, **kwargs):
        """Auto-calculate unit costs when manager sets total bottle cost"""
        # CRITICAL FIX: Ensure spec_label is never None (defensive normalization)
        # This prevents DB constraint violations from older code paths
        if self.spec_label is None:
            self.spec_label = ""

        # CRITICAL FIX: Auto-generate internal_sku if missing (NOT NULL constraint)
        # This ensures every product has a SKU regardless of entry path
        if not self.internal_sku or not self.internal_sku.strip():
            from inventory.utils_sku import generate_sku

            self.internal_sku = generate_sku(
                business_id=self.business_id, name=self.name, existing_sku=self.internal_sku
            )

        # NEW RULE: Cider pack_size must be exactly 6 (6-pack only, no crates)
        if self.kind == BusinessKind.LIQUOR and self.category and self.category.lower() == "cider":
            if self.bottles_per_crate is not None and self.bottles_per_crate != 6:
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    f"Cider pack size must be exactly 6 (6-pack). Got: {self.bottles_per_crate}. "
                    f"Cider does not use crates."
                )

        # Auto-calculate cost_per_glass for wines if total bottle cost is provided
        if self.has_glasses and self.glasses_per_bottle and self.cost_per_bottle:
            # Only auto-calc if cost_per_glass is not manually set
            if not self.cost_per_glass or self.cost_per_glass == Decimal("0.00"):
                self.cost_per_glass = (self.cost_per_bottle / Decimal(str(self.glasses_per_bottle))).quantize(
                    Decimal("0.01")
                )

        # Auto-calculate cost_per_shot for spirits/whiskey if total bottle cost is provided
        if self.has_shots and self.shots_per_bottle and self.cost_per_bottle:
            # Only auto-calc if cost_per_shot is not manually set
            if not self.cost_per_shot or self.cost_per_shot == Decimal("0.00"):
                # Calculate based on sellable shots (excluding barman reserved)
                sellable_shots = max(1, self.shots_per_bottle - self.barman_shots_reserved)
                self.cost_per_shot = (self.cost_per_bottle / Decimal(str(sellable_shots))).quantize(Decimal("0.01"))

        super().save(*args, **kwargs)


class MerchUnitPrice(models.Model):
    """
    A sellable pack for a MerchProduct. Converts to base units via multiplier.
    Examples:
      - Grocery: Unit (×1), Dozen (×12), Box (×N)
      - Liquor (shots): Shot (×1), Bottle (×shots_per_bottle)
      - Liquor (no shots): Bottle (×1), Crate (×24)
    """

    class Label(models.TextChoices):
        UNIT = "unit", "Unit"
        DOZEN = "dozen", "Dozen (12)"
        BOX = "box", "Box"
        CRATE = "crate", "Crate"
        BOTTLE = "bottle", "Bottle"
        SHOT = "shot", "Shot"

    product = models.ForeignKey(MerchProduct, on_delete=models.CASCADE, related_name="unit_prices")
    label = models.CharField(max_length=20, choices=Label.choices)
    multiplier = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text="How many base units in this pack (e.g., 12 for dozen, 24 for bottle of 24 shots, 1 for unit).",
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = (("product", "label"),)
        indexes = [
            models.Index(fields=["product", "label"], name="merchprice_prod_label_idx"),
        ]

    def __str__(self):
        return f"{self.product.name} · {self.get_label_display()} (×{self.multiplier})"


# ---- Helpers for POS math (merch) ----
def merch_price_for(product: MerchProduct, label: str):
    try:
        return product.unit_prices.get(label=label).price
    except MerchUnitPrice.DoesNotExist:
        return None


def merch_base_units_for_qty(product: MerchProduct, label: str, qty: float) -> float:
    """
    Convert a sale of 'qty' packs (label) into base-unit quantity to decrement inventory once.
    """
    up = product.unit_prices.get(label=label)
    return float(up.multiplier) * float(qty)


# =========================
# Phones catalog (unchanged)
# =========================
class Product(CompatKwargsMixin, models.Model):
    """
    Phone product catalog. Global (not tenant-scoped).
    
    Note: This model does NOT have business/order_price/selling_price fields.
    Those fields exist on InventoryItem (the actual stock item).
    We accept them in __init__ for backwards compatibility with tests/legacy code,
    but silently ignore them (they don't map to any field).
    """
    
    # Backwards compatibility: Accept legacy kwargs that don't map to fields
    # We map them to a non-existent field so they get silently dropped
    COMPAT_MAP = {
        'business': '_ignored_business',      # Product is global, doesn't have business FK
        'order_price': '_ignored_order_price', # This is on InventoryItem, not Product
        'selling_price': '_ignored_selling_price', # This is on InventoryItem, not Product
    }
    
    # FINAL: non-nullable, unique code (backfilled via migration)
    code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SKU/code used in CSV import",
    )
    name = models.CharField(max_length=120, blank=True, help_text="Optional display name")

    brand = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=80)  # correct
    # e.g., Spark 10C
    variant = models.CharField(max_length=80, blank=True)  # e.g., (4+128)
    
    # Barcode field (optional, for barcode scanning)
    barcode = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="",
        db_index=True,
        help_text="Product barcode (EAN, UPC, QR, etc.)",
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Default cost for this product",
    )
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text="Default selling price"
    )

    # Per-product low-stock threshold (applied per location in the daily digest)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    class Meta:
        unique_together = ("model", "variant", "brand")
        indexes = [
            models.Index(fields=["brand", "model", "variant"], name="prod_bmv_idx"),
        ]

    def __str__(self):
        if self.name:
            return self.name
        bits = [self.brand, self.model, self.variant]
        return " ".join(b for b in bits if b).strip()

    # Convenience for templates/forms: Product.active_order_price
    @property
    def active_order_price(self):
        return OrderPrice.get_active_price(self.id)


# --- Default Order Price catalog (with history) ---
class OrderPrice(models.Model):
    """
    Stores the active default *order* price for each product, with history.
    Exactly one active row per product (enforced by a partial unique constraint).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="order_prices")
    default_order_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    active = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "active"],
                condition=Q(active=True),
                name="uniq_active_order_price_per_product",
            )
        ]

    indexes = [
        models.Index(fields=["product", "active"], name="ordprice_prod_active_idx"),
        models.Index(fields=["effective_from"], name="ordprice_effective_idx"),
    ]

    def __str__(self):
        return f"{self.product} — MWK {self.default_order_price:,.2f} ({'active' if self.active else 'old'})"

    @staticmethod
    def get_active_price(product_id: int):
        return (
            OrderPrice.objects.filter(product_id=product_id, active=True)
            .values_list("default_order_price", flat=True)
            .first()
        )


# =========================
# Inventory (phones/IMEI)
# =========================
class InventoryItemQuerySet(models.QuerySet):
    # ---------- general helpers ----------
    def with_related(self):
        """Pull common FKs to prevent N+1s in views/admin/templates."""
        return self.select_related("product", "current_location", "assigned_agent")

    def in_stock(self):
        # Be explicit: active, status IN_STOCK and not sold_at
        return self.filter(is_active=True, status="IN_STOCK", sold_at__isnull=True)

    def sold(self):
        return self.filter(status="SOLD")

    # ---------- SINGLE SOURCE OF TRUTH: IMEI lookup ----------
    def find_in_stock_by_imei(self, business, imei_raw: str):
        """
        Normalized, tenant-aware, 'in stock' lookup for an IMEI.
        This is the ONE place views (scan_in / scan_sold / APIs) should use.
        """
        imei = normalize_imei(imei_raw)
        if len(imei) != 15:
            return None
        biz_id = business.id if isinstance(business, Business) else business
        return self.in_stock().filter(business_id=biz_id, imei=imei).with_related().first()

    # ---------- filters for analytics ----------
    def by_agent(self, user_or_id):
        uid = user_or_id.id if hasattr(user_or_id, "id") else user_or_id
        return self.filter(assigned_agent_id=uid) if uid else self

    def by_location(self, location_or_id):
        lid = location_or_id.id if hasattr(location_or_id, "id") else location_or_id
        return self.filter(current_location_id=lid) if lid else self

    def by_city(self, city: str):
        return self.filter(current_location__city__iexact=city.strip()) if city else self

    def received_between(self, start, end):
        if start and end:
            return self.filter(received_at__range=(start, end))
        return self

    def sold_between(self, start, end):
        if start and end:
            return self.filter(sold_at__date__range=(start, end))
        return self

    # ---------- aggregations for charts ----------
    def daily_in(self, start, end):
        """
        Returns rows like: {'day': date, 'count': N}
        """
        qs = self.received_between(start, end)
        return qs.values("received_at").order_by("received_at").annotate(count=Count("id"))

    def daily_out(self, start, end):
        """
        Returns rows like: {'day': date, 'count': N}
        """
        qs = self.sold().sold_between(start, end)
        return qs.annotate(day=TruncDate("sold_at")).values("day").order_by("day").annotate(count=Count("id"))

    def totals_in(self, start=None, end=None):
        return self.received_between(start, end).count()

    def totals_out(self, start=None, end=None):
        return self.sold_between(start, end).sold().count()


# -------- Tenant-aware managers (scoped/global) --------
TenantInventoryItemManager = TenantManager.from_queryset(InventoryItemQuerySet)  # scoped
UnscopedInventoryItemManager = UnscopedManager.from_queryset(InventoryItemQuerySet)  # global


class TenantActiveItemManager(TenantInventoryItemManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class InventoryItem(CompatKwargsMixin, models.Model):
    """
    One physical phone. Use IMEI for scanning. If you ever need to,
    IMEI can be left blank and we still track the device.
    """
    
    # Backwards compatibility: Map legacy kwargs to canonical fields
    COMPAT_MAP = {
        'brand': '_ignored_brand',  # InventoryItem doesn't have brand (it's on Product FK)
        'model': '_ignored_model',  # InventoryItem doesn't have model (it's on Product FK)
        'cost': 'order_price',  # Legacy: cost maps to order_price (cost to acquire)
        'sell_price': 'selling_price',  # Legacy: sell_price maps to selling_price
        'code': 'imei',  # Legacy: code maps to imei (serial/identifier)
        'serial': 'imei',  # Legacy: serial maps to imei
        'sku': '_ignored_sku',  # InventoryItem doesn't have sku (it's on Product FK)
        'barcode': 'imei',  # Legacy: barcode can map to imei for phones
    }

    STATUS = [("IN_STOCK", "In stock"), ("SOLD", "Sold")]

    # --- TENANCY ---
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="inventory_items",
        db_index=True,
        null=True,  # keep nullable for migration/backfill; set not null once data is clean
        blank=True,
    )

    imei = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\d{15}$", "IMEI must be exactly 15 digits.")],
        help_text="15-digit IMEI. GLOBALLY UNIQUE across all tenants when provided.",
    )
    product = models.ForeignKey("Product", on_delete=models.PROTECT)

    # default today
    received_at = models.DateField(default=timezone.localdate)  # stock-in date

    # give NOT NULL a safe default
    order_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Must be zero or positive.",
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Must be zero or positive when provided.",
    )
    status = models.CharField(max_length=10, choices=STATUS, default="IN_STOCK", db_index=True)
    current_location = models.ForeignKey("Location", on_delete=models.PROTECT, db_index=True)
    assigned_agent = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_items",
        help_text="If set, this stock item belongs to a specific agent; otherwise to the manager/global pool.",
    )
    # Stock ownership role categorization
    ASSIGNMENT_ROLE_CHOICES = [
        ("MANAGER", "Manager"),
        ("AGENT", "Agent"),
    ]
    assigned_role = models.CharField(
        max_length=20,
        choices=ASSIGNMENT_ROLE_CHOICES,
        default="MANAGER",
        db_index=True,
        help_text="For reporting and filters. Indicates whether stock is manager-owned or agent-owned.",
    )
    # Soft-delete flag (archive instead of hard delete when needed)
    is_active = models.BooleanField(default=True, db_index=True)

    # Archive tracking (enhanced soft-delete)
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this item was archived (soft-deleted). NULL means not archived.",
    )
    archived_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_stock_items",
        help_text="Manager/admin who archived this item.",
    )

    # Payment method (for phones sold)
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("BANK", "Bank"),
        ("MOBILE_MONEY", "Mobile Money"),
    ]
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="CASH",
        blank=True,
        help_text="Payment method used when sold",
    )

    # ✅ Timestamps – use defaults to avoid interactive migration prompts
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)  # we’ll bump this in save()

    # ---------- Carlcare warranty/activation tracking ----------
    # NOTE: If you see "no such column: inventory_inventoryitem.warranty_expiration",
    #       run: python manage.py migrate inventory
    #       Migration 0039 renames warranty_expires_at -> warranty_expiration.
    WARRANTY_CHOICES = [
        ("unknown", "Unknown"),
        ("no_warranty", "No warranty"),
        ("in_warranty", "In warranty"),
        ("expired", "Expired"),
        ("activated", "Activated"),  # Warranty present + expiration date (already activated)
    ]
    warranty_status = models.CharField(
        max_length=20,
        choices=WARRANTY_CHOICES,
        default="unknown",
        help_text="Carlcare warranty status for Tecno/Itel phones",
    )
    warranty_expiration = models.DateField(
        null=True, blank=True, db_index=True, help_text="Warranty expiration date if available"
    )
    warranty_checked_at = models.DateTimeField(
        null=True, blank=True, help_text="Last time warranty was checked with Carlcare"
    )
    warranty_source = models.CharField(
        max_length=50, default="carlcare", blank=True, help_text="Source of warranty information (e.g., carlcare)"
    )
    warranty_raw = models.JSONField(null=True, blank=True, help_text="Raw warranty check response for auditing")

    # Backward compatibility aliases (deprecated - remove after migration)
    @property
    def warranty_expires_at(self):
        """Alias for warranty_expiration (backward compatibility)"""
        return self.warranty_expiration

    @property
    def warranty_last_checked_at(self):
        """Alias for warranty_checked_at (backward compatibility)"""
        return self.warranty_checked_at

    @property
    def activation_detected_at(self):
        """Deprecated: use warranty_checked_at when status is 'activated'"""
        if self.warranty_status == "activated":
            return self.warranty_checked_at
        return None

    # Marked when a sale is recorded (used by 15-minute theft alert)
    sold_at = models.DateTimeField(null=True, blank=True, db_index=True)  # fast recent-sold lookups

    # Agent/user who sold this item (for commission attribution)
    sold_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items_sold",
        help_text="Agent/user who sold this item (for commission attribution)",
    )
    # ----------------------------------------------------------------

    # Tenant-aware managers
    objects = TenantInventoryItemManager()  # scoped to active tenant (has QuerySet helpers)
    active = TenantActiveItemManager()  # scoped + non-archived
    all_objects = UnscopedInventoryItemManager()  # global/admin (use sparingly)

    class Meta:
        indexes = [
            models.Index(fields=["imei"], name="inv_imei_global_idx"),  # Global IMEI index
            models.Index(fields=["business", "imei"], name="inv_biz_imei_idx"),
            # Composite for inventory lists — name <= 30 chars
            models.Index(
                fields=["business", "product", "current_location", "status"],
                name="inv_bpls_idx",
                condition=Q(is_active=True),
            ),
            models.Index(fields=["business", "is_active", "status"], name="inv_bis_idx"),
            # Warranty lookups (use the real DB field: warranty_expiration)
            models.Index(fields=["warranty_status", "warranty_expiration"], name="inv_wty_stat_exp_idx"),
            # Stock aging
            models.Index(fields=["received_at"], name="inv_received_idx"),
            # sold_by tracking (for commission attribution)
            models.Index(fields=["sold_by", "sold_at"], name="inv_sold_by_at_idx"),
        ]
        constraints = [
            # GLOBAL IMEI uniqueness (across ALL tenants) - enforced when IMEI present
            models.UniqueConstraint(
                fields=["imei"],
                condition=Q(imei__isnull=False) & ~Q(imei=""),
                name="uniq_imei_globally",
            ),
            models.CheckConstraint(condition=Q(order_price__gte=0), name="inv_order_price_nonneg"),
            models.CheckConstraint(
                condition=Q(selling_price__gte=0) | Q(selling_price__isnull=True),
                name="inv_selling_price_nonneg",
            ),
            models.CheckConstraint(condition=Q(status__in=["IN_STOCK", "SOLD"]), name="inv_status_allowed"),
            models.CheckConstraint(
                condition=Q(product__isnull=False) & Q(current_location__isnull=False),
                name="inv_requires_product_and_location",
            ),
        ]

    def __str__(self):
        return self.imei or f"{self.pk} (no IMEI)"

    @property
    def profit(self):
        return (self.selling_price - self.order_price) if self.selling_price is not None else None

    @property
    def is_sold(self) -> bool:
        return self.status == "SOLD"

    @property
    def is_archived(self) -> bool:
        """Check if item is archived (soft-deleted)."""
        return self.archived_at is not None

    # --- Compatibility helpers for templates / legacy code ---
    @property
    def location_safe(self):
        """
        Back-compat accessor for templates that previously used `item.location`.
        Prefer `current_location`, but expose a stable name that won’t break.
        """
        return getattr(self, "current_location", None)

    @property
    def location(self):
        """
        Hard back-compat: many older views/serializers may still access .location.
        Map it to .current_location to prevent AttributeError or select_related errors.
        """
        return getattr(self, "current_location", None)
    
    @location.setter
    def location(self, value):
        """
        Setter for backwards compatibility with tests.
        Maps location assignment to current_location field.
        
        Usage:
            item.location = some_location
            # Equivalent to: item.current_location = some_location
        """
        self.current_location = value

    # ---------- SINGLE SOURCE OF TRUTH: exported helpers ----------
    @classmethod
    def normalize_imei(cls, raw: Optional[str]) -> str:
        return normalize_imei(raw)

    @classmethod
    def lookup_in_stock(cls, business, imei_raw: str):
        """
        Tenant-aware, normalized, in-stock lookup. Use this everywhere.
        """
        return cls.objects.find_in_stock_by_imei(business, imei_raw)

    # --- NEW: guard — only allow IMEI/price changes on IN_STOCK items
    def _raise_if_sold_fields_changed(self):
        """
        If this row already exists and is SOLD, prevent IMEI/selling_price edits.
        This enforces your rule at the model layer without changing DB schema.
        """
        if not self.pk:
            return
        try:
            old = InventoryItem.all_objects.get(pk=self.pk)
        except InventoryItem.DoesNotExist:
            return
        if old.status == "SOLD":
            changed_imei = (old.imei or "") != (self.imei or "")
            changed_price = (old.selling_price or 0) != (self.selling_price or 0)
            if changed_imei or changed_price:
                raise ValidationError({"status": "Cannot edit IMEI or selling price for SOLD items."})

    def clean(self):
        errors = {}

        # Normalize IMEI before validation so storage is consistent
        if self.imei:
            self.imei = normalize_imei(self.imei)

        if self.status == "SOLD" and not self.sold_at:
            # Allow auto-fill in save(); don't hard-require here
            pass

        if self.imei:
            s = str(self.imei).strip()
            if not s.isdigit() or len(s) != 15:
                errors["imei"] = "IMEI must be exactly 15 numeric digits."
            else:
                # Check for GLOBAL IMEI uniqueness (across all tenants)
                existing = InventoryItem.objects.filter(imei=s).exclude(pk=self.pk)
                if existing.exists():
                    errors["imei"] = "This IMEI already exists in the system and cannot be used again."

        if self.assigned_agent_id:
            # HQ Admins (superuser/staff) should never hold stock
            if getattr(self.assigned_agent, "is_staff", False) or getattr(self.assigned_agent, "is_superuser", False):
                errors["assigned_agent"] = "Stock cannot be assigned to admin/staff accounts. Assign to an agent."
            # Managers don't need AgentProfile - they're operational supervisors
            # Only enforce AgentProfile for actual field agents
            elif not hasattr(self.assigned_agent, "agent_profile"):
                # Check if user is a manager - managers can hold stock without AgentProfile
                try:
                    from tenants.utils_roles import is_manager

                    user_is_manager = is_manager(self.assigned_agent, business=self.business)
                    if not user_is_manager:
                        errors["assigned_agent"] = "Assigned user must be an agent (has AgentProfile) or a manager."
                except Exception:
                    # If we can't check manager status, require AgentProfile
                    errors["assigned_agent"] = "Assigned user must be an agent (has AgentProfile)."

        if errors:
            raise ValidationError(errors)

        # --- NEW: enforce 'no edit fields when SOLD'
        self._raise_if_sold_fields_changed()

    # ---- auto-defaults for date/location/sold_at ----
    def save(self, *args, **kwargs):
        # Normalize IMEI again at save-time (defense-in-depth)
        if self.imei:
            self.imei = normalize_imei(self.imei)

        # Ensure received_at is set (field has default, but just in case)
        if not getattr(self, "received_at", None):
            self.received_at = timezone.localdate()

        # ---------- NEW: inherit business from current_location if missing ----------
        # This prevents NULL-business items and avoids future uniqueness collisions
        # when backfilling business later.
        if not getattr(self, "business_id", None) and getattr(self, "current_location_id", None):
            try:
                self.business_id = getattr(self.current_location, "business_id", None)
            except Exception:
                # if current_location not hydrated, fetch id from DB
                self.business_id = (
                    Location.objects.only("business_id")
                    .filter(pk=self.current_location_id)
                    .values_list("business_id", flat=True)
                    .first()
                )

        # Auto-pick or create a default store for the business if missing
        if not getattr(self, "current_location_id", None) and self.business_id:
            # We require the Business instance to create a location if needed
            biz = getattr(self, "business", None)
            default_loc = None
            try:
                # Try strong default first
                default_loc = Location.default_for(self.business_id)
                if default_loc is None and biz is not None:
                    # Create one if the business has zero locations
                    default_loc = Location.ensure_default_for_business(biz)
            except Exception:
                default_loc = None
            if default_loc:
                self.current_location = default_loc

        # If it's marked sold without a timestamp, use now
        if self.status == "SOLD" and not self.sold_at:
            self.sold_at = timezone.now()

        # ✅ keep updated_at fresh
        self.updated_at = timezone.now()

        super().save(*args, **kwargs)

    # -------------------------
    # --- NEW: safe helpers ---
    # -------------------------
    def can_modify_instock(self) -> bool:
        """Allowed to edit/delete only when IN_STOCK and active."""
        return self.is_active and self.status == "IN_STOCK" and (self.sold_at is None)

    def apply_instock_update(
        self, *, new_imei: Optional[str] = None, new_price: Optional[float] = None, by_user=None
    ) -> None:
        """
        Update IMEI and/or selling_price ONLY for IN_STOCK items.
        Creates InventoryAudit rows; raises ValidationError on rule breaks.
        """
        if not self.can_modify_instock():
            raise ValidationError("Only IN_STOCK & active items can be edited.")

        changes = {}
        if new_imei is not None:
            norm = normalize_imei(new_imei)
            if len(norm) != 15 or not norm.isdigit():
                raise ValidationError("IMEI must be exactly 15 numeric digits.")
            if (self.imei or "") != norm:
                old = self.imei or ""
                self.imei = norm
                changes["imei"] = {"from": old, "to": norm}

        if new_price is not None:
            try:
                # trust Decimal at form layer; here accept float/str for convenience
                new_val = float(new_price)
            except Exception:
                raise ValidationError("Invalid price.")
            if new_val < 0:
                raise ValidationError("Price must be non-negative.")
            oldp = float(self.selling_price or 0)
            if oldp != new_val:
                self.selling_price = new_val
                changes["selling_price"] = {"from": oldp, "to": new_val}

        if not changes:
            return

        self.full_clean()  # will re-check IMEI/uniqueness/ SOLD rules
        fields = ["imei", "selling_price", "updated_at"] if hasattr(self, "updated_at") else ["imei", "selling_price"]
        self.save(update_fields=fields)

        try:
            AuditLog.objects.create(
                action="EDIT",
                by_user=by_user,
                item=self,
                business=self.business,
                details=json.dumps(changes, sort_keys=True),
            )
        except Exception:
            # never block the request on audit failure
            pass

    def soft_delete_instock(self, *, by_user=None) -> None:
        """
        Soft-delete (archive) ONLY when IN_STOCK & active.
        """
        if not self.can_modify_instock():
            raise ValidationError("Only IN_STOCK & active items can be deleted.")

        if not self.is_active:
            return  # already archived

        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"] if hasattr(self, "updated_at") else ["is_active"])

        try:
            AuditLog.objects.create(
                action="DELETE",
                by_user=by_user,
                item=self,
                business=self.business,
                details="Soft delete (archive) — IN_STOCK rule",
            )
        except Exception:
            pass


# =========================
# Auditing & logs
# =========================
class InventoryAudit(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("EDIT", "Edit"),
        ("STOCK_IN", "Stock in"),
        ("SOLD", "Sold"),
        ("SOLD_FORM", "Sold via form"),
        ("SOLD_API", "Sold via API"),
        ("SOLD_API_DUP", "Sold via API (duplicate)"),
        ("BULK_PRICE_UPDATE", "Bulk price update"),
        ("DELETE", "Delete"),
        ("DELETE_DENIED", "Delete denied"),
        ("DELETE_BLOCKED", "Delete blocked (FK protect)"),
        ("ARCHIVE_FALLBACK", "Archived instead of delete"),
        ("RESTORE", "Restore"),
    ]

    business = models.ForeignKey(  # carry tenant for fast/scoped reads
        Business, on_delete=models.CASCADE, null=True, blank=True, related_name="inventory_audits", db_index=True
    )
    item = models.ForeignKey("InventoryItem", on_delete=models.SET_NULL, related_name="audits", null=True, blank=True)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [
            models.Index(fields=["business", "action", "at"], name="invaudit_biz_action_at_idx"),
            models.Index(fields=["action", "at"], name="invaudit_action_at_idx"),
        ]

    def __str__(self):
        who = self.by_user.username if self.by_user else "system"
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} by {who} on item {self.item_id}"


# ---- Proxy for legacy AuditLog API ----
class _AuditLogManager(models.Manager):
    def create(self, *args, **kwargs):
        mapped = {}
        if "action" in kwargs:
            mapped["action"] = kwargs.pop("action")
        if "by_user" in kwargs:
            mapped["by_user"] = kwargs.pop("by_user")
        if "user" in kwargs:
            mapped["by_user"] = kwargs.pop("user")
        if "item" in kwargs:
            mapped["item"] = kwargs.pop("item")

        # allow business passthrough if provided
        if "business" in kwargs:
            mapped["business"] = kwargs.pop("business")

        extra_bits = []
        if "model" in kwargs:
            extra_bits.append(f"model={kwargs.pop('model')}")
        if "object_id" in kwargs:
            extra_bits.append(f"object_id={kwargs.pop('object_id')}")
        if "changes" in kwargs:
            try:
                extra_bits.append("changes=" + json.dumps(kwargs.pop("changes"), sort_keys=True))
            except Exception:
                extra_bits.append("changes=<unserializable>")

        details = kwargs.pop("details", "")
        if extra_bits:
            details = (details + "; " if details else "") + ", ".join(extra_bits)
        if details:
            mapped["details"] = details

        mapped.update(kwargs)
        return super().create(**mapped)


class AuditLog(InventoryAudit):
    objects = _AuditLogManager()

    class Meta:
        proxy = True
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"


class WarrantyCheckLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    imei = models.CharField(max_length=30)
    result = models.CharField(max_length=32)  # mirrors InventoryItem.WARRANTY_CHOICES keys
    expires_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    item = models.ForeignKey(InventoryItem, null=True, blank=True, on_delete=models.SET_NULL)
    by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # SHORTENED to satisfy 30-char limit
            models.Index(fields=["business", "imei", "created_at"], name="wcl_biz_imei_created"),
            models.Index(fields=["imei", "created_at"], name="warrantylog_imei_created_idx"),
            models.Index(fields=["result", "created_at"], name="wlog_res_created_idx"),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.imei} -> {self.result}"


class AgentPasswordReset(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_resets")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["user", "code", "used", "expires_at"], name="agrs_user_code_used_exp_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reset for {self.user_id} at {self.created_at:%Y-%m-%d %H:%M} (used={self.used})"

    def is_valid(self) -> bool:
        return (not self.used) and timezone.now() <= self.expires_at

    @staticmethod
    def generate_code() -> str:
        return "".join(secrets.choice(string.digits) for _ in 6)


# ---- NEW: ShiftSession (for inside/outside second counters) ----
class ShiftSession(models.Model):
    """
    Open/closed work session for an agent, used to accumulate inside/outside seconds.
    Safe additive model: does not change TimeLog behavior; analytics read from here.
    """

    STATUS_CHOICES = [("inside", "Inside"), ("outside", "Outside")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shift_sessions")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    location = models.ForeignKey("Location", on_delete=models.SET_NULL, null=True, blank=True)

    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=8, choices=STATUS_CHOICES, null=True, blank=True)
    last_credited_at = models.DateTimeField(null=True, blank=True)

    inside_seconds = models.IntegerField(default=0)
    outside_seconds = models.IntegerField(default=0)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["user", "started_at"], name="shift_user_started_idx"),
            models.Index(fields=["business", "started_at"], name="shift_biz_started_idx"),
            models.Index(fields=["ended_at"], name="shift_ended_idx"),
        ]

    def __str__(self):
        return f"Shift #{self.id} · {self.user} · {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def total_seconds(self) -> int:
        return max(0, int(self.inside_seconds) + int(self.outside_seconds))


class WalletTxn(models.Model):
    """Money going into/out of an agent wallet (bonuses, penalties, manual)."""

    REASON_CHOICES = [
        ("EARLY_BIRD", "Early-bird bonus"),
        ("LATE_PENALTY", "Late penalty"),
        ("SUNDAY_BONUS", "Sunday bonus"),
        ("ADJUSTMENT", "Adjustment"),
        ("COMMISSION", "Commission"),
        ("ADVANCE", "Advance payment to agent"),
        ("PAYOUT", "Payout to agent"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inventory_wallet_txns",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # + = bonus/credit, - = deduction
    reason = models.CharField(max_length=32, choices=REASON_CHOICES, default="ADJUSTMENT")
    created_at = models.DateTimeField(default=timezone.now)
    memo = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"], name="wallettxn_user_created_idx"),
            models.Index(fields=["reason", "created_at"], name="wallettxn_reason_created_idx"),
        ]

    def __str__(self):
        sign = "+" if self.amount >= 0 else "-"
        return f"{self.user} {sign}MK{abs(self.amount)} ({self.reason})"

    @staticmethod
    def balance_for(user) -> float:
        val = WalletTxn.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or 0
        return float(val)

    @staticmethod
    def month_sum_for(user, year: int, month: int) -> float:
        start = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        val = (
            WalletTxn.objects.filter(user=user, created_at__gte=start, created_at__lt=end).aggregate(s=Sum("amount"))[
                "s"
            ]
            or 0
        )
        return float(val)


# ------------------------------------------------------------------
# Back-compat aliases (fix legacy imports without touching views)
# ------------------------------------------------------------------
# Old code may do: from inventory.models import AgentLocation
AgentLocation = Location
# Some code referenced AgentStore as an alias for Location
AgentStore = Location


# =====================================================================
# CATEGORY-SPECIFIC PRODUCT PROXIES (to satisfy helpers & clean imports)
# =====================================================================


# ---- Managers that pin a MerchProduct proxy to a kind ----
class _KindLockedManager(models.Manager):
    """Returns only rows that match the locked kind for the proxy."""

    KIND_VALUE: Optional[str] = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.KIND_VALUE:
            return qs.filter(kind=self.KIND_VALUE)
        return qs


class _PharmacyManager(_KindLockedManager):
    KIND_VALUE = BusinessKind.PHARMACY


class _ClothingManager(_KindLockedManager):
    KIND_VALUE = BusinessKind.CLOTHING


class _LiquorManager(_KindLockedManager):
    KIND_VALUE = BusinessKind.LIQUOR


# ---- Proxies over MerchProduct (enforce kind on save) ----
class PharmacyProduct(MerchProduct):
    objects = _PharmacyManager()

    class Meta:
        proxy = True
        verbose_name = "Pharmacy Product"
        verbose_name_plural = "Pharmacy Products"

    def save(self, *args, **kwargs):
        self.kind = BusinessKind.PHARMACY
        return super().save(*args, **kwargs)


class ClothingProduct(MerchProduct):
    objects = _ClothingManager()

    class Meta:
        proxy = True
        verbose_name = "Clothing Product"
        verbose_name_plural = "Clothing Products"

    def save(self, *args, **kwargs):
        self.kind = BusinessKind.CLOTHING
        return super().save(*args, **kwargs)


class LiquorProduct(MerchProduct):
    objects = _LiquorManager()

    class Meta:
        proxy = True
        verbose_name = "Liquor Product"
        verbose_name_plural = "Liquor Products"

    def save(self, *args, **kwargs):
        self.kind = BusinessKind.LIQUOR
        return super().save(*args, **kwargs)


# ==============================================================================
# PRODUCT PRICE HISTORY (for tracking price changes without creating duplicates)
# ==============================================================================


class ProductPriceHistory(models.Model):
    """
    Tracks price changes for products over time, avoiding duplicate product creation.
    
    Use case: Cement vertical needs to track weekly/seasonal price changes for the
    same brand without creating "Brand Week 1", "Brand Week 2" as separate products.
    
    Instead, keep ONE canonical product and record price history entries.
    """
    product = models.ForeignKey(
        MerchProduct,
        on_delete=models.CASCADE,
        related_name="price_history",
        help_text="The product whose price is being tracked"
    )
    
    # Prices (match MerchProduct fields)
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Selling price at this point in time"
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cost/order price at this point in time"
    )
    
    # Timing
    effective_date = models.DateField(
        default=timezone.now,
        db_index=True,
        help_text="Date when this price became effective"
    )
    
    # Optional label (e.g. "Week 1", "Q1 2026", "Jan Season")
    label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional label for this price period (e.g. 'Week 3', 'Q2 2026')"
    )
    
    # Audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_history_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-effective_date", "-created_at"]
        indexes = [
            models.Index(fields=["product", "-effective_date"]),
        ]
        # Prevent duplicate price history for same product + date
        constraints = [
            models.UniqueConstraint(
                fields=["product", "effective_date"],
                name="unique_product_price_per_date"
            ),
        ]
        verbose_name = "Product Price History"
        verbose_name_plural = "Product Price Histories"
    
    def __str__(self):
        label_str = f" ({self.label})" if self.label else ""
        return f"{self.product.name} - MK {self.selling_price}{label_str} @ {self.effective_date}"


# ---- PhoneProduct proxy over phones' Product (for uniform import path) ----
class PhoneProduct(Product):
    class Meta:
        proxy = True
        verbose_name = "Phone Product"
        verbose_name_plural = "Phone Products"


# ==============================================================================
# Import verticals-specific models
# ==============================================================================
# Import after all base models are defined to avoid circular imports
try:
    # Import clothing barcode unit model
    from .models_clothing_barcode import ClothingBarcodeUnit
    from .models_verticals import (  # Liquor; Gym; Clothing
        ClothingProductLog,
        ClothingSale,
        GymMember,
        GymMemberLog,
        GymPayment,
        GymSettings,
        GymWalletEntry,
        LiquorCredit,
        LiquorCreditPayment,
        LiquorExpense,
        LiquorSale,
        LiquorStockEditRequest,
        LiquorWalletEntry,
        TrainerFee,
    )

    __all__ = [
        # Liquor
        "LiquorSale",
        "LiquorCredit",
        "LiquorCreditPayment",
        "LiquorStockEditRequest",
        "LiquorExpense",
        "LiquorWalletEntry",
        # Gym
        "GymMember",
        "GymPayment",
        "GymMemberLog",
        "GymSettings",
        "GymWalletEntry",
        "TrainerFee",
        # Clothing
        "ClothingSale",
        "ClothingProductLog",
        "ClothingBarcodeUnit",
    ]
except ImportError:
    # Not yet migrated
    pass


# ---------------------------------------------------------------------------
# Marketplace models (public listing + enquiries)
# ---------------------------------------------------------------------------
try:
    from inventory.models_marketplace import (  # noqa: F401, E402
        MarketplaceListing,
        MarketplaceListingImage,
        MarketplaceEnquiry,
        ListingStatus,
    )
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Car Dealer vertical models
# ---------------------------------------------------------------------------
try:
    from inventory.models_car_dealer import (  # noqa: F401, E402
        CarMake,
        CarModel,
        CarDealerVehicle,
    )
except ImportError:
    pass
