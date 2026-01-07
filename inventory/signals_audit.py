# inventory/signals_audit.py
"""
Signal handlers for stock audit trail.

Automatically logs all stock activities for HQ visibility.
"""
from __future__ import annotations

import logging
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver

log = logging.getLogger(__name__)


def _get_request_meta(instance):
    """
    Try to get request metadata from instance if available.
    Returns tuple: (user, ip_address, user_agent)
    """
    user = None
    ip_address = None
    user_agent = ""

    # Try to get from instance if it has a request cached
    if hasattr(instance, "_request"):
        request = instance._request
        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        # Get IP
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0]
        else:
            ip_address = request.META.get("REMOTE_ADDR")

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    return user, ip_address, user_agent


def _should_log_stock_activity(instance):
    """
    Determine if this instance should be logged.

    Skip logging for:
    - Models that aren't stock-related
    - Test/fixture data (if we can detect it)
    """
    model_name = instance.__class__.__name__

    # Only log certain models
    stock_models = [
        "InventoryItem",
        "MerchProduct",
        "PhoneStock",
        "ClothingProduct",
        "LiquorProduct",
        "PharmacyProduct",
    ]

    return model_name in stock_models


# =============================================================================
# STOCK CREATION/UPDATE LOGGING
# =============================================================================


@receiver(post_save, sender="inventory.InventoryItem")
def log_inventory_item_activity(sender, instance, created, **kwargs):
    """Log when inventory items are created or updated."""
    if not _should_log_stock_activity(instance):
        return

    try:
        from .models_audit import StockActivityLog, StockAction

        # Get business
        business = getattr(instance, "business", None)
        if not business:
            return

        # Get location
        location = getattr(instance, "current_location", None)

        # Get user from request if available
        user, ip_address, user_agent = _get_request_meta(instance)

        # Determine action
        action = StockAction.CREATE if created else StockAction.UPDATE

        # Get product name
        product = getattr(instance, "product", None)
        product_name = product.name if product and hasattr(product, "name") else str(instance)

        # Get IMEI if it's a phone
        imei = getattr(instance, "imei", "") or getattr(instance, "serial_number", "")

        # Log the activity
        StockActivityLog.log_activity(
            business=business,
            action=action,
            product_model=sender.__name__,
            product_id=instance.pk,
            performed_by=user,
            location=location,
            product_name=product_name,
            imei=imei if imei else "",
            ip_address=ip_address,
            user_agent=user_agent,
            note=f"{'Created' if created else 'Updated'} stock item",
        )

        log.info(f"Logged {action} for {product_name} (#{instance.pk})")

    except Exception as e:
        log.exception(f"Failed to log stock activity: {e}")


# =============================================================================
# PREVENT HARD DELETES & LOG ATTEMPTS
# =============================================================================


@receiver(pre_delete, sender="inventory.InventoryItem")
def prevent_hard_delete_and_log(sender, instance, **kwargs):
    """
    Prevent hard deletion of stock items and log the attempt.

    Note: This raises an exception to block the delete.
    Soft deletes should be done by setting is_active=False.
    """
    # Check if this is a soft delete (is_active was set to False)
    if hasattr(instance, "is_active") and not instance.is_active:
        # Allow soft delete to proceed
        try:
            from .models_audit import StockActivityLog, StockAction

            business = getattr(instance, "business", None)
            if business:
                user, ip_address, user_agent = _get_request_meta(instance)
                product = getattr(instance, "product", None)
                product_name = product.name if product and hasattr(product, "name") else str(instance)

                StockActivityLog.log_activity(
                    business=business,
                    action=StockAction.SOFT_DELETE,
                    product_model=sender.__name__,
                    product_id=instance.pk,
                    performed_by=user,
                    location=getattr(instance, "current_location", None),
                    product_name=product_name,
                    imei=getattr(instance, "imei", "") or getattr(instance, "serial_number", ""),
                    note="Soft deleted (is_active=False)",
                )
        except Exception as e:
            log.exception(f"Failed to log soft delete: {e}")

        return  # Allow the update to proceed

    # Otherwise, this is a hard delete attempt - block it
    try:
        from .models_audit import StockActivityLog, StockAction
        from django.core.exceptions import ValidationError

        business = getattr(instance, "business", None)
        if business:
            user, ip_address, user_agent = _get_request_meta(instance)
            product = getattr(instance, "product", None)
            product_name = product.name if product and hasattr(product, "name") else str(instance)

            # Log the delete attempt
            StockActivityLog.log_activity(
                business=business,
                action=StockAction.DELETE_ATTEMPT,
                product_model=sender.__name__,
                product_id=instance.pk,
                performed_by=user,
                location=getattr(instance, "current_location", None),
                product_name=product_name,
                imei=getattr(instance, "imei", "") or getattr(instance, "serial_number", ""),
                note=f"Hard delete attempted by {user.username if user else 'Unknown'}",
            )

            log.warning(
                f"Blocked hard delete attempt on {product_name} (#{instance.pk}) "
                f"by {user.username if user else 'Unknown'}"
            )

        # Raise exception to block the delete
        raise ValidationError(
            "Hard deletion of stock is not allowed. "
            "Use soft delete (set is_active=False) instead. "
            "Contact HQ if deletion is absolutely necessary."
        )
    except ValidationError:
        raise  # Re-raise validation error
    except Exception as e:
        log.exception(f"Error in delete prevention: {e}")
        # Still raise to block delete even if logging fails
        raise ValidationError("Stock deletion blocked for audit compliance.")


# =============================================================================
# IMEI UNIQUENESS VALIDATION
# =============================================================================


def validate_imei_uniqueness(instance):
    """
    Ensure IMEI is globally unique across all businesses and agents.

    Called in the model's save() method or via signal.
    """
    imei = getattr(instance, "imei", None) or getattr(instance, "serial_number", None)

    if not imei:
        return  # No IMEI to validate

    # Normalize IMEI
    from .models import normalize_imei

    imei_clean = normalize_imei(imei)

    if not imei_clean:
        return

    # Check for duplicates
    model = instance.__class__
    existing = model.objects.filter(Q(imei=imei_clean) | Q(serial_number=imei_clean)).exclude(pk=instance.pk)

    if existing.exists():
        duplicate = existing.first()
        raise ValidationError(
            f"This IMEI ({imei_clean}) already exists in the system. "
            f"Found on: {duplicate} (ID: {duplicate.pk}). "
            f"Search for it instead of stocking it again."
        )


# Wire up IMEI validation
@receiver(pre_delete, sender="inventory.InventoryItem")
def validate_imei_on_save(sender, instance, **kwargs):
    """Validate IMEI uniqueness before saving."""
    # Only validate if instance has IMEI field
    if hasattr(instance, "imei") or hasattr(instance, "serial_number"):
        validate_imei_uniqueness(instance)
