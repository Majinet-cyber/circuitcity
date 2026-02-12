"""
Corrections Framework - Deletion Services (Feb 2026)
=====================================================

Safe deletion services for correctable entities with audit trail.

This module provides services for deleting records that were created in error
(e.g., duplicate payments, wrong entries) with proper:
- Tenant isolation
- Audit logging
- Related data cleanup (wallet entries, ledger effects)
- Soft delete by default (preserves data for audit)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from inventory.models_verticals import GymPayment, GymWalletEntry
    from tenants.models import Business

logger = logging.getLogger(__name__)


@dataclass
class DeletionResult:
    """Result of a deletion operation."""
    success: bool
    message: str
    errors: list[str] = None
    deleted_object_id: Optional[int] = None
    wallet_entries_removed: int = 0
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class GymPaymentDeletionService:
    """Service for safely deleting gym payments with full audit trail."""
    
    def __init__(self, business: 'Business', user: 'User'):
        """
        Initialize deletion service.
        
        Args:
            business: The business/tenant context
            user: The user performing the deletion
        """
        self.business = business
        self.user = user
        self.logger = logging.getLogger(f"{__name__}.GymPaymentDeletionService")
    
    def delete_payment(
        self,
        payment: 'GymPayment',
        reason: str,
        notes: str = "",
        hard_delete: bool = False,
    ) -> DeletionResult:
        """
        Delete a gym payment safely with audit trail.
        
        This method:
        1. Validates tenant access
        2. Creates a snapshot for audit
        3. Reverses wallet entries
        4. Soft-deletes the payment (or hard-deletes if specified)
        5. Logs the action
        
        Args:
            payment: The GymPayment instance to delete
            reason: Required reason for deletion (e.g., 'duplicate', 'wrong_member')
            notes: Optional additional notes
            hard_delete: If True, permanently delete (default: False = soft delete)
        
        Returns:
            DeletionResult with success status and details
        """
        from inventory.models_verticals import GymWalletEntry
        from corrections.models import CorrectionAuditLog
        
        # Validate inputs
        if not reason or not reason.strip():
            return DeletionResult(
                success=False,
                message="Deletion reason is required",
                errors=["reason_missing"],
            )
        
        # Validate tenant access
        if payment.member.business != self.business:
            self.logger.warning(
                f"Attempted to delete payment #{payment.pk} from another tenant. "
                f"Payment business: {payment.member.business.id}, "
                f"User business: {self.business.id}",
                extra={
                    'payment_id': payment.pk,
                    'payment_business_id': payment.member.business.id,
                    'user_business_id': self.business.id,
                    'user_id': self.user.id,
                }
            )
            return DeletionResult(
                success=False,
                message="Payment not found or access denied",
                errors=["tenant_mismatch"],
            )
        
        # Check if already deleted
        if payment.is_deleted:
            return DeletionResult(
                success=True,
                message=f"Payment #{payment.pk} was already deleted",
                deleted_object_id=payment.pk,
            )
        
        # Create snapshot for audit trail
        snapshot = {
            'id': payment.pk,
            'member_id': payment.member.id,
            'member_name': payment.member.name,
            'membership_amount': str(payment.membership_amount),
            'trainer_fee': str(payment.trainer_fee),
            'amount': str(payment.amount) if payment.amount else None,
            'payment_method': payment.payment_method,
            'start_date': payment.start_date.isoformat(),
            'end_date': payment.end_date.isoformat(),
            'paid_at': payment.paid_at.isoformat(),
            'paid_by_id': payment.paid_by.id if payment.paid_by else None,
            'trainer_id': payment.trainer.id if payment.trainer else None,
            'notes': payment.notes,
        }
        
        try:
            with transaction.atomic():
                # 1. Find and remove related wallet entries
                wallet_entries = GymWalletEntry.objects.filter(
                    business=self.business,
                    related_payment=payment,
                )
                wallet_count = wallet_entries.count()
                
                if wallet_count > 0:
                    self.logger.info(
                        f"Deleting {wallet_count} wallet entries for payment #{payment.pk}",
                        extra={
                            'payment_id': payment.pk,
                            'wallet_entries_count': wallet_count,
                        }
                    )
                    
                    # Store wallet entry details in snapshot
                    snapshot['wallet_entries'] = [
                        {
                            'id': entry.id,
                            'amount': str(entry.amount),
                            'description': entry.description,
                            'entry_type': entry.entry_type,
                            'created_at': entry.created_at.isoformat(),
                        }
                        for entry in wallet_entries
                    ]
                    
                    # Delete wallet entries (hard delete - they're derived data)
                    wallet_entries.delete()
                
                # 2. Soft delete or hard delete the payment
                if hard_delete:
                    payment_id = payment.pk
                    payment.delete()
                    self.logger.info(
                        f"Hard-deleted payment #{payment_id}",
                        extra={'payment_id': payment_id}
                    )
                else:
                    # Soft delete
                    payment.is_deleted = True
                    payment.deleted_at = timezone.now()
                    payment.deleted_by = self.user
                    payment.delete_reason = reason[:100]  # Truncate to field max
                    payment.delete_notes = notes
                    payment.save(update_fields=[
                        'is_deleted',
                        'deleted_at',
                        'deleted_by',
                        'delete_reason',
                        'delete_notes',
                    ])
                    self.logger.info(
                        f"Soft-deleted payment #{payment.pk}",
                        extra={'payment_id': payment.pk}
                    )
                
                # 3. Create audit log
                CorrectionAuditLog.objects.create(
                    business=self.business,
                    batch=None,  # Deletion is not part of a correction batch
                    item=None,
                    performed_by=self.user,
                    action='gym_payment_deleted',
                    details={
                        'payment_id': payment.pk if not hard_delete else snapshot['id'],
                        'reason': reason,
                        'notes': notes,
                        'hard_delete': hard_delete,
                        'snapshot': snapshot,
                        'wallet_entries_removed': wallet_count,
                    },
                )
                
                return DeletionResult(
                    success=True,
                    message=f"Payment #{payment.pk} deleted successfully",
                    deleted_object_id=payment.pk if not hard_delete else snapshot['id'],
                    wallet_entries_removed=wallet_count,
                )
        
        except Exception as e:
            self.logger.error(
                f"Failed to delete payment #{payment.pk}: {str(e)}",
                extra={
                    'payment_id': payment.pk,
                    'reason': reason,
                },
                exc_info=True,
            )
            return DeletionResult(
                success=False,
                message=f"Failed to delete payment: {str(e)}",
                errors=[str(e)],
            )


# Export
__all__ = [
    'DeletionResult',
    'GymPaymentDeletionService',
]













