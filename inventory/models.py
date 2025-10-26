# circuitcity/inventory/models.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone

# --- Tenancy imports (explicit) ---
from tenants.models import Business, TenantManager, UnscopedManager  # NEW

import json
import secrets
import string
import re

User = get_user_model()


# ==========================================================
# SINGLE SOURCE OF TRUTH: IMEI normalization (15 digits)
# ==========================================================
def normalize_imei(raw: Optional[str]) -> str:
    """Keep digits only and enforce 15-digit IMEI semantics."""
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", str(raw))
    return digits[:15]  # scanners sometimes add noise; we clip to 15


# =========================
# Core reference models
# =========================
class Location(models.Model):
    """
    Store / warehouse, scoped to a tenant.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="locations",
        db_index=True,
        null=True,   # keep nullable for smooth migration; backfill then set False if desired
        blank=True,
    )
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80, blank=True)

    # Optional GPS + geofence radius (meters)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(
        default=150,
        help_text="Meters around (lat, lon) considered on-site."
    )

    # ---- business default toggle ----
    is_default = models.BooleanField(
        default=False,
        help_text="When true, this is the default store/location for this business."
    )

    class Meta:
        unique_together = (("business", "name"),)
        indexes = [
            models.Index(fields=["business", "name"], name="loc_biz_name_idx"),
            models.Index(fields=["city"], name="loc_city_idx"),
            models.Index(fields=["business", "is_default"], name="loc_biz_isdefault_idx"),
        ]
    # NOTE: Partial unique below ensures one default per business
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
            label = f"{label} Â· {getattr(self.business, 'name', self.business_id)}"
        return label

    def save(self, *args, **kwargs):
        """
        Ensure only one default per business by unsetting others after save.
        """
        super().save(*args, **kwargs)
        if self.is_default and self.business_id:
            Location.objects.filter(
                business_id=self.business_id, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

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
    # connects a Django user to a home location
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="agent_profile")
    location = models.ForeignKey("Location", on_delete=models.PROTECT)
    joined_on = models.DateField(null=True, blank=True)  # optional join date

    class Meta:
        indexes = [
            models.Index(fields=["joined_on"], name="agentprof_joined_on_idx"),
            models.Index(fields=["location"], name="agentprof_location_idx"),
        ]

    def __str__(self):
        return self.user.get_username()

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


# =====================================================================
# Generic merchandise catalog (non-IMEI) for liquor/grocery/pharmacy/clothing
# =====================================================================
class BusinessKind(models.TextChoices):
    PHONES   = "phones",   "Phones & Electronics"
    LIQUOR   = "liquor",   "Liquor / Bar"
    GROCERY  = "grocery",  "Grocery / General"
    PHARMACY = "pharmacy", "Pharmacy"
    CLOTHING = "clothing", "Clothing"


class BaseUnit(models.TextChoices):
    UNIT = "unit", "Unit"     # atomic piece (bread, charger, pack, bottle if no shots)
    SHOT = "shot", "Shot"     # atomic for bars selling shots
    ML   = "ml",   "ml"       # reserved for future use
    G    = "g",    "g"        # reserved for future use


class MerchProduct(models.Model):
    """
    Simple, non-IMEI product used by liquor/grocery/pharmacy/clothing, etc.
    Phones KEEP using the existing Product + InventoryItem models below.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="merch_products", db_index=True)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=BusinessKind.choices, default=BusinessKind.GROCERY)
    sku = models.CharField(max_length=64, blank=True, null=True)
    scan_required = models.BooleanField(default=False)  # set True if you want barcode scanning for some items
    base_unit = models.CharField(max_length=10, choices=BaseUnit.choices, default=BaseUnit.UNIT)
    track_inventory = models.BooleanField(default=True)

    # Liquor helpers
    has_shots = models.BooleanField(default=False)
    shots_per_bottle = models.PositiveIntegerField(null=True, blank=True)

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

    def clean(self):
        if self.has_shots:
            if not self.shots_per_bottle:
                raise ValidationError({"shots_per_bottle": "Required when 'has shots' is enabled."})
            # force atomic to SHOT
            self.base_unit = BaseUnit.SHOT


