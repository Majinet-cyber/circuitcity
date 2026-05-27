"""
Schema safety utilities to prevent 500 errors when database migrations haven't been applied yet.
"""
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist


def model_has_field(model, field_name):
    """
    Check if a model has a specific field defined.
    
    Args:
        model: Django model class
        field_name: Name of the field to check
        
    Returns:
        bool: True if the field exists on the model, False otherwise
    """
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def require_field(model, field_name, operation_name=None):
    """
    Ensure a field exists on a model, raising helpful error in DEBUG mode.
    
    Args:
        model: Django model class
        field_name: Name of the field to check
        operation_name: Description of what operation needs this field (for error message)
        
    Raises:
        RuntimeError: In DEBUG mode if field doesn't exist
        
    Returns:
        bool: True if field exists, False otherwise
    """
    if not model_has_field(model, field_name):
        model_name = model.__name__
        app_label = model._meta.app_label
        db_table = model._meta.db_table
        
        error_msg = (
            f"Missing database field: {model_name}.{field_name}\n"
            f"Database table: {db_table}\n"
            f"App: {app_label}\n\n"
            f"This field is required for: {operation_name or 'this operation'}\n\n"
            f"To fix this issue:\n"
            f"1. Run: python manage.py makemigrations {app_label}\n"
            f"2. Run: python manage.py migrate {app_label}\n"
            f"3. Restart the server\n"
        )
        
        if settings.DEBUG:
            raise RuntimeError(error_msg)
        else:
            # In production, log the error but don't crash
            import logging
            logger = logging.getLogger(__name__)
            logger.error(error_msg)
            return False
    
    return True


def safe_filter_by_field(queryset, field_name, **filter_kwargs):
    """
    Safely filter a queryset by a field that might not exist in the database yet.
    
    Args:
        queryset: Django queryset to filter
        field_name: Name of the field to filter by
        **filter_kwargs: Filter arguments (e.g., name_canonical="john doe")
        
    Returns:
        QuerySet: Filtered queryset if field exists, original queryset otherwise
    """
    model = queryset.model
    if model_has_field(model, field_name):
        return queryset.filter(**filter_kwargs)
    else:
        if settings.DEBUG:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Skipping filter on {model.__name__}.{field_name} - field doesn't exist in database yet. "
                f"Run migrations."
            )
        return queryset


def safe_order_by_field(queryset, field_name, *other_fields):
    """
    Safely order a queryset by a field that might not exist in the database yet.
    
    Args:
        queryset: Django queryset to order
        field_name: Name of the field to order by (can include '-' prefix for descending)
        *other_fields: Additional fallback ordering fields
        
    Returns:
        QuerySet: Ordered queryset if field exists, fallback ordering otherwise
    """
    model = queryset.model
    # Strip the '-' prefix to check field existence
    clean_field_name = field_name.lstrip('-')
    
    if model_has_field(model, clean_field_name):
        return queryset.order_by(field_name, *other_fields)
    else:
        if settings.DEBUG:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Skipping order_by on {model.__name__}.{clean_field_name} - field doesn't exist in database yet. "
                f"Using fallback ordering."
            )
        # Use fallback ordering if provided
        if other_fields:
            return queryset.order_by(*other_fields)
        return queryset

