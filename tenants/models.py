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
from django.core.exceptions import ValidationError
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
        dashboard with non-empty pickers.

        Creates:
          - a default Location if none exists
          - optionally a default Warehouse if your inventory app defines one
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

    # Default working location for agents (managers may leave this null)
    location = models.ForeignKey(
        "inventory.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
        help_text="Default store/location for this member. Agents must have this set; managers may leave it blank.",
    )

    class Meta:
        # Allow multiple rows per (user, business) as long as location differs.
        # This enables attaching an agent to multiple locations in the same business.
        unique_together = [("user", "business", "location")]
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
        role = (self.role or "").upper()
        if role == "AGENT" and not self.location_id:
            raise ValidationError({"location": "Agents must be assigned to a location."})
        # Optional: keep managers business-wide (no accidental scoping)
        # If you want to allow manager-per-location, comment the block below.
        if role == "MANAGER" and self.location_id:
            raise ValidationError({"location": "Managers should not be tied to a specific location."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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
        ("JOINED", "Joined"),   # treated as "Accepted" in UI
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

    @property
    def ui_status(self) -> str:
        if (self.status or "").upper() == "JOINED":
            return "ACCEPTED"
        if self.is_expired():
            return "EXPIRED"
        return "PENDING"

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
            f"<p>Please click <a href=\"{url}\">here</a> to set your password and join.</p>"
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
