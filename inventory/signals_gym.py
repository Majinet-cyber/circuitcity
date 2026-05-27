# inventory/signals_gym.py
"""
Signal handlers for gym vertical operations.
Handles automatic email notifications for gym member lifecycle events.
"""
from __future__ import annotations

import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="inventory.GymMember")
def send_welcome_email_on_member_creation(sender, instance, created, **kwargs):
    """
    Send welcome email with QR code when a new gym member is created.
    
    This signal ensures emails are sent reliably for all creation paths:
    - UI form (member_add view)
    - Bulk import (bulk_create_members service)
    - Admin panel
    - API endpoints
    
    Idempotency: Only sends on creation (created=True), not on updates.
    Graceful degradation: Silently skips if email is missing/blank.
    Transaction safety: Uses transaction.on_commit to ensure DB commit before sending.
    """
    # Only send on creation, not updates
    if not created:
        return
    
    # Skip if no email
    if not instance.email or not instance.email.strip():
        logger.debug(f"Skipping welcome email for member {instance.id} (no email)")
        return
    
    # Skip if explicitly disabled (for migrations, bulk operations that handle emails separately)
    if getattr(instance, '_skip_welcome_email', False):
        logger.debug(f"Skipping welcome email for member {instance.id} (_skip_welcome_email flag)")
        return
    
    try:
        from inventory.services.gym_qr_email import send_member_qr_email
        
        # Capture member_id to avoid closure issues
        member_id = instance.id
        
        # Send email after transaction commits (ensures member is saved to DB)
        # Note: No request object available in signal, so PDF won't be attached
        # The view layer can still call send_member_qr_email with request for PDF
        transaction.on_commit(
            lambda: _send_welcome_email_safe(member_id)
        )
        
        logger.info(f"Scheduled welcome email for member {instance.id} ({instance.name})")
        
    except Exception as e:
        # Don't break member creation if email fails
        logger.error(
            f"Failed to schedule welcome email for member {instance.id}: {e}",
            exc_info=True
        )


def _send_welcome_email_safe(member_id: int) -> None:
    """
    Safely send welcome email to a gym member.
    
    This is a separate function to ensure proper error handling and logging.
    Called from transaction.on_commit to ensure DB consistency.
    """
    try:
        from inventory.models_verticals import GymMember
        from inventory.services.gym_qr_email import send_member_qr_email
        
        # Fetch member from DB (ensures we have committed data)
        try:
            member = GymMember.objects.get(id=member_id)
        except GymMember.DoesNotExist:
            logger.error(f"Member {member_id} not found when trying to send welcome email")
            return
        
        # Double-check email still exists (defensive)
        if not member.email or not member.email.strip():
            logger.debug(f"Member {member_id} has no email, skipping welcome email")
            return
        
        # Send email (no request object, so no PDF attachment)
        success = send_member_qr_email(member, request=None)
        
        if success:
            logger.info(f"Welcome email sent successfully to {member.email} for member {member_id}")
        else:
            logger.warning(f"Welcome email failed to send to {member.email} for member {member_id}")
            
    except Exception as e:
        # Log but don't raise - email failures shouldn't break the application
        logger.error(
            f"Error sending welcome email for member {member_id}: {e}",
            exc_info=True
        )

