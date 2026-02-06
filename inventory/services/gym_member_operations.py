"""
Service functions for gym member operations: merge, dedupe, bulk create.

These functions ensure data integrity and history preservation when managing members.
"""
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from inventory.models_verticals import (
    GymCheckIn,
    GymMember,
    GymMemberAction,
    GymMemberLog,
    GymPayment,
    normalize_member_name,
)
from tenants.models import Business

User = get_user_model()
logger = logging.getLogger(__name__)


def merge_members(
    source_member: GymMember,
    target_member: GymMember,
    user: User,
    reason: str,
    notes: str = "",
) -> Dict[str, any]:
    """
    Merge a duplicate member into a canonical member.
    
    All history (payments, check-ins, logs) is preserved by repointing
    from source → target. Source is then soft-deleted.
    
    Args:
        source_member: The duplicate member to merge away
        target_member: The canonical member to keep
        user: User performing the merge
        reason: Reason for merge (e.g., "duplicate", "auto_dedupe")
        notes: Optional additional notes
        
    Returns:
        Dict with merge statistics:
        {
            "payments_moved": int,
            "checkins_moved": int,
            "logs_moved": int,
            "source_id": int,
            "target_id": int,
            "duplicate_checkins_removed": int,
        }
        
    Raises:
        ValueError: If members are from different businesses or source == target
    """
    if source_member.id == target_member.id:
        raise ValueError("Cannot merge a member into itself")
    
    if source_member.business_id != target_member.business_id:
        raise ValueError("Cannot merge members from different businesses")
    
    stats = {
        "payments_moved": 0,
        "checkins_moved": 0,
        "logs_moved": 0,
        "duplicate_checkins_removed": 0,
        "source_id": source_member.id,
        "target_id": target_member.id,
    }
    
    with transaction.atomic():
        # 1. Repoint all payments
        payments = GymPayment.objects.filter(member=source_member)
        payment_count = payments.count()
        payments.update(member=target_member)
        stats["payments_moved"] = payment_count
        
        # 2. Repoint check-ins (with duplicate detection)
        checkins = GymCheckIn.objects.filter(member=source_member).order_by("timestamp")
        
        # Find duplicate check-ins (same day) and keep earliest
        for checkin in checkins:
            checkin_date = checkin.timestamp.date()
            
            # Check if target already has check-in on this date
            existing = GymCheckIn.objects.filter(
                member=target_member,
                timestamp__date=checkin_date
            ).first()
            
            if existing:
                # Duplicate check-in - keep earliest, delete duplicate
                if checkin.timestamp < existing.timestamp:
                    # Source is earlier - delete target's later check-in
                    existing.delete()
                    checkin.member = target_member
                    checkin.save()
                    stats["checkins_moved"] += 1
                else:
                    # Target is earlier - just delete source's check-in
                    checkin.delete()
                stats["duplicate_checkins_removed"] += 1
            else:
                # No duplicate - just repoint
                checkin.member = target_member
                checkin.save()
                stats["checkins_moved"] += 1
        
        # 3. Repoint member logs
        logs = GymMemberLog.objects.filter(member=source_member)
        log_count = logs.count()
        logs.update(member=target_member)
        stats["logs_moved"] = log_count
        
        # 4. Merge gamification stats (take maximum/best values)
        if source_member.streak_days > target_member.streak_days:
            target_member.streak_days = source_member.streak_days
            target_member.last_checkin_date = source_member.last_checkin_date
        
        target_member.total_checkins += source_member.total_checkins
        target_member.monthly_checkins += source_member.monthly_checkins
        
        # Badge level: take highest
        badge_order = {"none": 0, "bronze": 1, "silver": 2, "gold": 3, "platinum": 4}
        if badge_order.get(source_member.badge_level, 0) > badge_order.get(target_member.badge_level, 0):
            target_member.badge_level = source_member.badge_level
        
        target_member.save(update_fields=["streak_days", "last_checkin_date", "total_checkins", "monthly_checkins", "badge_level"])
        
        # 5. Soft delete source member
        source_member.is_deleted = True
        source_member.deleted_at = timezone.now()
        source_member.deleted_by = user
        source_member.delete_reason = reason
        source_member.delete_notes = notes
        source_member.merged_into = target_member
        source_member.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by", "delete_reason", "delete_notes", "merged_into"]
        )
        
        # 6. Create audit log for merge
        GymMemberLog.objects.create(
            member=target_member,
            action=GymMemberAction.UPDATED,
            changes={
                "action": "merged_from",
                "source_member_id": source_member.id,
                "source_member_name": source_member.name,
                "reason": reason,
                "notes": notes,
                "stats": stats,
            },
            performed_by=user,
        )
        
        logger.info(
            f"Merged member {source_member.id} ({source_member.name}) into {target_member.id} ({target_member.name}). "
            f"Stats: {stats}"
        )
    
    return stats


