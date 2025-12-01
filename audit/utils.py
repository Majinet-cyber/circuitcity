# audit/utils.py
"""
Utility functions for audit logging.
"""
from typing import Optional
from django.http import HttpRequest
from .models import AuditLog


def get_client_ip(request: HttpRequest) -> Optional[str]:
    """Extract client IP from request, considering proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request: HttpRequest) -> str:
    """Extract user agent from request."""
    return request.META.get('HTTP_USER_AGENT', '')[:500]  # Truncate to fit


def log_audit(
    request: HttpRequest,
    action: str,
    entity: str = '',
    entity_id: str = '',
    message: str = ''
) -> Optional[AuditLog]:
    """
    Create an audit log entry.
    
    Args:
        request: Django request object
        action: Type of action (VIEW, EXPORT, UPDATE, DELETE, etc.)
        entity: Type of entity being accessed (e.g., 'InventoryItem', 'Business')
        entity_id: ID/identifier of the entity
        message: Human-readable message
    
    Returns:
        AuditLog instance if successful, None otherwise
    """
    try:
        business = getattr(request, 'business', None)
        if not business:
            # Try to get from session
            from tenants.utils import get_active_business
            business = get_active_business(request)
        
        # Skip if no business context (e.g., public pages)
        if not business:
            return None
        
        log = AuditLog.objects.create(
            business=business,
            user=request.user if request.user.is_authenticated else None,
            entity=entity[:64],
            entity_id=str(entity_id)[:64],
            action=action[:64],
            message=message,
            ip=get_client_ip(request),
            ua=get_user_agent(request)
        )
        return log
    except Exception as e:
        # Log to console but don't break the application
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create audit log: {e}")
        return None


def log_model_action(request: HttpRequest, instance, action: str, message: str = ''):
    """
    Log an action on a model instance.
    
    Args:
        request: Django request object
        instance: Model instance
        action: Action type (CREATE, UPDATE, DELETE, etc.)
        message: Optional message
    """
    entity = instance.__class__.__name__
    entity_id = str(getattr(instance, 'pk', ''))
    
    if not message:
        message = f"{action} {entity} {entity_id}"
    
    return log_audit(request, action, entity, entity_id, message)
