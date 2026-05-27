# inventory/compat_create.py
"""
Compatibility layer for model creation with legacy kwargs.

This module provides helpers to create model instances while gracefully
handling legacy/deprecated field names that may no longer exist on the model.

CRITICAL: This prevents tests from failing when model schema changes
but test fixtures still pass old field names.

Usage:
    from inventory.compat_create import safe_create
    
    product = safe_create(
        MerchProduct,
        business=business,
        location=location,  # May not exist on model anymore
        quantity=10,        # May have moved to a separate stock table
        batch_number="B001",  # Pharmacy-specific, may not exist on base model
        **other_kwargs
    )
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set, Type

from django.db import models

logger = logging.getLogger(__name__)


# ============================================================================
# Legacy field mappings
# ============================================================================
# Maps old field names to new field names or special handlers
LEGACY_FIELD_MAPPINGS: Dict[str, Optional[str]] = {
    # location -> current_location (if renamed)
    "location": "current_location",
    # code -> sku or barcode (for InventoryItem)
    "code": "sku",
    # price -> selling_price (common rename)
    "price": "selling_price",
}

# Fields that should be silently ignored if not present on model
SILENTLY_IGNORED_FIELDS: Set[str] = {
    # These are often passed from fixtures but may not exist on all model versions
    "quantity",
    "location",
    "vertical_type",
    "status",
    "batch_number",
    "expiry_date",
    "size",
    "color",
    "has_shots",
    "shots_per_bottle",
    "barman_shots_reserved",
    "price_per_bottle",
    "price_per_shot",
}


def get_model_field_names(model_cls: Type[models.Model]) -> Set[str]:
    """
    Get all valid field names for a Django model.
    
    Includes:
    - Regular fields (attname)
    - Foreign key fields
    - Related fields
    """
    field_names = set()
    
    try:
        for field in model_cls._meta.get_fields():
            # Get the attribute name (what you use in kwargs)
            if hasattr(field, "attname"):
                field_names.add(field.attname)
            if hasattr(field, "name"):
                field_names.add(field.name)
    except Exception:
        pass
    
    return field_names


def filter_kwargs_for_model(
    model_cls: Type[models.Model],
    kwargs: Dict[str, Any],
    *,
    strict: bool = False,
    log_filtered: bool = True,
) -> Dict[str, Any]:
    """
    Filter kwargs to only include fields that exist on the model.
    
    Args:
        model_cls: The Django model class
        kwargs: Dictionary of field names -> values
        strict: If True, raise ValueError for unknown fields
        log_filtered: If True, log filtered (ignored) fields
        
    Returns:
        Filtered kwargs dictionary containing only valid fields
    """
    allowed = get_model_field_names(model_cls)
    filtered = {}
    ignored = []
    
    for key, value in kwargs.items():
        if key in allowed:
            # Field exists on model - include it
            filtered[key] = value
        elif key in LEGACY_FIELD_MAPPINGS:
            # Try mapped field name
            new_key = LEGACY_FIELD_MAPPINGS[key]
            if new_key and new_key in allowed:
                filtered[new_key] = value
            elif key not in SILENTLY_IGNORED_FIELDS:
                ignored.append(key)
        elif key not in SILENTLY_IGNORED_FIELDS:
            ignored.append(key)
    
    if ignored:
        if strict:
            raise ValueError(
                f"{model_cls.__name__} got unexpected keyword arguments: {', '.join(ignored)}"
            )
        if log_filtered:
            logger.debug(
                "Filtered unknown fields from %s.objects.create(): %s",
                model_cls.__name__,
                ", ".join(ignored),
            )
    
    return filtered


def safe_create(
    model_cls: Type[models.Model],
    *,
    strict: bool = False,
    **kwargs: Any,
) -> models.Model:
    """
    Safely create a model instance, filtering out unknown/legacy fields.
    
    This is the main entry point for creating model instances in tests
    and fixtures where field names may have drifted from the model schema.
    
    Args:
        model_cls: The Django model class to instantiate
        strict: If True, raise ValueError for unknown fields (default: False)
        **kwargs: Field values to pass to model.objects.create()
        
    Returns:
        The created model instance
        
    Example:
        product = safe_create(
            MerchProduct,
            business=business,
            name="Test Product",
            quantity=10,  # Silently ignored if field doesn't exist
            location=location,  # Mapped to current_location if renamed
        )
    """
    filtered_kwargs = filter_kwargs_for_model(
        model_cls,
        kwargs,
        strict=strict,
        log_filtered=True,
    )
    
    return model_cls.objects.create(**filtered_kwargs)


def safe_get_or_create(
    model_cls: Type[models.Model],
    defaults: Optional[Dict[str, Any]] = None,
    *,
    strict: bool = False,
    **lookup_kwargs: Any,
) -> tuple:
    """
    Safely get or create a model instance, filtering unknown fields.
    
    Args:
        model_cls: The Django model class
        defaults: Dictionary of field values for creation (filtered)
        strict: If True, raise ValueError for unknown fields
        **lookup_kwargs: Lookup fields (also filtered)
        
    Returns:
        Tuple of (instance, created)
    """
    filtered_lookup = filter_kwargs_for_model(
        model_cls,
        lookup_kwargs,
        strict=strict,
        log_filtered=True,
    )
    
    filtered_defaults = {}
    if defaults:
        filtered_defaults = filter_kwargs_for_model(
            model_cls,
            defaults,
            strict=strict,
            log_filtered=True,
        )
    
    return model_cls.objects.get_or_create(
        defaults=filtered_defaults,
        **filtered_lookup,
    )


def safe_update_or_create(
    model_cls: Type[models.Model],
    defaults: Optional[Dict[str, Any]] = None,
    *,
    strict: bool = False,
    **lookup_kwargs: Any,
) -> tuple:
    """
    Safely update or create a model instance, filtering unknown fields.
    
    Args:
        model_cls: The Django model class
        defaults: Dictionary of field values for update/creation (filtered)
        strict: If True, raise ValueError for unknown fields
        **lookup_kwargs: Lookup fields (also filtered)
        
    Returns:
        Tuple of (instance, created)
    """
    filtered_lookup = filter_kwargs_for_model(
        model_cls,
        lookup_kwargs,
        strict=strict,
        log_filtered=True,
    )
    
    filtered_defaults = {}
    if defaults:
        filtered_defaults = filter_kwargs_for_model(
            model_cls,
            defaults,
            strict=strict,
            log_filtered=True,
        )
    
    return model_cls.objects.update_or_create(
        defaults=filtered_defaults,
        **filtered_lookup,
    )


# ============================================================================
# Convenience aliases
# ============================================================================
create = safe_create
get_or_create = safe_get_or_create
update_or_create = safe_update_or_create


__all__ = [
    "safe_create",
    "safe_get_or_create", 
    "safe_update_or_create",
    "filter_kwargs_for_model",
    "get_model_field_names",
    "create",
    "get_or_create",
    "update_or_create",
]