def find_duplicate_members(business: Business) -> List[List[GymMember]]:
    """
    Find all duplicate members in a business (grouped by canonical name).
    
    Returns list of duplicate groups, where each group contains 2+ members
    with the same canonical name.
    
    Args:
        business: Business to check for duplicates
        
    Returns:
        List of duplicate groups: [[member1, member2], [member3, member4, member5], ...]
    """
    from inventory.utils_schema import model_has_field
    
    # Safety check: name_canonical field must exist for deduplication
    if not model_has_field(GymMember, "name_canonical"):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "GymMember.name_canonical field not found. "
            "Run migrations to enable duplicate detection. "
            "Returning empty list."
        )
        return []
    
    # Find all canonical names with duplicates
    duplicates_qs = (
        GymMember.objects.filter(business=business)
        .values("name_canonical")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    
    duplicate_groups = []
    for item in duplicates_qs:
        canonical = item["name_canonical"]
        if not canonical:  # Skip empty names
            continue
        
        members = list(
            GymMember.objects.filter(
                business=business,
                name_canonical=canonical
            ).order_by("joined_at")
        )
        
        if len(members) > 1:
            duplicate_groups.append(members)
    
    return duplicate_groups


def choose_canonical_member(members: List[GymMember]) -> GymMember:
    """
    Choose which member should be kept when merging duplicates.
    
    Rules (in order of priority):
    1. Member with most related records (payments + check-ins)
    2. Member with earliest joined_at date
    3. Member with lowest ID
    
    Args:
        members: List of duplicate members
        
    Returns:
        The member chosen as canonical
    """
    if len(members) == 1:
        return members[0]
    
    # Calculate "richness" score (count of related data)
    scored = []
    for member in members:
        payment_count = GymPayment.objects.filter(member=member).count()
        checkin_count = GymCheckIn.objects.filter(member=member).count()
        score = payment_count * 10 + checkin_count  # Weight payments higher
        scored.append((score, member.joined_at, member.id, member))
    
    # Sort by score (desc), then joined_at (asc), then id (asc)
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    
    return scored[0][3]


def dedupe_members(
    business: Business,
    user: Optional[User] = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """
    Auto-deduplicate all members in a business by merging duplicates.
    
    For each group of duplicates:
    - Choose canonical member (most data, earliest join date)
    - Merge all others into canonical
    
    Args:
        business: Business to deduplicate
        user: User performing the dedupe (None for system/migration)
        dry_run: If True, only report what would be done without making changes
        
    Returns:
        Dict with statistics:
        {
            "duplicate_groups_found": int,
            "members_merged": int,
            "canonical_members_kept": int,
            "payments_moved": int,
            "checkins_moved": int,
            "errors": List[str],
        }
    """
    duplicate_groups = find_duplicate_members(business)
    
    stats = {
        "duplicate_groups_found": len(duplicate_groups),
        "members_merged": 0,
        "canonical_members_kept": 0,
        "payments_moved": 0,
        "checkins_moved": 0,
        "duplicate_checkins_removed": 0,
        "errors": [],
    }
    
    if dry_run:
        logger.info(f"DRY RUN: Found {len(duplicate_groups)} duplicate groups in business {business.id}")
        for group in duplicate_groups:
            canonical = choose_canonical_member(group)
            logger.info(
                f"  Would merge {len(group)-1} members into canonical: {canonical.name} (ID {canonical.id})"
            )
        return stats
    
    for group in duplicate_groups:
        try:
            canonical = choose_canonical_member(group)
            stats["canonical_members_kept"] += 1
            
            # Merge all others into canonical
            for member in group:
                if member.id == canonical.id:
                    continue
                
                merge_stats = merge_members(
                    source_member=member,
                    target_member=canonical,
                    user=user,
                    reason="auto_dedupe",
                    notes=f"Automatic deduplication on deploy. Merged into {canonical.name} (ID {canonical.id})",
                )
                
                stats["members_merged"] += 1
                stats["payments_moved"] += merge_stats["payments_moved"]
                stats["checkins_moved"] += merge_stats["checkins_moved"]
                stats["duplicate_checkins_removed"] += merge_stats["duplicate_checkins_removed"]
                
        except Exception as e:
            error_msg = f"Error merging group {[m.id for m in group]}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            stats["errors"].append(error_msg)
    
    logger.info(f"Dedupe complete for business {business.id}. Stats: {stats}")
    return stats


def bulk_create_members(
    business: Business,
    members_data: List[Dict[str, any]],
    user: User,
    skip_duplicates: bool = True,
) -> Dict[str, any]:
    """
    Bulk create gym members from a list of member data.
    
    Args:
        business: Business to create members in
        members_data: List of dicts with keys: name, phone, email, trainer_id, notes
        user: User creating the members
        skip_duplicates: If True, skip members with duplicate names (default)
                        If False, raise error on duplicate
        
    Returns:
        Dict with results:
        {
            "created": [list of created member objects],
            "skipped_duplicates": [list of {name, existing_member_id, reason}],
            "errors": [list of {row_index, name, error_message}],
        }
    """
    from inventory.models_verticals import GymTrainer
    from core.validators import validate_no_digits
    from django.core.exceptions import ValidationError
    import re
    
    results = {
        "created": [],
        "skipped_duplicates": [],
        "errors": [],
    }
    
    for idx, data in enumerate(members_data):
        try:
            # Skip empty rows
            name = data.get("name", "").strip()
            if not name:
                continue
            
            # Validate name (text only, no digits)
            try:
                validate_no_digits(name)
            except ValidationError as e:
                results["errors"].append({
                    "row_index": idx,
                    "name": name,
                    "error": "Name must contain only letters, spaces, hyphens, and apostrophes"
                })
                continue
            
            # Normalize and check for duplicates
            from inventory.utils_schema import safe_filter_by_field
            canonical = normalize_member_name(name)
            
            # Check against existing members (safe - handles missing name_canonical field)
            base_qs = GymMember.objects.filter(business=business)
            existing = safe_filter_by_field(base_qs, "name_canonical", name_canonical=canonical).first()
            
            if existing:
                if skip_duplicates:
                    results["skipped_duplicates"].append({
                        "name": name,
                        "existing_member_id": existing.id,
                        "existing_member_name": existing.name,
                        "reason": "duplicate_name"
                    })
                    continue
                else:
                    results["errors"].append({
                        "row_index": idx,
                        "name": name,
                        "error": f"Member already exists: {existing.name} (ID {existing.id})"
                    })
                    continue
            
            # Check against already-created members in this batch
            already_in_batch = any(
                normalize_member_name(created.name) == canonical
                for created in results["created"]
            )
            if already_in_batch:
                results["skipped_duplicates"].append({
                    "name": name,
                    "reason": "duplicate_in_batch"
                })
                continue
            
            # Validate and prepare data
            phone = data.get("phone", "").strip() or None
            email = data.get("email", "").strip() or ""
            notes = data.get("notes", "").strip() or ""
            trainer_id = data.get("trainer_id")
            
            # Validate phone format (basic)
            if phone:
                # Remove common separators for validation
                phone_digits = re.sub(r'[\s\-\(\)]', '', phone)
                if not phone_digits.isdigit() or len(phone_digits) < 7:
                    results["errors"].append({
                        "row_index": idx,
                        "name": name,
                        "error": "Invalid phone number format"
                    })
                    continue
            
            # Validate email
            if email:
                from django.core.validators import validate_email
                try:
                    validate_email(email)
                except ValidationError:
                    results["errors"].append({
                        "row_index": idx,
                        "name": name,
                        "error": "Invalid email format"
                    })
                    continue
            
            # Get trainer if specified
            trainer = None
            if trainer_id:
                try:
                    trainer = GymTrainer.objects.get(id=trainer_id, business=business, is_active=True)
                except GymTrainer.DoesNotExist:
                    results["errors"].append({
                        "row_index": idx,
                        "name": name,
                        "error": f"Trainer ID {trainer_id} not found"
                    })
                    continue
            
            # Create member (transaction per member for isolation)
            with transaction.atomic():
                member = GymMember.objects.create(
                    business=business,
                    name=name,
                    phone=phone,
                    email=email,
                    trainer=trainer,
                    notes=notes,
                    status="pending_payment",
                )
                
                # Log creation
                GymMemberLog.objects.create(
                    member=member,
                    action=GymMemberAction.CREATED,
                    changes={
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "trainer": trainer.name if trainer else None,
                        "bulk_import": True,
                    },
                    performed_by=user,
                )
                
                results["created"].append(member)
        
        except Exception as e:
            logger.error(f"Error creating member at row {idx}: {str(e)}", exc_info=True)
            results["errors"].append({
                "row_index": idx,
                "name": data.get("name", ""),
                "error": str(e)
            })
    
    logger.info(
        f"Bulk create complete: {len(results['created'])} created, "
        f"{len(results['skipped_duplicates'])} skipped, "
        f"{len(results['errors'])} errors"
    )
    
    return results

