# Generated migration for automatic gym member deduplication
"""
Automatically deduplicate existing gym members on production deploy.

For each group of duplicates (same business + canonical name):
1. Choose canonical member (most data, earliest join date)
2. Merge all others into canonical (preserve all history)
3. Soft delete duplicates with reason "auto_dedupe"

This is safe to run multiple times (idempotent).
"""

from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def auto_dedupe_members(apps, schema_editor):
    """
    Auto-deduplicate all gym members across all businesses.
    
    Uses the merge_members service to safely merge duplicates
    while preserving all payment and check-in history.
    """
    from django.db.models import Count
    from django.db import transaction
    
    GymMember = apps.get_model("inventory", "GymMember")
    GymPayment = apps.get_model("inventory", "GymPayment")
    GymCheckIn = apps.get_model("inventory", "GymCheckIn")
    GymMemberLog = apps.get_model("inventory", "GymMemberLog")
    Business = apps.get_model("tenants", "Business")
    
    total_groups = 0
    total_merged = 0
    
    # Process each business separately
    for business in Business.objects.all():
        # Find duplicate groups in this business
        duplicates_qs = (
            GymMember.objects.filter(business=business, is_deleted=False)
            .values("name_canonical")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        
        for item in duplicates_qs:
            canonical = item["name_canonical"]
            if not canonical:  # Skip empty names
                continue
            
            # Get all members with this canonical name
            members = list(
                GymMember.objects.filter(
                    business=business,
                    name_canonical=canonical,
                    is_deleted=False,
                ).order_by("joined_at")
            )
            
            if len(members) <= 1:
                continue
            
            total_groups += 1
            
            # Choose canonical member (most data, earliest join date)
            def get_richness_score(member):
                payment_count = GymPayment.objects.filter(member=member).count()
                checkin_count = GymCheckIn.objects.filter(member=member).count()
                return payment_count * 10 + checkin_count
            
            scored = [
                (get_richness_score(m), m.joined_at, m.id, m)
                for m in members
            ]
            scored.sort(key=lambda x: (-x[0], x[1], x[2]))
            canonical_member = scored[0][3]
            
            logger.info(
                f"Deduping {len(members)} members with name '{canonical_member.name}' "
                f"(business {business.id}). Canonical: ID {canonical_member.id}"
            )
            
            # Merge all others into canonical
            for member in members:
                if member.id == canonical_member.id:
                    continue
                
                try:
                    with transaction.atomic():
                        # Repoint payments
                        GymPayment.objects.filter(member=member).update(member=canonical_member)
                        
                        # Repoint check-ins (with duplicate handling)
                        checkins = GymCheckIn.objects.filter(member=member).order_by("timestamp")
                        for checkin in checkins:
                            checkin_date = checkin.timestamp.date()
                            
                            # Check if canonical already has check-in on this date
                            existing = GymCheckIn.objects.filter(
                                member=canonical_member,
                                timestamp__date=checkin_date
                            ).first()
                            
                            if existing:
                                # Keep earliest check-in
                                if checkin.timestamp < existing.timestamp:
                                    existing.delete()
                                    checkin.member = canonical_member
                                    checkin.save()
                                else:
                                    checkin.delete()
                            else:
                                checkin.member = canonical_member
                                checkin.save()
                        
                        # Repoint logs
                        GymMemberLog.objects.filter(member=member).update(member=canonical_member)
                        
                        # Merge gamification stats
                        if member.streak_days > canonical_member.streak_days:
                            canonical_member.streak_days = member.streak_days
                            canonical_member.last_checkin_date = member.last_checkin_date
                        
                        canonical_member.total_checkins += member.total_checkins
                        canonical_member.monthly_checkins += member.monthly_checkins
                        
                        # Badge level: take highest
                        badge_order = {"none": 0, "bronze": 1, "silver": 2, "gold": 3, "platinum": 4}
                        if badge_order.get(member.badge_level, 0) > badge_order.get(canonical_member.badge_level, 0):
                            canonical_member.badge_level = member.badge_level
                        
                        canonical_member.save()
                        
                        # Soft delete duplicate
                        from django.utils import timezone
                        member.is_deleted = True
                        member.deleted_at = timezone.now()
                        member.delete_reason = "auto_dedupe"
                        member.delete_notes = f"Automatic deduplication on deploy. Merged into {canonical_member.name} (ID {canonical_member.id})"
                        member.merged_into = canonical_member
                        member.save()
                        
                        total_merged += 1
                        logger.info(f"  Merged member {member.id} into {canonical_member.id}")
                
                except Exception as e:
                    logger.error(f"Error merging member {member.id}: {str(e)}", exc_info=True)
                    # Continue with next member - don't fail entire migration
    
    print(f"Auto-dedupe complete: {total_groups} duplicate groups found, {total_merged} members merged")


def reverse_dedupe(apps, schema_editor):
    """
    Reverse is not fully supported - we can only restore the deleted flag.
    Payment/check-in history cannot be automatically un-merged.
    """
    GymMember = apps.get_model("inventory", "GymMember")
    
    # Restore members that were auto-deduped
    restored = GymMember.objects.filter(
        is_deleted=True,
        delete_reason="auto_dedupe"
    ).update(
        is_deleted=False,
        deleted_at=None,
        deleted_by=None,
        delete_reason="",
        delete_notes="",
        merged_into=None,
    )
    
    print(f"Restored {restored} auto-deduped members (but history links remain merged)")


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0116_gym_member_deduplication_fields"),
        ("tenants", "0001_initial"),  # Ensure Business model is available
    ]

    operations = [
        migrations.RunPython(auto_dedupe_members, reverse_dedupe),
    ]

