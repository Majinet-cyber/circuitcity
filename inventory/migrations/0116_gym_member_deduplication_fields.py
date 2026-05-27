# Generated migration for gym member deduplication
"""
Add fields for duplicate prevention and soft delete to GymMember:
- name_canonical: normalized name for duplicate detection
- is_deleted, deleted_at, deleted_by, delete_reason, delete_notes: soft delete tracking
- merged_into: reference to canonical member if this was merged

This migration:
1. Adds the new fields
2. Backfills name_canonical for all existing members
3. Adds unique constraint on (business, name_canonical) excluding deleted members
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import re


def backfill_canonical_names(apps, schema_editor):
    """Backfill name_canonical for all existing gym members"""
    GymMember = apps.get_model("inventory", "GymMember")
    
    def normalize_name(name):
        """Normalize member name for duplicate detection"""
        if not name:
            return ""
        # Strip and collapse whitespace, then casefold
        normalized = re.sub(r"\s+", " ", name.strip()).casefold()
        return normalized
    
    members = GymMember.objects.all()
    batch_size = 500
    updated = 0
    
    for i in range(0, members.count(), batch_size):
        batch = list(members[i:i + batch_size])
        for member in batch:
            member.name_canonical = normalize_name(member.name)
        
        GymMember.objects.bulk_update(batch, ["name_canonical"], batch_size=batch_size)
        updated += len(batch)
    
    print(f"Backfilled name_canonical for {updated} gym members")


def reverse_backfill(apps, schema_editor):
    """Clear canonical names on reverse migration"""
    GymMember = apps.get_model("inventory", "GymMember")
    GymMember.objects.all().update(name_canonical="")


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0115_alter_agentprofile_location"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Add name_canonical field (without unique constraint yet)
        migrations.AddField(
            model_name="gymmember",
            name="name_canonical",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                editable=False,
                help_text="Normalized name for duplicate detection (auto-populated)",
                max_length=120,
            ),
        ),
        # Step 2: Add soft delete fields
        migrations.AddField(
            model_name="gymmember",
            name="is_deleted",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Soft delete flag - set when member is deleted or merged into another member",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                help_text="When this member was soft-deleted",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gym_members_deleted",
                to=settings.AUTH_USER_MODEL,
                help_text="User who deleted this member",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="delete_reason",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Reason for deletion (e.g., 'duplicate', 'entered_by_mistake', 'merged_into_X')",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="delete_notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Additional notes about why this member was deleted",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="merged_duplicates",
                to="inventory.gymmember",
                help_text="If this member was merged, reference to the canonical member",
            ),
        ),
        # Step 3: Backfill canonical names for existing members
        migrations.RunPython(backfill_canonical_names, reverse_backfill),
        # Step 4: Add indexes for performance (but NOT unique constraint yet - that comes after dedupe in 0117)
        migrations.AddIndex(
            model_name="gymmember",
            index=models.Index(fields=["business", "name_canonical"], name="inventory_g_busines_name_ca_idx"),
        ),
        migrations.AddIndex(
            model_name="gymmember",
            index=models.Index(fields=["is_deleted"], name="inventory_g_is_dele_idx"),
        ),
        # NOTE: Unique constraint will be added in migration 0118 AFTER auto-dedupe in 0117
    ]

