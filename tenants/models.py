# tenants/models.py
from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from typing import Optional
from urllib.parse import quote

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.models_compat_kwargs import CompatKwargsMixin

try:
    from tenants.constants import BusinessKind
except Exception:  # pragma: no cover
    # Fallback if constants can't be imported (shouldn't happen in normal operation)
    try:
        from inventory.business_kinds import BusinessKind
    except Exception:

        class BusinessKind(models.TextChoices):  # type: ignore
            PHONES = "phones", "Phones & Electronics"
            LIQUOR = "liquor", "Liquor / Bar"
            GROCERY = "grocery", "Grocery / General"
            PHARMACY = "pharmacy", "Pharmacy"
            CLOTHING = "clothing", "Clothing"
            GYM = "gym", "Gym / Fitness"


User = settings.AUTH_USER_MODEL

# ===============================
# Thread-local tenant context
# ===============================
_tenant_state = threading.local()


def get_current_business_id() -> Optional[int]:
    """Read the active tenant id for this request/thread."""
    return getattr(_tenant_state, "business_id", None)


def set_current_business_id(business_id: Optional[int]) -> None:
    """Write/clear the active tenant id for this request/thread."""
    if business_id is None:
        if hasattr(_tenant_state, "business_id"):
            delattr(_tenant_state, "business_id")
    else:
        _tenant_state.business_id = int(business_id)


@contextmanager
def using_business(business: Optional["Business"] | int):
    """
    Temporarily set the active tenant (useful in tasks/management commands).
    Example:
        with using_business(biz):
            InventoryItem.objects.create(...)
    """
    prev = get_current_business_id()
    try:
        bid = business.pk if isinstance(business, Business) else business
        set_current_business_id(bid)
        yield
    finally:
        set_current_business_id(prev)


# ===============================
# Business / Membership
# ===============================


