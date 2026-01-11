# tenants/scoping.py
"""
Tenant Scoping Helpers (Single Source of Truth for IDOR Prevention)
====================================================================

This module provides secure helpers for tenant-scoped object access.
ALWAYS use these helpers instead of raw `Model.objects.get(pk=...)` to prevent IDOR vulnerabilities.

Usage:
    from tenants.scoping import scoped_get_object_or_404, get_business, get_location

    # In views:
    sale = scoped_get_object_or_404(Sale, request, pk=sale_id)
    item = scoped_get_object_or_404(InventoryItem, request, pk=item_id, location_required=True)

Key Principles:
1. Business scope is MANDATORY for all tenant-scoped models
2. Location scope is enforced when `location_required=True`
3. Returns 404 for cross-tenant access (never 403 - prevents enumeration)
4. Never performs unscoped `.get(pk=...)` on tenant data
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar, Union

from django.db.models import Model, QuerySet
from django.http import Http404

if TYPE_CHECKING:
    from django.http import HttpRequest
    from tenants.models import Business
    from inventory.models import Location

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Model)


# --------------------------------------------------------------------------------------
# Core Scope Helpers
# --------------------------------------------------------------------------------------

def get_business(request: "HttpRequest") -> Optional["Business"]:
    """
    Get the active business from request context.
    
    Resolution order:
    1. request.business (set by TenantResolutionMiddleware)
    2. tenants.services.active_business.get_active_business()
    3. session['active_business_id']
    
    Returns None if no business context is available.
    """
    # 1. Middleware-set business (preferred)
    business = getattr(request, "business", None)
    if business is not None:
        return business
    
    # 2. SSOT service
    try:
        from tenants.services.active_business import get_active_business
        business = get_active_business(request)
        if business:
            return business
    except ImportError:
        pass
    
    # 3. Legacy: session-based lookup
    try:
        from tenants.models import Business
        bid = request.session.get("active_business_id")
        if bid:
            return Business.objects.filter(pk=bid, status="ACTIVE").first()
    except Exception:
        pass
    
    return None


def get_location(request: "HttpRequest") -> Optional["Location"]:
    """
    Get the active location from request context.
    
    Resolution order:
    1. For agents: their membership.location (hard lock)
    2. For managers: ?location query param or session, validated against business
    3. Default location for business
    
    Returns None if no location context is available or model not present.
    """
    try:
        from tenants.scope import resolve_location_for_user
        from inventory.models import Location
        
        loc_id = resolve_location_for_user(request)
        if loc_id:
            return Location.objects.filter(pk=loc_id).first()
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error resolving location: {e}")
    
    return None


def get_business_id(request: "HttpRequest") -> Optional[int]:
    """Get the active business ID (convenience wrapper)."""
    business = get_business(request)
    return business.id if business else None


def get_location_id(request: "HttpRequest") -> Optional[int]:
    """Get the active location ID (convenience wrapper)."""
    location = get_location(request)
    return location.id if location else None


# --------------------------------------------------------------------------------------
# Model Introspection Helpers
# --------------------------------------------------------------------------------------

def _model_has_field(model: Type[Model], field_name: str) -> bool:
    """Check if model has a specific field."""
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _get_business_field_name(model: Type[Model]) -> Optional[str]:
    """
    Determine the field name used for business FK on a model.
    Returns 'business', 'store__business', 'location__business', etc.
    """
    # Direct business FK
    if _model_has_field(model, "business"):
        return "business"
    
    # Via item relationship (for Sale model)
    if _model_has_field(model, "item"):
        try:
            item_field = model._meta.get_field("item")
            related_model = item_field.related_model
            if related_model and _model_has_field(related_model, "business"):
                return "item__business"
        except Exception:
            pass
    
    # Via store relationship
    if _model_has_field(model, "store"):
        return "store__business"
    
    # Via warehouse relationship
    if _model_has_field(model, "warehouse"):
        return "warehouse__business"
    
    # Via location relationship
    if _model_has_field(model, "location"):
        return "location__business"
    
    # Via current_location (InventoryItem)
    if _model_has_field(model, "current_location"):
        return "current_location__business"
    
    return None


def _get_location_field_name(model: Type[Model]) -> Optional[str]:
    """Determine the field name used for location FK on a model."""
    if _model_has_field(model, "location"):
        return "location"
    if _model_has_field(model, "current_location"):
        return "current_location"
    return None


# --------------------------------------------------------------------------------------
# Core Scoping Function
# --------------------------------------------------------------------------------------

def apply_tenant_scope(
    qs: QuerySet,
    business: Optional["Business"],
    *,
    location: Optional["Location"] = None,
    location_required: bool = False,
) -> QuerySet:
    """
    Apply tenant scope (business + optional location) to a queryset.
    
    Args:
        qs: The queryset to scope
        business: The active business (required for filtering)
        location: Optional location for additional filtering
        location_required: If True and model has location field, filter by location
    
    Returns:
        Scoped queryset. Returns qs.none() if business is None.
    
    Example:
        qs = apply_tenant_scope(Sale.objects.all(), request.business)
    """
    if business is None:
        return qs.none()
    
    model = qs.model
    
    # Apply business scope
    biz_field = _get_business_field_name(model)
    if biz_field:
        if biz_field == "business":
            qs = qs.filter(business=business)
        else:
            qs = qs.filter(**{biz_field: business})
    
    # Apply location scope if required
    if location_required and location:
        loc_field = _get_location_field_name(model)
        if loc_field:
            qs = qs.filter(**{f"{loc_field}_id": location.id})
    
    return qs


# --------------------------------------------------------------------------------------
# Scoped get_object_or_404 (THE PRIMARY IDOR-SAFE HELPER)
# --------------------------------------------------------------------------------------

def scoped_get_object_or_404(
    model: Type[T],
    request: "HttpRequest",
    *,
    pk: Optional[int] = None,
    id: Optional[int] = None,  # noqa: A002 - alias for pk
    extra_filters: Optional[Dict[str, Any]] = None,
    location_required: bool = False,
    select_related: Optional[list] = None,
    prefetch_related: Optional[list] = None,
) -> T:
    """
    Secure tenant-scoped get_object_or_404.
    
    ALWAYS use this instead of Django's get_object_or_404 for tenant-scoped models.
    
    Args:
        model: The Django model class
        request: The HTTP request (must have business context)
        pk: Primary key of the object (alias: id)
        extra_filters: Additional filter kwargs (e.g., {"status": "ACTIVE"})
        location_required: If True, also scope by location
        select_related: Optional list of relations to select_related
        prefetch_related: Optional list of relations to prefetch_related
    
    Returns:
        The model instance if found and belongs to the tenant.
    
    Raises:
        Http404: If object not found OR belongs to a different tenant.
                 (Never returns 403 to prevent enumeration attacks)
    
    Example:
        sale = scoped_get_object_or_404(Sale, request, pk=sale_id)
        item = scoped_get_object_or_404(
            InventoryItem, request, 
            pk=item_id, 
            location_required=True,
            select_related=["product", "location"]
        )
    """
    # Normalize pk/id
    object_pk = pk or id
    if object_pk is None:
        raise Http404(f"{model.__name__} not found")
    
    # Get business context (REQUIRED)
    business = get_business(request)
    if business is None:
        # No business context = no access to any tenant data
        logger.warning(
            f"scoped_get_object_or_404: No business context for {model.__name__} pk={object_pk}"
        )
        raise Http404(f"{model.__name__} not found")
    
    # Get location context if required
    location = get_location(request) if location_required else None
    
    # Build queryset
    qs = model.objects.all()
    
    # Apply select_related / prefetch_related
    if select_related:
        qs = qs.select_related(*select_related)
    if prefetch_related:
        qs = qs.prefetch_related(*prefetch_related)
    
    # Apply tenant scope
    qs = apply_tenant_scope(qs, business, location=location, location_required=location_required)
    
    # Apply extra filters
    if extra_filters:
        qs = qs.filter(**extra_filters)
    
    # Final lookup
    try:
        return qs.get(pk=object_pk)
    except model.DoesNotExist:
        # Log potential IDOR attempt (object exists but in different tenant)
        if model.objects.filter(pk=object_pk).exists():
            logger.warning(
                f"IDOR attempt blocked: {model.__name__} pk={object_pk} "
                f"requested by business_id={business.id}"
            )
        raise Http404(f"{model.__name__} not found")


def scoped_get_or_none(
    model: Type[T],
    request: "HttpRequest",
    *,
    pk: Optional[int] = None,
    id: Optional[int] = None,  # noqa: A002
    extra_filters: Optional[Dict[str, Any]] = None,
    location_required: bool = False,
) -> Optional[T]:
    """
    Like scoped_get_object_or_404 but returns None instead of raising Http404.
    
    Useful when you want to handle missing objects differently.
    """
    try:
        return scoped_get_object_or_404(
            model, request,
            pk=pk, id=id,
            extra_filters=extra_filters,
            location_required=location_required,
        )
    except Http404:
        return None


# --------------------------------------------------------------------------------------
# Queryset Scoping Helpers
# --------------------------------------------------------------------------------------

def scoped_queryset(
    model: Type[T],
    request: "HttpRequest",
    *,
    location_required: bool = False,
    select_related: Optional[list] = None,
    prefetch_related: Optional[list] = None,
) -> QuerySet[T]:
    """
    Get a tenant-scoped queryset for a model.
    
    Use for list views and filtered queries.
    
    Example:
        sales = scoped_queryset(Sale, request).filter(status="completed")
    """
    business = get_business(request)
    location = get_location(request) if location_required else None
    
    qs = model.objects.all()
    
    if select_related:
        qs = qs.select_related(*select_related)
    if prefetch_related:
        qs = qs.prefetch_related(*prefetch_related)
    
    return apply_tenant_scope(qs, business, location=location, location_required=location_required)


# --------------------------------------------------------------------------------------
# Ownership Assertion (Defense in Depth)
# --------------------------------------------------------------------------------------

def assert_tenant_ownership(
    obj: Model,
    request: "HttpRequest",
    *,
    location_check: bool = False,
) -> None:
    """
    Assert that an object belongs to the current tenant.
    
    Use as defense-in-depth after lookups that may not be pre-scoped.
    
    Raises:
        Http404: If object belongs to a different tenant.
    
    Example:
        sale = Sale.objects.get(pk=pk)  # Legacy code
        assert_tenant_ownership(sale, request)  # Add this check
    """
    business = get_business(request)
    if business is None:
        raise Http404("Object not found")
    
    # Check business ownership
    obj_business_id = None
    
    if hasattr(obj, "business_id"):
        obj_business_id = obj.business_id
    elif hasattr(obj, "item") and hasattr(obj.item, "business_id"):
        obj_business_id = obj.item.business_id
    elif hasattr(obj, "location") and hasattr(obj.location, "business_id"):
        obj_business_id = obj.location.business_id
    elif hasattr(obj, "current_location") and hasattr(obj.current_location, "business_id"):
        obj_business_id = obj.current_location.business_id
    
    if obj_business_id is not None and obj_business_id != business.id:
        logger.warning(
            f"IDOR attempt blocked via assert_tenant_ownership: "
            f"{obj.__class__.__name__} pk={obj.pk} "
            f"(belongs to business_id={obj_business_id}, requested by business_id={business.id})"
        )
        raise Http404("Object not found")
    
    # Check location ownership if required
    if location_check:
        location = get_location(request)
        if location:
            obj_location_id = getattr(obj, "location_id", None) or getattr(obj, "current_location_id", None)
            if obj_location_id is not None and obj_location_id != location.id:
                raise Http404("Object not found")


# --------------------------------------------------------------------------------------
# Bind Business to New Objects
# --------------------------------------------------------------------------------------

def bind_business_to_object(obj: Model, request: "HttpRequest") -> Model:
    """
    Stamp an object with the active business before saving.
    
    Use for create flows to guarantee tenant ownership.
    
    Example:
        sale = Sale(price=100, ...)
        bind_business_to_object(sale, request)
        sale.save()
    """
    business = get_business(request)
    if business is None:
        raise Http404("No active business context")
    
    if hasattr(obj, "business") and getattr(obj, "business_id", None) is None:
        obj.business = business
    
    return obj


# --------------------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------------------

__all__ = [
    # Core scope getters
    "get_business",
    "get_location",
    "get_business_id",
    "get_location_id",
    # Primary IDOR-safe helpers
    "scoped_get_object_or_404",
    "scoped_get_or_none",
    "scoped_queryset",
    # Queryset scoping
    "apply_tenant_scope",
    # Defense in depth
    "assert_tenant_ownership",
    "bind_business_to_object",
]