class MerchUnitPrice(models.Model):
    """
    A sellable pack for a MerchProduct. Converts to base units via multiplier.
    Examples:
      - Grocery: Unit (Ã—1), Dozen (Ã—12), Box (Ã—N)
      - Liquor (shots): Shot (Ã—1), Bottle (Ã—shots_per_bottle)
      - Liquor (no shots): Bottle (Ã—1), Crate (Ã—24)
    """
    class Label(models.TextChoices):
        UNIT   = "unit",   "Unit"
        DOZEN  = "dozen",  "Dozen (12)"
        BOX    = "box",    "Box"
        CRATE  = "crate",  "Crate"
        BOTTLE = "bottle", "Bottle"
        SHOT   = "shot",   "Shot"

    product = models.ForeignKey(MerchProduct, on_delete=models.CASCADE, related_name="unit_prices")
    label = models.CharField(max_length=20, choices=Label.choices)
    multiplier = models.DecimalField(
        max_digits=10, decimal_places=3,
        help_text="How many base units in this pack (e.g., 12 for dozen, 24 for bottle of 24 shots, 1 for unit)."
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = (("product", "label"),)
        indexes = [
            models.Index(fields=["product", "label"], name="merchprice_prod_label_idx"),
        ]

    def __str__(self):
        return f"{self.product.name} Â· {self.get_label_display()} (Ã—{self.multiplier})"


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
class Product(models.Model):
    # FINAL: non-nullable, unique code (backfilled via migration)
    code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SKU/code used in CSV import",
    )
    name = models.CharField(max_length=120, blank=True, help_text="Optional display name")

    brand = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=80)  # âœ… correct
    # e.g., Spark 10C
    variant = models.CharField(max_length=80, blank=True)  # e.g., (4+128)

    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], help_text="Default cost for this product"
    )
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], help_text="Default selling price"
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
        return f"{self.product} â€” MWK {self.default_order_price:,.2f} ({'active' if self.active else 'old'})"

    @staticmethod
    def get_active_price(product_id: int):
        return (
            OrderPrice.objects
            .filter(product_id=product_id, active=True)
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
        return self.filter(is_active=True, status="IN_STOCK")

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
        return (
            self.in_stock()
            .filter(business_id=biz_id, imei=imei)
            .with_related()
            .first()
        )

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
        return (
            qs.values("received_at")
              .order_by("received_at")
              .annotate(count=Count("id"))
        )

    def daily_out(self, start, end):
        """
        Returns rows like: {'day': date, 'count': N}
        """
        qs = self.sold().sold_between(start, end)
        return (
            qs.annotate(day=TruncDate("sold_at"))
              .values("day")
              .order_by("day")
              .annotate(count=Count("id"))
        )

    def totals_in(self, start=None, end=None):
        return self.received_between(start, end).count()

    def totals_out(self, start=None, end=None):
        return self.sold_between(start, end).sold().count()


# -------- Tenant-aware managers (scoped/global) --------
TenantInventoryItemManager = TenantManager.from_queryset(InventoryItemQuerySet)      # scoped
UnscopedInventoryItemManager = UnscopedManager.from_queryset(InventoryItemQuerySet)  # global


class TenantActiveItemManager(TenantInventoryItemManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class InventoryItem(models.Model):
    """
    One physical phone. Use IMEI for scanning. If you ever need to,
    IMEI can be left blank and we still track the device.
    """
    STATUS = [("IN_STOCK", "In stock"), ("SOLD", "Sold")]

    # --- TENANCY ---
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="inventory_items",
        db_index=True,
        null=True,   # keep nullable for migration/backfill; set not null once data is clean
        blank=True,
    )

    imei = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\d{15}$", "IMEI must be exactly 15 digits.")],
        help_text="15-digit IMEI. Unique per business when provided.",
    )
    product = models.ForeignKey("Product", on_delete=models.PROTECT)

    # default today
    received_at = models.DateField(default=timezone.localdate)  # stock-in date

    # give NOT NULL a safe default
    order_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Must be zero or positive.",
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Must be zero or positive when provided.",
    )
    status = models.CharField(max_length=10, choices=STATUS, default="IN_STOCK", db_index=True)
    current_location = models.ForeignKey("Location", on_delete=models.PROTECT, db_index=True)
    assigned_agent = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_items"
    )
    # Soft-delete flag (archive instead of hard delete when needed)
    is_active = models.BooleanField(default=True, db_index=True)

    # ---------- Carlcare warranty/activation tracking ----------
    WARRANTY_CHOICES = [
        ("UNDER_WARRANTY", "Under warranty"),
        ("WAITING_ACTIVATION", "Waiting to be activated"),
        ("NOT_IN_COUNTRY", "Not in country"),
        ("UNKNOWN", "Unknown"),
    ]
    warranty_status = models.CharField(max_length=32, choices=WARRANTY_CHOICES, default="UNKNOWN")
    warranty_expires_at = models.DateField(null=True, blank=True)
    warranty_last_checked_at = models.DateTimeField(null=True, blank=True)
    activation_detected_at = models.DateTimeField(null=True, blank=True)  # first time we saw it activated
    warranty_raw = models.JSONField(null=True, blank=True)  # raw scrape metadata for auditing

    # Marked when a sale is recorded (used by 15-minute theft alert)
    sold_at = models.DateTimeField(null=True, blank=True, db_index=True)  # fast recent-sold lookups
    # ----------------------------------------------------------------

    # Tenant-aware managers
    objects = TenantInventoryItemManager()    # scoped to active tenant (has QuerySet helpers)
    active = TenantActiveItemManager()        # scoped + non-archived
    all_objects = UnscopedInventoryItemManager()  # global/admin (use sparingly)

    class Meta:
        indexes = [
            models.Index(fields=["business", "imei"], name="inv_biz_imei_idx"),
            # Composite for inventory lists â€” name <= 30 chars
            models.Index(
                fields=["business", "product", "current_location", "status"],
                name="inv_bpls_idx",
                condition=Q(is_active=True),
            ),
            models.Index(fields=["business", "is_active", "status"], name="inv_bis_idx"),
            # Warranty lookups
            models.Index(fields=["warranty_status", "warranty_expires_at"], name="inv_wty_stat_exp_idx"),
            # Stock aging
            models.Index(fields=["received_at"], name="inv_received_idx"),
        ]
        constraints = [
            # Per-tenant IMEI uniqueness (only when IMEI present and non-empty)
            models.UniqueConstraint(
                fields=["business", "imei"],
                condition=Q(imei__isnull=False) & ~Q(imei=""),
                name="uniq_imei_per_business",
            ),
            models.CheckConstraint(check=Q(order_price__gte=0), name="inv_order_price_nonneg"),
            models.CheckConstraint(
                check=Q(selling_price__gte=0) | Q(selling_price__isnull=True),
                name="inv_selling_price_nonneg",
            ),
            models.CheckConstraint(check=Q(status__in=["IN_STOCK", "SOLD"]), name="inv_status_allowed"),
            models.CheckConstraint(
                check=Q(product__isnull=False) & Q(current_location__isnull=False),
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

    # --- Compatibility helpers for templates / legacy code ---
    @property
    def location_safe(self):
        """
        Back-compat accessor for templates that previously used `item.location`.
        Prefer `current_location`, but expose a stable name that wonâ€™t break.
        """
        return getattr(self, "current_location", None)

    @property
    def location(self):
        """
        Hard back-compat: many older views/serializers may still access .location.
        Map it to .current_location to prevent AttributeError or select_related errors.
        """
        return getattr(self, "current_location", None)

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

        if self.assigned_agent_id:
            if getattr(self.assigned_agent, "is_staff", False) or getattr(self.assigned_agent, "is_superuser", False):
                errors["assigned_agent"] = "Stock cannot be assigned to admin/staff accounts. Assign to an agent."
            if not hasattr(self.assigned_agent, "agent_profile"):
                errors["assigned_agent"] = "Assigned user must be an agent (has AgentProfile)."

        if errors:
            raise ValidationError(errors)

    # ---- auto-defaults for date/location/sold_at ----
    def save(self, *args, **kwargs):
        # Normalize IMEI again at save-time (defense-in-depth)
        if self.imei:
            self.imei = normalize_imei(self.imei)

        # Ensure received_at is set (field has default, but just in case)
        if not getattr(self, "received_at", None):
            self.received_at = timezone.localdate()

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

        super().save(*args, **kwargs)


# =========================
# Auditing & logs
# =========================
class InventoryAudit(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("EDIT", "Edit"),
        ("EDIT_DENIED", "Edit denied"),
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


class TimeLog(models.Model):
    """Agent arrival/departure logs with optional GPS verification."""
    ARRIVAL = "ARRIVAL"
    DEPARTURE = "DEPARTURE"
    TYPE_CHOICES = [(ARRIVAL, "Arrival"), (DEPARTURE, "Departure")]

    # --- NEW (non-breaking): event for heartbeat semantics ---
    # start | ping | end (optional; we still keep checkin_type for legacy arrivals/departures)
    EVENT_CHOICES = [("start", "Start"), ("ping", "Ping"), ("end", "End")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_logs")
    logged_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)

    # Link to store + GPS fields
    location = models.ForeignKey("Location", null=True, blank=True, on_delete=models.SET_NULL)
    checkin_type = models.CharField(max_length=12, choices=TYPE_CHOICES, default=ARRIVAL)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    within_geofence = models.BooleanField(default=False)

    # --- NEW (non-breaking): textual geofence + event (for analytics/UI) ---
    event = models.CharField(max_length=10, choices=EVENT_CHOICES, blank=True)
    geofence = models.CharField(max_length=8, blank=True)  # "inside" / "outside" (mirrors within_geofence)

    class Meta:
        ordering = ["-logged_at"]
        indexes = [
            models.Index(fields=["user", "logged_at"], name="timelog_user_logged_idx"),
            models.Index(fields=["location", "logged_at"], name="timelog_location_logged_idx"),
            models.Index(fields=["event", "logged_at"], name="timelog_event_logged_idx"),
        ]

    def __str__(self):
        where = self.location.name if (self.location_id and getattr(self.location, "name", None)) else "unknown"
        return f"{self.user} {self.checkin_type} @ {self.logged_at:%Y-%m-%d %H:%M} ({where})"

    @property
    def business(self):
        """Convenience: infer business from location (if set)."""
        return getattr(self.location, "business", None)


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
        return f"Shift #{self.id} Â· {self.user} Â· {self.started_at:%Y-%m-%d %H:%M}"

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
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # + = bonus/credit, âˆ’ = deduction
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
        val = WalletTxn.objects.filter(
            user=user, created_at__gte=start, created_at__lt=end
        ).aggregate(s=Sum("amount"))["s"] or 0
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


# ---- PhoneProduct proxy over phones' Product (for uniform import path) ----
class PhoneProduct(Product):
    class Meta:
        proxy = True
        verbose_name = "Phone Product"
        verbose_name_plural = "Phone Products"