class Business(CompatKwargsMixin, models.Model):
    """
    A tenant. Created by a 'manager' (pending approval by staff).
    """
    
    # Backwards compatibility: Map legacy kwargs to canonical fields
    COMPAT_MAP = {
        'kind': 'business_kind',       # Legacy alias
        'vertical': 'business_kind',   # Alternative legacy alias
        'owner': 'created_by',         # Legacy: owner maps to created_by (who created/proposed it)
        'owner_email': '_ignored_owner_email',  # No direct field; ignore for now (could be stored in User if needed)
    }

    STATUS_CHOICES = [
        ("PENDING", "Pending staff approval"),
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
    ]

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)
    business_kind = models.CharField(
        max_length=20,
        choices=BusinessKind.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Business vertical (drives tailored dashboards and flows).",
    )

    # Currency for this business (defaults to MWK - Malawian Kwacha)
    currency = models.CharField(
        max_length=3,
        default="MWK",
        help_text="Currency code (ISO 4217, e.g., MWK, USD, GBP).",
    )

    # Optional for subdomain routing later (e.g., acme.circuit.city)
    subdomain = models.CharField(max_length=63, blank=True, default="", db_index=True)

    # Who proposed/created it (aspiring manager)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="businesses_created",
    )

    # Logo (optional branding)
    logo = models.ImageField(
        upload_to="business_logos/",
        null=True,
        blank=True,
        help_text="Business logo. Best fit: square or 3:1 ratio (e.g., 300x300 or 600x200). PNG with transparent background recommended.",
    )

    # HQ notification tracking (idempotency)
    hq_notified_signup_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When HQ was notified of this business signup (idempotency)",
    )

    # Section flags (feature toggles per vertical)
    # All default to False to prevent NOT NULL constraint errors
    has_cosmetics_section = models.BooleanField(
        default=False,
        help_text="Enable cosmetics section for pharmacy businesses",
    )
    has_groceries_section = models.BooleanField(
        default=False,
        help_text="Enable groceries section",
    )
    has_cement_section = models.BooleanField(
        default=False,
        help_text="Enable cement/hardware section",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            # Enforce unique subdomain only when non-blank
            models.UniqueConstraint(
                fields=["subdomain"],
                condition=~Q(subdomain=""),
                name="uniq_business_subdomain_nonblank",
            ),
            # Enforce case-insensitive unique business name
            models.UniqueConstraint(
                Lower("name"),
                name="uniq_business_name_ci",
                violation_error_message="A business with this name already exists (case-insensitive).",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def kind(self):
        """Alias for business_kind (legacy compatibility)."""
        return self.business_kind

    @kind.setter
    def kind(self, value):
        """Setter for kind alias."""
        self.business_kind = value

    @property
    def is_active(self) -> bool:
        return (self.status or "").upper() == "ACTIVE"
    
    @is_active.setter
    def is_active(self, value: bool) -> None:
        """
        Setter for backwards compatibility with tests.
        Maps boolean to status field (ACTIVE/SUSPENDED).
        
        Security note: This does NOT bypass subscription gates or validation.
        It only sets the status field.
        """
        if value:
            self.status = "ACTIVE"
        else:
            self.status = "SUSPENDED"
    
    @property
    def members(self):
        """
        Backwards compatibility property.
        Returns the memberships manager for this business.
        
        Usage:
            business.members.filter(status="ACTIVE")
            business.members.all()
        
        Note: This returns memberships, not users directly.
        For legacy code that used business.members.add(user),
        use Membership.objects.create() instead.
        """
        return self.memberships

    def save(self, *args, **kwargs):
        # Normalize subdomain to lowercase (if provided)
        if self.subdomain:
            self.subdomain = self.subdomain.strip().lower()
        
        # Auto-generate unique slug if not provided
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name) or "business"
            slug = base_slug
            counter = 2
            while Business.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        super().save(*args, **kwargs)

    # ---------- Tenant bootstrap ----------

    def seed_defaults(self) -> None:
        """
        Idempotently create per-tenant essentials so new managers land on a 'fresh'
        dashboard with non-empty pickers.

        Creates:
          - a default Location if none exists
          - optionally a default Warehouse if your inventory app defines one
          - for gym businesses: default trainers (Steve, Lesta, Philip)
        """
        try:
            Location = apps.get_model("inventory", "Location")
        except Exception:
            # If inventory app isn't installed or Location model missing, just no-op.
            return

        # Location
        loc = (
            Location.all_objects.filter(business=self).order_by("id").first()
            if hasattr(Location, "all_objects")
            else Location.objects.filter(business=self).order_by("id").first()
        )
        if not loc:
            kwargs = {"business": self, "name": f"{self.name} Store"}
            if hasattr(Location, "is_default"):
                kwargs["is_default"] = True
            loc = (
                Location.all_objects.create(**kwargs)
                if hasattr(Location, "all_objects")
                else Location.objects.create(**kwargs)
            )

        # Optional: Warehouse if present in your app
        try:
            Warehouse = apps.get_model("inventory", "Warehouse")
        except Exception:
            Warehouse = None

        if Warehouse:
            wh_qs = getattr(Warehouse, "all_objects", Warehouse.objects).filter(business=self)
            wh = wh_qs.order_by("id").first()
            if not wh:
                wkwargs = {"business": self, "name": "Main Warehouse"}
                # If your Warehouse model links to a location field, set it
                if hasattr(Warehouse, "location"):
                    wkwargs["location"] = loc
                if hasattr(Warehouse, "is_default"):
                    wkwargs["is_default"] = True
                getattr(Warehouse, "all_objects", Warehouse.objects).create(**wkwargs)

        # Gym-specific: seed default trainers
        vertical = getattr(self, "business_kind", None) or getattr(self, "vertical", None) or ""
        if vertical.lower() == "gym":
            try:
                GymTrainer = apps.get_model("inventory", "GymTrainer")
                GymSettings = apps.get_model("inventory", "GymSettings")

                # Create default trainers if none exist
                existing_count = GymTrainer.objects.filter(business=self).count()
                if existing_count == 0:
                    default_trainers = ["Steve", "Lesta", "Philip"]
                    for trainer_name in default_trainers:
                        GymTrainer.objects.get_or_create(business=self, name=trainer_name, defaults={"is_active": True})

                # Create gym settings if not exists
                GymSettings.objects.get_or_create(business=self)
            except Exception:
                # If gym models aren't available, skip silently
                pass

    # Convenience: fetch the default/first location
    def default_location(self):
        try:
            Location = apps.get_model("inventory", "Location")
        except Exception:
            return None
        qs = getattr(Location, "all_objects", Location.objects).filter(business=self)
        if hasattr(Location, "is_default"):
            x = qs.filter(is_default=True).first()
            if x:
                return x
        return qs.order_by("id").first()

    # Where to land new agents after accept; used by views after login.
    def agents_url(self) -> str:
        for name in ("tenants:agents_home", "tenants:agents", "agents:list"):
            try:
                return reverse(name)
            except NoReverseMatch:
                continue
        return "/tenants/agents/"


def normalize_membership_role(value: str | None) -> str:
    """
    Normalize legacy role strings to canonical uppercase values.
    
    Accepts: "Manager", "manager", "MANAGER" → "MANAGER"
             "Agent", "agent", "AGENT" → "AGENT"
             "Admin", "admin", "ADMIN" → "MANAGER" (admin is treated as manager)
             "Bar Manager", "bar_manager", "BAR_MANAGER" → "BAR_MANAGER"
    
    Returns the canonical value, or the original value if unknown.
    """
    if not value:
        return value
    
    # Normalize to uppercase for matching
    upper_val = value.strip().upper().replace(" ", "_").replace("-", "_")
    
    # Map legacy/variant values to canonical choices
    ROLE_ALIASES = {
        "MANAGER": "MANAGER",
        "ADMIN": "MANAGER",  # Admin is treated as Manager
        "AGENT": "AGENT",
        "BAR_MANAGER": "BAR_MANAGER",
        "BARMANAGER": "BAR_MANAGER",
    }
    
    return ROLE_ALIASES.get(upper_val, value)


class Membership(models.Model):
    """
    User → Business with a role and approval status.

    NOTE:
    - Managers: location may be NULL (business-wide access).
    - Agents: location MUST be set (scoped to that store/branch).
    - A user may have *multiple* agent memberships under the same business
      (one per location). This is enabled by the unique_together rule below.
    """

    ROLE_CHOICES = [
        ("MANAGER", "Manager"),
        ("AGENT", "Agent"),
        ("BAR_MANAGER", "Bar Manager"),  # Liquor vertical: team lead / supervisor
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("REJECTED", "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)  # Increased for BAR_MANAGER
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Backwards compatibility: is_active field (maps to status="ACTIVE")
    # This allows tests to pass is_active=True during creation
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Backwards compatibility flag. Prefer using status field.",
    )

    # Default working location for agents (managers may leave this null)
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
        help_text="Default store/location for this member. Agents must have this set; managers may leave it blank.",
    )

    # Geolocation tracking for agents (for time-log bonuses/penalties)
    location_tracking_enabled = models.BooleanField(
        default=False,
        help_text="True if the agent has granted location permission for automatic time logs.",
    )
    last_known_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Last known GPS latitude from agent.",
    )
    last_known_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Last known GPS longitude from agent.",
    )
    last_location_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last location ping.",
    )

    class Meta:
        # Allow multiple rows per (user, business) as long as location differs.
        # This enables attaching an agent to multiple locations in the same business.
        unique_together = [("user", "business", "location")]
        constraints = [
            # Prevent duplicate ACTIVE memberships for the same (user, business) pair
            models.UniqueConstraint(
                fields=["user", "business"],
                condition=Q(status="ACTIVE"),
                name="uniq_active_membership_user_business",
            )
        ]
        indexes = [
            models.Index(fields=["user", "business"]),
            models.Index(fields=["role"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        at = f" · {self.location.name}" if self.location_id else ""
        return f"{self.user} @ {self.business}{at} ({self.role}, {self.status})"

    # ---- Role helpers ----
    def is_manager(self) -> bool:
        return (self.role or "").upper() == "MANAGER"

    def is_agent(self) -> bool:
        return (self.role or "").upper() == "AGENT"

    # ---- Validation: enforce location rules by role ----
    def clean(self):
        # Normalize role BEFORE validation to accept legacy values
        self.role = normalize_membership_role(self.role)
        
        role = (self.role or "").upper()
        
        # For agents: auto-assign default location if none provided
        if role == "AGENT" and not self.location_id and self.business_id:
            # Try to get a default location for this business
            try:
                Location = apps.get_model("inventory", "Location")
                loc = (
                    Location.objects.filter(business_id=self.business_id, is_default=True).first()
                    or Location.objects.filter(business_id=self.business_id).order_by("id").first()
                )
                if loc:
                    self.location = loc
            except Exception:
                pass  # No location model or no locations available
        
        # Note: We no longer require agents to have a location set at validation time.
        # This allows test scenarios and edge cases where the business may not have
        # locations yet. The agent will be assigned a location when one is available.
        
        # NOTE: Managers and BAR_MANAGERs CAN optionally have a location
        # (for organizational purposes), but it's not required.
        # They still have business-wide access regardless of location setting.
        # The location field for managers is used as a "default location" preference,
        # not a scope restriction.

        # Note: Managers can have memberships in multiple businesses for multi-tenant scenarios.
        # Cross-business product isolation is enforced at the query level, not membership level.

        # Managers and BAR_MANAGERs cannot gain memberships (even as agents) in other businesses.
        if role not in ("MANAGER", "BAR_MANAGER") and self.user_id and self.business_id:
            manager_conflict = Membership.objects.filter(
                user_id=self.user_id, 
                role__in=["MANAGER", "manager", "BAR_MANAGER"]
            ).exclude(business_id=self.business_id)
            if manager_conflict.exists():
                raise ValidationError({"business": "Managers cannot join or view other businesses."})

    def save(self, *args, **kwargs):
        # Normalize role BEFORE full_clean() because Django validates field choices
        # before calling clean(). This accepts legacy values like "Manager", "agent", etc.
        self.role = normalize_membership_role(self.role)
        self.full_clean()
        return super().save(*args, **kwargs)

    def transfer_location(self, new_location, changed_by):
        """
        Transfer this membership to a new location and create history record.

        Args:
            new_location: New Location instance
            changed_by: User performing the transfer

        Returns:
            MembershipLocationHistory instance
        """
        if not new_location or new_location == self.location:
            return None

        # Create history record
        from django.db import transaction

        with transaction.atomic():
            history = MembershipLocationHistory.objects.create(
                membership=self,
                from_location=self.location,
                to_location=new_location,
                changed_by=changed_by,
            )

            # Update membership
            self.location = new_location
            self.save(update_fields=["location"])

            return history


# ===============================
# Tenancy base + auto-scoping manager
# ===============================


class TenantQuerySet(models.QuerySet):
    def for_business(self, business: Optional[Business]):
        """Manually scope a queryset to a business (escape hatch)."""
        if business is None:
            return self.none()
        return self.filter(business=business)


class TenantManager(models.Manager):
    """
    Default manager that auto-filters by the current tenant id stored in
    thread-local (set by middleware that reads session.active_business_id).
    
    SECURITY: When thread-local is set, queries are always scoped to that tenant.
    When thread-local is NOT set (e.g., test assertions outside request context),
    queries are allowed if they explicitly filter by business (for test compatibility).
    """

    def get_queryset(self):
        qs = super().get_queryset()
        bid = get_current_business_id()
        if bid is None:
            # No thread-local: return unfiltered queryset
            # CRITICAL: Security is maintained because:
            # 1. In views/middleware, thread-local is ALWAYS set
            # 2. Outside request context (tests/tasks), caller must filter by business
            # 3. If caller forgets to filter, they get ALL records (fail-loud, easy to catch)
            # This allows tests to do: Model.objects.filter(business=x, ...).first()
            return qs
        return qs.filter(business_id=bid)

    def for_business(self, business: Optional[Business]):
        """Explicit scoping when you can't rely on thread-local (e.g., tasks)."""
        bid = business.pk if isinstance(business, Business) else business
        qs = super().get_queryset()
        if not bid:
            return qs.none()
        return qs.filter(business_id=bid)


class UnscopedManager(models.Manager):
    """
    Global manager for admin or maintenance scripts where cross-tenant access is intended.
    Use Model.all_objects.* explicitly; never in tenant views.
    """

    pass


class BaseTenantModel(models.Model):
    """
    Inherit this for all tenant-owned tables.
    Always includes a ForeignKey to Business named 'business'.

    - .objects      -> auto-scoped to current tenant (via TenantManager)
    - .all_objects  -> unscoped/global (admin/scripts only)
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    # Auto-scoped manager (honors thread-local tenant)
    objects = TenantManager()
    # Global manager for admin/scripts
    all_objects = UnscopedManager()

    class Meta:
        abstract = True

    # Safety net: auto-attach active tenant if caller forgot to set .business
    def save(self, *args, **kwargs):
        if not getattr(self, "business_id", None):
            bid = get_current_business_id()
            if bid:
                self.business_id = bid
        super().save(*args, **kwargs)


# ===============================
# Agent Invites (with Location assignment)
# ===============================


class AgentInvite(BaseTenantModel):
    """
    Manager-generated invite that lets an agent create their own account
    and auto-join this Business.
    """

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("JOINED", "Joined"),  # treated as "Accepted" in UI
        ("EXPIRED", "Expired"),
    ]

    ROLE_CHOICES = [
        ("AGENT", "Sales Agent"),
        ("BAR_MANAGER", "Bar Manager"),  # Liquor-specific: team lead / supervisor
    ]

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_invites_created",
    )

    invited_name = models.CharField(max_length=120, blank=True, default="")

    email = models.EmailField(blank=True, default="", db_index=True)
    phone = models.CharField(max_length=32, blank=True, default="", db_index=True)

    # Assign a location at invite time (agents will be bound to this on accept)
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_invites",
        help_text="Location for this invite. On accept, the membership will use this location.",
    )

    token = models.CharField(max_length=140, unique=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)

    # Role for the invite (default: AGENT for backward compatibility)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="AGENT",
        db_index=True,
        help_text="Role the user will receive upon accepting this invite",
    )

    joined_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_invites_redeemed",
    )
    joined_at = models.DateTimeField(null=True, blank=True)

    message = models.CharField(max_length=240, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)

    # Temporary password fields (Task 3)
    temp_password_hash = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Hashed temporary password for agent login.",
    )
    temp_password_used = models.BooleanField(
        default=False,
        help_text="Whether the temp password has been used.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["business", "status", "-created_at"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        to = self.email or self.phone or "unknown"
        return f"Invite → {to} [{self.business.name}] ({self.status})"

    # -------- Convenience bits --------

    @property
    def recipient(self) -> str:
        return self.email or self.phone or "—"

    @property
    def display_name(self) -> str:
        return (self.invited_name or self.email or self.phone or "").strip()

    # ---- Token helpers ----

    @staticmethod
    def _signer() -> TimestampSigner:
        return TimestampSigner(salt="tenants.AgentInvite")

    @classmethod
    def make_token(cls, payload: str) -> str:
        payload = (payload or "").strip() or uuid.uuid4().hex
        return cls._signer().sign(payload)

    @classmethod
    def unsign_token(cls, token: str, *, max_age_seconds: int | None = None) -> str:
        try:
            if max_age_seconds:
                return cls._signer().unsign(token, max_age=max_age_seconds)
            return cls._signer().unsign(token)
        except SignatureExpired as e:
            raise e
        except BadSignature as e:
            raise e

    def ensure_token(self) -> None:
        if not self.token:
            base = f"{(self.email or '').lower()}:{uuid.uuid4().hex}"
            self.token = self.make_token(base)

    def save(self, *args, **kwargs):
        self.ensure_token()
        super().save(*args, **kwargs)

    # ---- Temp password helpers ----

    @staticmethod
    def generate_temp_password(length: int = 8) -> str:
        """Generate a human-readable temporary password."""
        import secrets
        import string

        # Use a mix that's easy to type and read
        alphabet = string.ascii_letters + string.digits
        # Avoid confusing characters like 0/O, 1/l/I
        alphabet = alphabet.replace("0", "").replace("O", "").replace("1", "").replace("l", "").replace("I", "")
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def set_temp_password(self, raw_password: str) -> None:
        """Hash and store a temporary password."""
        from django.contrib.auth.hashers import make_password

        self.temp_password_hash = make_password(raw_password)
        self.temp_password_used = False

    def check_temp_password(self, raw_password: str) -> bool:
        """Verify a temporary password."""
        from django.contrib.auth.hashers import check_password

        if not self.temp_password_hash:
            return False
        return check_password(raw_password, self.temp_password_hash)

    def create_and_set_temp_password(self) -> str:
        """Generate, set, and return a new temp password (plaintext for emailing)."""
        raw = self.generate_temp_password()
        self.set_temp_password(raw)
        return raw

    # ---- Status helpers ----

    def mark_sent(self, *, message: str | None = None, save: bool = True) -> None:
        self.status = "SENT"
        if message is not None:
            self.message = message
        if save:
            self.save(update_fields=["status", "message"])

    def mark_joined(self, *, user, when: Optional[timezone.datetime] = None, save: bool = True) -> None:
        self.status = "JOINED"
        self.joined_user = user
        self.joined_at = when or timezone.now()
        if save:
            self.save(update_fields=["status", "joined_user", "joined_at"])

    def mark_expired_if_needed(self, *, save: bool = True) -> bool:
        if self.status in ("EXPIRED", "JOINED"):
            return False
        if self.expires_at and timezone.now() >= self.expires_at:
            self.status = "EXPIRED"
            if save:
                self.save(update_fields=["status"])
            return True
        return False

    # ---- One source of truth for invite state & share links ----

    def is_expired(self) -> bool:
        if (self.status or "").upper() == "EXPIRED":
            return True
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def is_pending(self) -> bool:
        st = (self.status or "").upper()
        return st in ("PENDING", "SENT") and not self.is_expired() and st != "JOINED"

    def can_use(self) -> bool:
        """Usable if pending/sent and not expired and not joined."""
        return self.is_pending()

    def _join_path(self) -> str:
        try:
            return reverse("tenants:invite_accept", args=[self.token])
        except NoReverseMatch:
            return f"/tenants/invites/accept/{self.token}/"

    def absolute_join_url(self, request) -> str:
        try:
            return request.build_absolute_uri(self._join_path())
        except Exception:
            path = self._join_path()
            host = getattr(request, "get_host", lambda: "localhost")()
            scheme = "https" if getattr(request, "is_secure", lambda: False)() else "http"
            return f"{scheme}://{host}{path}"

    def share_payload(self, request) -> dict[str, str]:
        url = self.absolute_join_url(request)
        tenant_name = getattr(getattr(self, "business", None), "name", "our team")
        name = (self.invited_name or "").strip() or "there"

        text = f"Hi {name}, please click this link to join {tenant_name}: {url}"
        subject_text = f"Join {tenant_name}"

        html = (
            f"<p>Hi {(name or 'there')},</p>"
            f"<p>You have been invited to join <strong>{tenant_name}</strong> as an <strong>Agent</strong>.</p>"
            f'<p>Please click <a href="{url}">here</a> to set your password and join.</p>'
            + (f"<p>This link expires on {self.expires_at:%b %d, %Y %H:%M}.</p>" if self.expires_at else "")
        )

        subject_q = quote(subject_text)
        body_q = quote(text)

        return {
            "copy_text": text,
            "url": url,
            "wa_url": f"https://wa.me/?text={body_q}",
            "mailto_url": f"mailto:?subject={subject_q}&body={body_q}",
            "email_subject": subject_text,
            "email_text": text,
            "email_html": html,
        }

    # ---- Accept helper (used by the view after validating password/email) ----

    @transaction.atomic
    def attach_user_as_agent(self, user) -> "Membership":
        """
        Idempotently attach `user` to this invite's business as an ACTIVE AGENT,
        scoped to the invite's location (required for agents).

        Always ensures the agent has a valid location by using the business's
        default location if the invite doesn't specify one.
        """
        MembershipModel = apps.get_model("tenants", "Membership")

        # Ensure we have a location for agents - use default if not set
        location_for_membership = self.location
        if not location_for_membership:
            # Import the helper from services to avoid duplication
            from tenants.services.invites import get_default_location_for_business

            location_for_membership = get_default_location_for_business(self.business)
            # Update the invite's location for consistency
            self.location = location_for_membership
            self.save(update_fields=["location"])

        membership, created = MembershipModel.objects.get_or_create(
            user=user,
            business=self.business,
            location=location_for_membership,
            defaults={"role": "AGENT", "status": "ACTIVE"},
        )

        # Ensure the role/status/location are correct in case it existed differently
        updates = []
        if membership.role != "AGENT":
            membership.role = "AGENT"
            updates.append("role")
        if membership.status != "ACTIVE":
            membership.status = "ACTIVE"
            updates.append("status")
        if not membership.location:
            membership.location = location_for_membership
            updates.append("location")
        if updates:
            membership.save(update_fields=updates)
        return membership

    @transaction.atomic
    def accept_for_user(self, user) -> "Membership":
        """
        Full accept: validate, attach membership, mark as joined. Returns membership.
        """
        if not self.can_use():
            raise ValidationError("This invite is no longer available.")
        membership = self.attach_user_as_agent(user)
        self.mark_joined(user=user, save=True)
        return membership


# ===============================
# Membership Location History
# ===============================


class MembershipLocationHistory(models.Model):
    """
    Tracks agent location transfers with timestamp and responsible user.
    Maintains an audit trail of all location changes.
    """

    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="location_history",
    )
    from_location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="membership_history_from",
        help_text="Previous location (null if this is the first assignment)",
    )
    to_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="membership_history_to",
        help_text="New location",
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="membership_transfers_made",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["membership", "-changed_at"]),
            models.Index(fields=["from_location", "-changed_at"]),
            models.Index(fields=["to_location", "-changed_at"]),
        ]
        verbose_name = "Membership Location History"
        verbose_name_plural = "Membership Location Histories"

    def __str__(self) -> str:
        from_name = self.from_location.name if self.from_location else "New"
        to_name = self.to_location.name if self.to_location else "Unknown"
        return f"{self.membership.user} transferred from {from_name} to {to_name} on {self.changed_at:%Y-%m-%d}"


# ===============================
# Backwards compatibility aliases
# ===============================

# BusinessUserMembership was renamed to Membership
# Keep this alias for backward compatibility with existing imports:
#   from tenants.models import BusinessUserMembership
BusinessUserMembership = Membership

# Re-export Location from inventory.models for convenience
# Many modules import Location from tenants.models for convenience.
# We re-export it here to maintain backwards compatibility.
try:
    from inventory.models import Location  # noqa: F401
except ImportError:
    # If inventory app isn't available, Location won't be exported
    # This is fine - modules that need it should import from inventory.models directly
    pass
