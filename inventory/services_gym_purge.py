# inventory/services_gym_purge.py
"""
Service for permanently deleting gym members and all related records.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from inventory.models_verticals import (
    GymMember,
    GymPayment,
    GymCheckIn,
    GymMemberLog,
    GymMemberAction,
    GymWalletEntry,
)

User = get_user_model()


def purge_member(
    member: GymMember,
    user: User,
    reason: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Permanently delete a gym member and ALL related records.
    
    This is a destructive operation that:
    1. Collects audit snapshot of member and related records
    2. Deletes all related records in safe order (respecting FK constraints)
    3. Deletes the member record itself
    4. Creates audit log entry
    
    Args:
        member: GymMember instance to purge
        user: User performing the purge (for audit)
        reason: Required reason for purge (e.g., "duplicate", "entered_by_mistake")
        notes: Optional additional notes
    
    Returns:
        Dict with:
            - ok: bool
            - message: str
            - deleted_counts: Dict[str, int]
            - snapshot: Dict (audit data)
    
    Raises:
        ValueError: If reason is empty
    """
    if not reason or not reason.strip():
        raise ValueError("Purge reason is required")
    
    # Collect audit snapshot BEFORE deletion
    snapshot = {
        "member_id": member.id,
        "member_name": member.name,
        "member_phone": member.phone,
        "member_email": member.email,
        "member_number": member.member_number,
        "qr_token": member.qr_token,
        "qr_uuid": str(member.qr_uuid),
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "is_active": member.is_active,
        "is_archived": member.is_archived,
        "trainer_id": member.trainer_id,
        "trainer_name": member.trainer.name if member.trainer else None,
        "membership_start": member.membership_start.isoformat() if member.membership_start else None,
        "membership_end": member.membership_end.isoformat() if member.membership_end else None,
        "total_checkins": member.total_checkins,
        "streak_days": member.streak_days,
        "badge_level": member.badge_level,
    }
    
    # Count related records
    payments_count = GymPayment.all_objects.filter(member=member).count()
    checkins_count = GymCheckIn.objects.filter(member=member).count()
    logs_count = GymMemberLog.objects.filter(member=member).count()
    
    # Count wallet entries linked to member's payments
    wallet_entries_count = GymWalletEntry.objects.filter(
        related_payment__member=member
    ).count()
    
    deleted_counts = {
        "payments": payments_count,
        "checkins": checkins_count,
        "logs": logs_count,
        "wallet_entries": wallet_entries_count,
    }
    
    # Perform deletion in transaction
    with transaction.atomic():
        # 1. Delete wallet entries linked to member's payments
        # (must be done before deleting payments due to FK)
        GymWalletEntry.objects.filter(related_payment__member=member).delete()
        
        # 2. Delete all payments (both soft-deleted and active)
        GymPayment.all_objects.filter(member=member).delete()
        
        # 3. Delete all check-ins
        GymCheckIn.objects.filter(member=member).delete()
        
        # 4. Delete all logs
        # Note: We delete logs last (before member) to preserve audit trail as long as possible
        GymMemberLog.objects.filter(member=member).delete()
        
        # 5. Create final audit log entry BEFORE deleting member
        # This will be deleted immediately after, but serves as a record
        # that the purge was intentional
        audit_log = GymMemberLog.objects.create(
            member=member,
            action="purged",  # Custom action for purge
            changes={
                "reason": reason,
                "notes": notes,
                "deleted_counts": deleted_counts,
                "snapshot": snapshot,
                "purged_by": user.username,
                "purged_at": timezone.now().isoformat(),
            },
            performed_by=user,
        )
        
        # Store audit log data before it's deleted
        audit_log_data = {
            "id": audit_log.id,
            "action": audit_log.action,
            "changes": audit_log.changes,
            "created_at": audit_log.created_at.isoformat(),
        }
        
        # 6. Finally, delete the member record itself
        # This will cascade-delete the audit log we just created
        member_name = member.name
        member_id = member.id
        member.delete()
    
    # Return success with audit data
    return {
        "ok": True,
        "message": f"Member '{member_name}' (ID: {member_id}) and all related records have been permanently deleted.",
        "deleted_counts": deleted_counts,
        "snapshot": snapshot,
        "audit_log": audit_log_data,
        "reason": reason,
        "notes": notes,
        "purged_by": user.username,
        "purged_at": timezone.now().isoformat(),
    }


def can_purge_member(member: GymMember, user: User) -> tuple[bool, Optional[str]]:
    """
    Check if a member can be purged by the given user.
    
    In the gym product, any logged-in user with access to the tenant can purge members.
    Tenant scoping is enforced by the view layer.
    
    Args:
        member: GymMember to check
        user: User attempting the purge
    
    Returns:
        Tuple of (can_purge: bool, error_message: Optional[str])
    """
    # Check if user is authenticated
    # Note: Tenant scoping and business access checks are handled by view decorators
    if not user or not user.is_authenticated:
        return False, "User must be authenticated"
    
    # Member must exist and not be in an invalid state
    if not member or not member.id:
        return False, "Member does not exist"
    
    # No other restrictions - we allow purging members with history
    # (that's the whole point of this feature)
    return True, None

