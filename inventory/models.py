# inventory/models.py
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

# --- Tenancy imports (explicit) ---
from tenants.models import Business, TenantManager, UnscopedManager  # NEW

import json
import secrets
import string

User = get_user_model()


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

    class Meta:
        unique_together = (("business", "name"),)
        indexes = [
            models.Index(fields=["business", "name"], name="loc_biz_name_idx"),
            models.Index(fields=["city"], name="loc_city_idx"),
        ]

    def __str__(self):
        label = self.name
        if self.business_id:
            label = f"{label} · {getattr(self.business, 'name', self.business_id)}"
        return label


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
    model = models.CharField(max_length=80)                # e.g., Spark 10C
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
        return f"{self.product} — MWK {self.default_order_price:,.2f} ({'active' if self.active else 'old'})"

    @staticmethod
    def get_active_price(product_id: int):
        return (
            OrderPrice.objects
            .filter(product_id=product_id, active=True)
            .values_list("default_order_price", flat=True)
            .first()
        )


# =========================
# Inventory
# =========================
class InventoryItemQuerySet(models.QuerySet):
    def with_related(self):
        """Pull common FKs to prevent N+1s in views/admin/templates."""
        return self.select_related("product", "current_location", "assigned_agent")

    def in_stock(self):
        return self.filter(is_active=True, status="IN_STOCK")

    def sold(self):
        return self.filter(status="SOLD")


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
    received_at = models.DateField()  # stock-in date
    order_price = models.DecimalField(
        max_digits=12, decimal_places=2,
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
            # Composite for inventory lists — name <= 30 chars
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

    def clean(self):
        errors = {}

        if self.status == "SOLD" and not self.sold_at:
            errors["sold_at"] = "sold_at is required when status is SOLD."

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
        return "".join(secrets.choice(string.digits) for _ in range(6))


class TimeLog(models.Model):
    """Agent arrival/departure logs with optional GPS verification."""
    ARRIVAL = "ARRIVAL"
    DEPARTURE = "DEPARTURE"
    TYPE_CHOICES = [(ARRIVAL, "Arrival"), (DEPARTURE, "Departure")]

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

    class Meta:
        ordering = ["-logged_at"]
        indexes = [
            models.Index(fields=["user", "logged_at"], name="timelog_user_logged_idx"),
            models.Index(fields=["location", "logged_at"], name="timelog_location_logged_idx"),
        ]

    def __str__(self):
        where = self.location.name if self.location_id else "unknown"
        return f"{self.user} {self.checkin_type} @ {self.logged_at:%Y-%m-%d %H:%M} ({where})"


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
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # + = bonus/credit, − = deduction
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
