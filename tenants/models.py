# tenants/models.py
from __future__ import annotations

from typing import Optional
import threading
from contextlib import contextmanager
import uuid
from urllib.parse import quote

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.urls import reverse, NoReverseMatch

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

class Business(models.Model):
    """
    A tenant. Created by a 'manager' (pending approval by staff).
    """
    STATUS_CHOICES = [
        ("PENDING", "Pending staff approval"),
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
    ]

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)

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

    class Meta:
        ordering = ["name"]
        constraints = [
            # Enforce unique subdomain only when non-blank
            models.UniqueConstraint(
                fields=["subdomain"],
                condition=~Q(subdomain=""),
                name="uniq_business_subdomain_nonblank",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return (self.status or "").upper() == "ACTIVE"

    def save(self, *args, **kwargs):
        # Normalize subdomain to lowercase (if provided)
        if self.subdomain:
            self.subdomain = self.subdomain.strip().lower()
        super().save(*args, **kwargs)

    # ---------- Tenant bootstrap ----------

    def seed_defaults(self) -> None:
        """
        Idempotently create per-tenant essentials so new managers land on a 'fresh'
        dashboard with non-empty Stock In pickers.

        Creates:
          - a default Store if none exists
          - a default Warehouse (linked to the default Store if that FK exists)
        Uses apps.get_model to avoid hard dependencies between apps.
        """
        try:
            Store = apps.get_model("inventory", "Store")
            Warehouse = apps.get_model("inventory", "Warehouse")
        except Exception:
            # If inventory app isn't installed, just no-op.
            return

        # Store
        store = (
            Store.all_objects.filter(business=self).order_by("id").first()
            if hasattr(Store, "all_objects")
            else Store.objects.filter(business=self).order_by("id").first()
        )
        if not store:
            kwargs = {"business": self, "name": f"{self.name} Store"}
            if hasattr(Store, "is_default"):
                kwargs["is_default"] = True
            store = (
                Store.all_objects.create(**kwargs)
                if hasattr(Store, "all_objects")
                else Store.objects.create(**kwargs)
            )

        # Warehouse
        wh = (
            Warehouse.all_objects.filter(business=self).order_by("id").first()
            if hasattr(Warehouse, "all_objects")
            else Warehouse.objects.filter(business=self).order_by("id").first()
        )
        if not wh:
            wkwargs = {"business": self, "name": "Main Warehouse"}
            if hasattr(Warehouse, "store"):
                wkwargs["store"] = store
            if hasattr(Warehouse, "is_default"):
                wkwargs["is_default"] = True
            (
                Warehouse.all_objects.create(**wkwargs)
                if hasattr(Warehouse, "all_objects")
                else Warehouse.objects.create(**wkwargs)
            )


class Membership(models.Model):
    """
    User ↔ Business with a role and approval status.
    """
    ROLE_CHOICES = [
        ("MANAGER", "Manager"),
        ("AGENT", "Agent"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("REJECTED", "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = [("user", "business")]
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.business} ({self.role}, {self.status})"


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
    """
    def get_queryset(self):
        qs = super().get_queryset()
        bid = get_current_business_id()
        if bid is None:
            # Safety: if no tenant selected, return nothing (prevents leakage)
            return qs.none()
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
# Agent Invites (new)
# ===============================

class AgentInvite(BaseTenantModel):
    """
    Manager-generated invite that lets an agent create their own account
    and auto-join this Business.

    We keep it intentionally simple:
      - optional invited_name / email / phone
      - a token string to embed in links (signed helper provided)
      - status to track lifecycle
      - joined_user set when someone uses it successfully
      - optional expires_at for auto-expiry
    """
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("JOINED", "Joined"),
        ("EXPIRED", "Expired"),
    ]

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_invites_created",
    )

    # friendly display name for the invitee (works with views that read .invited_name)
    invited_name = models.CharField(max_length=120, blank=True, default="")

    email = models.EmailField(blank=True, default="", db_index=True)
    phone = models.CharField(max_length=32, blank=True, default="", db_index=True)

    # Expanded to allow signed tokens
    token = models.CharField(max_length=140, unique=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING", db_index=True)

    # Filled when an invite link is redeemed and a membership is activated
    joined_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_invites_redeemed",
    )
    joined_at = models.DateTimeField(null=True, blank=True)

    # Optional: manager’s custom message
    message = models.CharField(max_length=240, blank=True, default="")

    # Optional expiry timestamp for UI/auto-expiry convenience
    expires_at = models.DateTimeField(null=True, blank=True)

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
        """Return a human-friendly recipient indicator."""
        return self.email or self.phone or "—"

    @property
    def display_name(self) -> str:
        """Best-effort label for the invitee (name/email/phone fallback)."""
        return (self.invited_name or self.email or self.phone or "").strip()

    # ---- Token helpers (compatible with views.create_agent_invite / accept_invite) ----

    @staticmethod
    def _signer() -> TimestampSigner:
        return TimestampSigner(salt="tenants.AgentInvite")

    @classmethod
    def make_token(cls, payload: str) -> str:
        """
        Return a signed token carrying the payload + timestamp.
        """
        payload = (payload or "").strip() or uuid.uuid4().hex
        return cls._signer().sign(payload)

    @classmethod
    def unsign_token(cls, token: str, *, max_age_seconds: int | None = None) -> str:
        """
        Verify and return the original payload. Raises on failure.
        """
        try:
            if max_age_seconds:
                return cls._signer().unsign(token, max_age=max_age_seconds)
            return cls._signer().unsign(token)
        except SignatureExpired as e:
            # Re-raise so caller can treat as expired
            raise e
        except BadSignature as e:
            raise e

    def ensure_token(self) -> None:
        """Generate a token if missing (idempotent, unsigned fallback)."""
        if not self.token:
            self.token = uuid.uuid4().hex  # 32 chars; unique + compact

    def save(self, *args, **kwargs):
        self.ensure_token()
        super().save(*args, **kwargs)

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
        """
        If expires_at is in the past and status is not already EXPIRED/JOINED,
        set status → EXPIRED. Returns True if a change was made.
        """
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
        """Truthful expiry check that also respects explicit EXPIRED status."""
        if (self.status or "").upper() == "EXPIRED":
            return True
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def is_pending(self) -> bool:
        """
        “Pending” for UI purposes:
        - status is PENDING or SENT
        - not expired
        - not joined
        """
        st = (self.status or "").upper()
        return st in ("PENDING", "SENT") and not self.is_expired() and st != "JOINED"

    def _join_path(self) -> str:
        """
        Reverse the accept URL using the token — never raise.
        Adjust the route name if yours differs.
        """
        try:
            return reverse("tenants:invite_accept", args=[self.token])
        except NoReverseMatch:
            # Safe fallback for dev if URL name changes
            return f"/tenants/invites/accept/{self.token}/"

    def absolute_join_url(self, request) -> str:
        """
        Build an absolute URL robustly, even if Sites framework isn't set up.
        """
        try:
            return request.build_absolute_uri(self._join_path())
        except Exception:
            path = self._join_path()
            host = getattr(request, "get_host", lambda: "localhost")()
            scheme = "https" if getattr(request, "is_secure", lambda: False)() else "http"
            return f"{scheme}://{host}{path}"

    def share_payload(self, request) -> dict[str, str]:
        """
        Centralized share strings/links for Copy, WhatsApp, and Email.
        Keep templates dumb and consistent.
        """
        url = self.absolute_join_url(request)
        tenant_name = getattr(getattr(self, "business", None), "name", "our team")
        name = (self.invited_name or "").strip() or "there"
        text = f"Hi {name}, please click this link to join {tenant_name}: {url}"
        subject = quote(f"Join {tenant_name}")
        body = quote(text)

        return {
            "copy_text": text,
            "url": url,
            "wa_url": f"https://wa.me/?text={body}",
            "mailto_url": f"mailto:?subject={subject}&body={body}",
        }
