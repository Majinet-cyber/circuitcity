from django.db import migrations

class Migration(migrations.Migration):
    # It must run after your existing 0025
    dependencies = [("inventory", "0025_backfill_location_non_null")]

    operations = [
        # These are idempotent (no-op if index isn't there)
        migrations.RunSQL("DROP INDEX IF EXISTS inventory_inventoryitem_is_active_435aae93;"),
        migrations.RunSQL("DROP INDEX IF EXISTS inventory_inventoryitem_status_59404d58;"),
        migrations.RunSQL("DROP INDEX IF EXISTS inventory_inventoryitem_status_59404d58_like;"),
    ]
