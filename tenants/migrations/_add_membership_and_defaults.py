# tenants/migrations/####_add_membership_and_defaults.py
from django.db import migrations, models
from django.db.models import Q


def _ensure_defaults_and_backfill_locations(apps, schema_editor):
    """
    Data migration:
      1) Ensure every Business has at least one Location (create a default if none).
      2) For Membership rows where role='AGENT' and location is NULL, set to the
         business' default Location (or first Location if no explicit default).
    """
    Business = apps.get_model("tenants", "Business")
    Membership = apps.get_model("tenants", "Membership")
    # inventory.Location must already exist in your project
    Location = apps.get_model("inventory", "Location")

    db = schema_editor.connection.alias

    # 1) Make sure each business has at least one location and a default
    for biz in Business.objects.using(db).all():
        loc_qs = Location.objects.using(db).filter(business_id=biz.id)
        first_loc = loc_qs.order_by("id").first()
        if not first_loc:
            # Create a sensible default if no locations exist yet
            name = f"{biz.name} Store".strip() or "Main Store"
            first_loc = Location.objects.using(db).create(
                business_id=biz.id,
                name=name,
                is_default=True,
            )
        else:
            # If no explicit default, mark the first as default
            if not loc_qs.filter(is_default=True).exists():
                first_loc.is_default = True
                first_loc.save(update_fields=["is_default"])

    # Helper to fetch a business' default Location id
    def default_loc_id_for(business_id: int):
        loc = (
            Location.objects.using(db)
            .filter(business_id=business_id, is_default=True)
            .first()
        )
        if not loc:
            loc = (
                Location.objects.using(db)
                .filter(business_id=business_id)
                .order_by("id")
                .first()
            )
        return loc.id if loc else None

    # 2) Backfill agent memberships with a location if missing
    agents_missing_location = Membership.objects.using(db).filter(
        role="AGENT", location__isnull=True
    )
    for m in agents_missing_location.iterator():
        loc_id = default_loc_id_for(m.business_id)
        if loc_id:
            m.location_id = loc_id
            m.save(update_fields=["location"])


def _noop_reverse(apps, schema_editor):
    # We don't undo the location backfill.
    pass


class Migration(migrations.Migration):

    # TODO: Change "0001_initial" to your latest tenants migration.
    dependencies = [
        ("tenants", "0001_initial"),
        # If your Location model lives in inventory and is already migrated, you can
        # optionally add a soft dependency to help ordering in some setups:
        # ("inventory", "0001_initial"),
    ]

    operations = [
        # --- Schema: adjust unique_together so Membership can exist per location ---
        migrations.AlterUniqueTogether(
            name="membership",
            unique_together={("user", "business", "location")},
        ),

        # --- Optional but recommended: add indexes for fast lookups ---
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(
                fields=["user", "business"],
                name="mship_user_biz_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(
                fields=["role"],
                name="mship_role_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(
                fields=["status"],
                name="mship_status_idx",
            ),
        ),

        # --- Data migration: create defaults and backfill agent locations ---
        migrations.RunPython(
            _ensure_defaults_and_backfill_locations,
            _noop_reverse,
        ),
    ]
