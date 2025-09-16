# tenants/models.py
from __future__ import annotations

from typing import Optional
import threading
from contextlib import contextmanager

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

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
        store = Store.all_objects.filter(business=self).order_by("id").first() \
            if hasattr(Store, "all_objects") else Store.objects.filter(business=self).order_by("id").first()
        if not store:
            kwargs = {"business": self, "name": f"{self.name} Store"}
            if hasattr(Store, "is_default"):
                kwargs["is_default"] = True
            store = Store.all_objects.create(**kwargs) if hasattr(Store, "all_objects") else Store.objects.create(**kwargs)

        # Warehouse
        wh = Warehouse.all_objects.filter(business=self).order_by("id").first() \
            if hasattr(Warehouse, "all_objects") else Warehouse.objects.filter(business=self).order_by("id").first()
        if not wh:
            wkwargs = {"business": self, "name": "Main Warehouse"}
            if hasattr(Warehouse, "store"):
                wkwargs["store"] = store
            if hasattr(Warehouse, "is_default"):
                wkwargs["is_default"] = True
            (Warehouse.all_objects.create(**wkwargs)
             if hasattr(Warehouse, "all_objects") else Warehouse.objects.create(**wkwargs))


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
        if not self.business_id:
            bid = get_current_business_id()
            if bid:
                self.business_id = bid
        super().save(*args, **kwargs)
