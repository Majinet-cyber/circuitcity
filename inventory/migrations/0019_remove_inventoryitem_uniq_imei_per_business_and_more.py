# inventory/migrations/0019_remove_inventoryitem_uniq_imei_per_business_and_more.py
from django.db import migrations


class Migration(migrations.Migration):
    # This restores the missing node so later migrations can depend on it.
    # If your DB/schema already contains the changes that the original 0019 did,
    # a no-op here is safe. If not, later migrations will still apply the needed state.

    dependencies = [
        ("inventory", "0018_inventoryaudit_business_location_business_and_more"),
    ]

    operations = [
        # Intentionally empty: placeholder to satisfy the dependency chain.
        # If you still had the original 0019, delete this shim and restore the original.
    ]
