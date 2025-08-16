from django.db import migrations
from django.utils import timezone

def forwards(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    InventoryItem = apps.get_model("inventory", "InventoryItem")
    # Align Sale.created_at with sold_at when missing/placeholder-ish
    for s in Sale.objects.all().iterator():
        if s.sold_at and (s.created_at.date() != s.sold_at):
            # Put created_at at midday on sold_at to keep tz simple
            s.created_at = timezone.make_aware(timezone.datetime(
                s.sold_at.year, s.sold_at.month, s.sold_at.day, 12, 0, 0
            ), timezone.get_current_timezone())
            s.save(update_fields=["created_at"])
        # Ensure InventoryItem.sold_at is set
        try:
            item = s.item
        except InventoryItem.DoesNotExist:
            continue
        if item and not item.sold_at:
            item.sold_at = s.created_at
            item.status = "SOLD"
            item.save(update_fields=["sold_at", "status"])

def backwards(apps, schema_editor):
    # No-op (keep the data improvements)
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_alter_sale_options_sale_created_at_and_more"),
        ("inventory", "0011_remove_inventoryitem_inventory_i_status_214241_idx_and_more"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
