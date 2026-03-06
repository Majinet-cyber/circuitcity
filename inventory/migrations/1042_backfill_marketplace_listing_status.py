# inventory/migrations/1042_backfill_marketplace_listing_status.py
"""
Data migration: set all existing marketplace listings (status='draft' from default)
to status='live', since all pre-migration listings had is_active=True by default.
"""
from django.db import migrations


def set_existing_to_live(apps, schema_editor):
    MarketplaceListing = apps.get_model("inventory", "MarketplaceListing")
    # All listings that currently have status='draft' were migrated from the
    # old is_active model — treat them as 'live' (they were publicly visible before)
    MarketplaceListing.objects.filter(status="draft").update(status="live")


def backwards(apps, schema_editor):
    MarketplaceListing = apps.get_model("inventory", "MarketplaceListing")
    MarketplaceListing.objects.filter(status="live").update(status="draft")


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1041_marketplace_upgrade_and_car_dealer"),
    ]

    operations = [
        migrations.RunPython(set_existing_to_live, backwards),
    ]
