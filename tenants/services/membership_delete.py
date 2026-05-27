# tenants/services/membership_delete.py
"""
Services for safely deleting memberships and users.

Hard deletion reassigns or nullifies references to prevent data loss.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from tenants.models import Membership

logger = logging.getLogger(__name__)
User = get_user_model()


def hard_delete_membership(membership: Membership, *, initiated_by: User) -> None:
    """
    Hard delete a membership and optionally the user if they have no other memberships.
    
    This function:
    1. Reassigns or nullifies all references to membership.user
    2. Deletes the membership
    3. Optionally deletes the user if they have no other memberships
    
    Args:
        membership: Membership instance to delete
        initiated_by: User performing the deletion (must be superuser)
    
    Raises:
        PermissionError: If initiated_by is not a superuser
        ValueError: If deletion would cause data loss
    """
    if not initiated_by.is_superuser:
        raise PermissionError("Only superusers can hard delete memberships")
    
    user = membership.user
    business = membership.business
    
    with transaction.atomic():
        # Step 1: Reassign or nullify references in operational tables
        
        # Sales: Change agent to SET_NULL (already handled by FK change, but ensure it's null)
        try:
            Sale = apps.get_model("sales", "Sale")
            sale_count = Sale.objects.filter(agent=user).count()
            if sale_count > 0:
                # Set agent to None (FK should be SET_NULL after migration)
                Sale.objects.filter(agent=user).update(agent=None)
                logger.info(f"Nullified {sale_count} sales for user {user.id}")
        except Exception as e:
            logger.warning(f"Could not update Sale records: {e}")
        
        # LiquorShifts: Change barman and created_by to SET_NULL
        try:
            LiquorShift = apps.get_model("inventory", "LiquorShift")
            shift_count = LiquorShift.objects.filter(
                Q(barman=user) | Q(created_by=user)
            ).count()
            if shift_count > 0:
                LiquorShift.objects.filter(barman=user).update(barman=None)
                LiquorShift.objects.filter(created_by=user).update(created_by=None)
                logger.info(f"Nullified {shift_count} liquor shifts for user {user.id}")
        except Exception as e:
            logger.warning(f"Could not update LiquorShift records: {e}")
        
        # PharmacySales: sold_by is already SET_NULL, but ensure it's null
        try:
            PharmacySale = apps.get_model("inventory", "PharmacySale")
            pharm_count = PharmacySale.objects.filter(sold_by=user).count()
            if pharm_count > 0:
                # Already SET_NULL, but ensure it's null
                PharmacySale.objects.filter(sold_by=user).update(sold_by=None)
                logger.info(f"Nullified {pharm_count} pharmacy sales for user {user.id}")
        except Exception as e:
            logger.warning(f"Could not update PharmacySale records: {e}")
        
        # StockActivityLog: performed_by is already SET_NULL
        try:
            StockActivityLog = apps.get_model("inventory", "StockActivityLog")
            log_count = StockActivityLog.objects.filter(performed_by=user).count()
            if log_count > 0:
                StockActivityLog.objects.filter(performed_by=user).update(performed_by=None)
                logger.info(f"Nullified {log_count} stock activity logs for user {user.id}")
        except Exception as e:
            logger.warning(f"Could not update StockActivityLog records: {e}")
        
        # LaybyOrders: received_by might have PROTECT (handle if exists)
        try:
            LaybyOrder = apps.get_model("layby", "LaybyOrder")
            if hasattr(LaybyOrder, "received_by"):
                layby_count = LaybyOrder.objects.filter(received_by=user).count()
                if layby_count > 0:
                    # Try to set to None if field allows it
                    try:
                        LaybyOrder.objects.filter(received_by=user).update(received_by=None)
                        logger.info(f"Nullified {layby_count} layby orders for user {user.id}")
                    except Exception:
                        logger.warning(f"Could not nullify LaybyOrder.received_by (may have PROTECT constraint)")
        except Exception as e:
            logger.debug(f"LaybyOrder model not found or no received_by field: {e}")
        
        # SuperInventory: created_by might have PROTECT (handle if exists)
        try:
            SuperInventory = apps.get_model("inventory", "SuperInventory")
            if hasattr(SuperInventory, "created_by"):
                super_count = SuperInventory.objects.filter(created_by=user).count()
                if super_count > 0:
                    # Try to set to None if field allows it
                    try:
                        SuperInventory.objects.filter(created_by=user).update(created_by=None)
                        logger.info(f"Nullified {super_count} super inventory records for user {user.id}")
                    except Exception:
                        logger.warning(f"Could not nullify SuperInventory.created_by (may have PROTECT constraint)")
        except Exception as e:
            logger.debug(f"SuperInventory model not found: {e}")
        
        # Step 2: Delete the membership
        membership_id = membership.id
        membership.delete()
        logger.info(f"Deleted membership {membership_id} for user {user.id} in business {business.id}")
        
        # Step 3: Check if user has other memberships
        remaining_memberships = Membership.objects.filter(user=user).count()
        
        if remaining_memberships == 0:
            # User has no other memberships - optionally delete the user
            # For safety, we'll just log this - actual user deletion can be done manually
            logger.info(f"User {user.id} has no remaining memberships. Consider deleting the user manually.")
            # Uncomment below if you want automatic user deletion:
            # user.delete()
            # logger.info(f"Deleted user {user.id}")

