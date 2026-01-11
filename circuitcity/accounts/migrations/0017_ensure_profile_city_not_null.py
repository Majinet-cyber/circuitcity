# Migration to ensure Profile.city is never NULL
# Fixes production IntegrityError: null value in column "city" violates not-null constraint
# Generated manually on 2026-01-08

from django.db import migrations, models


def backfill_null_cities(apps, schema_editor):
    """
    Backfill any NULL or empty city values with default.
    This ensures production DB is consistent with code expectations.
    """
    Profile = apps.get_model("accounts", "Profile")
    
    # Update any profiles with NULL or empty city
    updated_null = Profile.objects.filter(city__isnull=True).count()
    Profile.objects.filter(city__isnull=True).update(city="Lilongwe")
    
    # Also catch empty strings (defensive)
    updated_empty = Profile.objects.filter(city="").count()
    Profile.objects.filter(city="").update(city="Lilongwe")
    
    total = updated_null + updated_empty
    if total > 0:
        print(f"✅ Backfilled {total} Profile records with city='Lilongwe'")


def reverse_migration(apps, schema_editor):
    """No-op reverse - we never want to set city back to NULL"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_add_city_field_to_profile"),
    ]

    operations = [
        # Backfill any existing NULL or empty values
        migrations.RunPython(
            backfill_null_cities,
            reverse_migration,
        ),
    ]

