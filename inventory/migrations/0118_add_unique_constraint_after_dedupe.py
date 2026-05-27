# Generated migration to add unique constraint AFTER deduplication
"""
Add unique constraint on (business, name_canonical) for GymMember.

This migration runs AFTER 0117 which performs automatic deduplication,
so we can safely add the constraint without conflicts.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1033_merge_20260206_1331"),
    ]

    operations = [
        # Add unique constraint (only for non-deleted members)
        migrations.AddConstraint(
            model_name="gymmember",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_deleted=False),
                fields=("business", "name_canonical"),
                name="unique_gym_member_name_per_business",
            ),
        ),
    ]

