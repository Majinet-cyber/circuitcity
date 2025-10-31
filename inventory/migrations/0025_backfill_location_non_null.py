# inventory/migrations/0025_backfill_location_non_null.py
from django.db import migrations, models


def _backfill_locations_and_business(apps, schema_editor):
    """
    Repair existing InventoryItem rows:

      1) current_location is NULL but business is set
         → set current_location to the business' default location (create one if needed).

      2) business is NULL but current_location is set
         → inherit business from that location.

      3) Both are set but business != current_location.business
         → trust the location (align business to the location's business).

    Idempotent. Works on SQLite/Postgres.
    """
    InventoryItem = apps.get_model("inventory", "InventoryItem")
    Location = apps.get_model("inventory", "Location")
    Business = apps.get_model("tenants", "Business")

    db = schema_editor.connection.alias

    # Ensure a business has a default location and return its id
    def ensure_default_location_id(biz_id: int) -> int | None:
        if not biz_id:
            return None

        qs = Location.objects.using(db).filter(business_id=biz_id)

        # Prefer explicit default if field exists
        loc = qs.filter(is_default=True).first() if hasattr(Location, "is_default") else None
        if not loc:
            loc = qs.order_by("id").first()

        if not loc:
            # Create a sensible default when none exists
            try:
                biz = Business.objects.using(db).only("name").get(pk=biz_id)
                name = f"{(biz.name or 'Main').strip()} Store"
            except Exception:
                name = "Main Store"

            kwargs = {"business_id": biz_id, "name": name}
            if hasattr(Location, "is_default"):
                kwargs["is_default"] = True
            loc = Location.objects.using(db).create(**kwargs)
        else:
            # If the field exists but nothing marked default, mark the first
            if hasattr(Location, "is_default") and not qs.filter(is_default=True).exists():
                loc.is_default = True
                loc.save(update_fields=["is_default"])

        return loc.id if loc else None

    # 1) Add a default location where missing
    missing_loc = InventoryItem.objects.using(db).filter(
        current_location__isnull=True, business__isnull=False
    )
    for item in missing_loc.iterator():
        loc_id = ensure_default_location_id(item.business_id)
        if loc_id:
            item.current_location_id = loc_id
            item.save(update_fields=["current_location"])

    # 2) Inherit business from current_location where missing
    missing_biz = InventoryItem.objects.using(db).filter(
        business__isnull=True, current_location__isnull=False
    )
    for item in missing_biz.iterator():
        try:
            loc_biz_id = (
                Location.objects.using(db)
                .only("business_id")
                .get(pk=item.current_location_id)
                .business_id
            )
        except Location.DoesNotExist:
            loc_biz_id = None

        if loc_biz_id:
            item.business_id = loc_biz_id
            item.save(update_fields=["business"])

    # 3) Align mismatches to the location's business
    mismatched = (
        InventoryItem.objects.using(db)
        .filter(business__isnull=False, current_location__isnull=False)
        .exclude(business_id=models.F("current_location__business_id"))
    )
    # Use a loop (SQLite dislikes joined updates with F() on some backends)
    for item in mismatched.iterator():
        try:
            loc_biz_id = (
                Location.objects.using(db)
                .only("business_id")
                .get(pk=item.current_location_id)
                .business_id
            )
        except Location.DoesNotExist:
            loc_biz_id = None

        if loc_biz_id and loc_biz_id != item.business_id:
            item.business_id = loc_biz_id
            item.save(update_fields=["business"])


def _noop_reverse(apps, schema_editor):
    # Data-only repair; nothing to undo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        # Chain AFTER your latest inventory migration:
        ("inventory", "0024_alter_inventoryaudit_action"),
        # Keep the tenants dependency consistent with your graph:
        ("tenants", "0003_alter_membership_role_and_more"),
    ]

    operations = [
        migrations.RunPython(_backfill_locations_and_business, _noop_reverse),
    ]
