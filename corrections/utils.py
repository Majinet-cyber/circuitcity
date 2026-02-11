"""
Corrections Framework Utilities (Feb 2026)
===========================================

Helper functions for corrections framework.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

if TYPE_CHECKING:
    from corrections.registry import EntityConfig
    from tenants.models import Business

logger = logging.getLogger(__name__)


def get_tenant_scoped_queryset(
    model,
    entity_config: 'EntityConfig',
    business: 'Business',
    queryset: Optional[QuerySet] = None,
) -> QuerySet:
    """
    Get a tenant-scoped queryset for a model using the entity's business filter path.
    
    This is the single source of truth for tenant isolation in corrections.
    
    Args:
        model: The Django model class
        entity_config: EntityConfig that defines business_filter_path
        business: The business/tenant to filter by
        queryset: Optional base queryset (defaults to model.objects.all())
    
    Returns:
        QuerySet filtered to the specified business/tenant
    
    Raises:
        PermissionDenied: If no valid tenant path can be found for this model
    
    Examples:
        # Model with direct business field (e.g., GymMember)
        qs = get_tenant_scoped_queryset(GymMember, entity_config, business)
        # Result: GymMember.objects.filter(business=business)
        
        # Model with indirect business via FK (e.g., GymPayment)
        qs = get_tenant_scoped_queryset(GymPayment, entity_config, business)
        # Result: GymPayment.objects.filter(member__business=business)
    """
    if queryset is None:
        queryset = model.objects.all()
    
    # Get the business filter path from entity config
    business_filter_path = getattr(entity_config, 'business_filter_path', 'business')
    
    # Build the filter kwargs
    filter_kwargs = {business_filter_path: business}
    
    # Try to apply the filter
    try:
        return queryset.filter(**filter_kwargs)
    except Exception as e:
        # If the filter fails (e.g., invalid field path), log and raise PermissionDenied
        logger.error(
            f"Corrections: Cannot apply tenant filter '{business_filter_path}' "
            f"to model {model.__name__}: {str(e)}",
            extra={
                'model': model.__name__,
                'business_filter_path': business_filter_path,
                'business_id': business.id if business else None,
            },
            exc_info=True,
        )
        raise PermissionDenied(
            f"Cannot verify tenant access for {model.__name__}. "
            f"This entity may not be properly configured for corrections."
        )


def validate_tenant_access(
    obj,
    entity_config: 'EntityConfig',
    business: 'Business',
) -> bool:
    """
    Validate that an object belongs to the specified business/tenant.
    
    This is a defensive check to ensure tenant isolation.
    
    Args:
        obj: The model instance to check
        entity_config: EntityConfig that defines business_filter_path
        business: The business/tenant to verify against
    
    Returns:
        True if the object belongs to the business, False otherwise
    
    Examples:
        # Direct business field
        validate_tenant_access(gym_member, entity_config, business)
        # Checks: gym_member.business == business
        
        # Indirect business via FK
        validate_tenant_access(gym_payment, entity_config, business)
        # Checks: gym_payment.member.business == business
    """
    business_filter_path = getattr(entity_config, 'business_filter_path', 'business')
    
    try:
        # Navigate the relationship path
        parts = business_filter_path.split('__')
        current = obj
        
        for part in parts:
            current = getattr(current, part, None)
            if current is None:
                logger.warning(
                    f"Corrections: Tenant validation failed - path '{business_filter_path}' "
                    f"is None for {obj.__class__.__name__} #{obj.pk}",
                    extra={
                        'model': obj.__class__.__name__,
                        'object_id': obj.pk,
                        'business_filter_path': business_filter_path,
                    }
                )
                return False
        
        # Current should now be a Business instance
        return current == business
    
    except Exception as e:
        logger.error(
            f"Corrections: Tenant validation error for {obj.__class__.__name__} #{obj.pk}: {str(e)}",
            extra={
                'model': obj.__class__.__name__,
                'object_id': obj.pk,
                'business_filter_path': business_filter_path,
            },
            exc_info=True,
        )
        return False


# Export
__all__ = [
    'get_tenant_scoped_queryset',
    'validate_tenant_access',
]











