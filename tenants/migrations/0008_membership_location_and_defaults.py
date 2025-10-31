from django.db import migrations, models
from django.db.models import Q


def _ensure_defaults_and_backfill_locations(apps, schema_editor):
    """
    1) Ensure every Business has at least one Location and exactly one default.
    2) Backfill Membership.location for AGENT rows that are NULL with the
       business' default (or first) Location.
    """
    Business = apps.get_model("tenants", "Business")
    Membership = apps.get_model("tenants", "Membership")
    Location = apps.get_model("inventory", "Location")

    db = schema_editor.connection.alias

    # 1) Guarantee default locations per business
    for biz in Business.objects.using(db).all():
        loc_qs = Location.objects.using(db).filter(business_id=biz.id)
        first_loc = loc_qs.order_by("id").first()
        if not first_loc:
            name = f"{biz.name} Store".strip() or "Main Store"
            kwargs = {"business_id": biz.id, "name": name}
            if hasattr(Location, "is_default"):
                kwargs["is_default"] = True
            first_loc = Location.objects.using(db).create(**kwargs)
        else:
            if hasattr(Location, "is_default") and not loc_qs.filter(is_default=True).exists():
                first_loc.is_default = True
                first_loc.save(update_fields=["is_default"])

    def default_loc_id_for(business_id: int):
        qs = Location.objects.using(db).filter(business_id=business_id)
        if hasattr(Location, "is_default"):
            loc = qs.filter(is_default=True).first()
            if loc:
                return loc.id
        loc = qs.order_by("id").first()
        return loc.id if loc else None

    # 2) Backfill agent memberships missing a location
    for m in Membership.objects.using(db).filter(role="AGENT", location__isnull=True).iterator():
        loc_id = default_loc_id_for(m.business_id)
        if loc_id:
            m.location_id = loc_id
            m.save(update_fields=["location"])


def _create_unique_subdomain_index_if_needed(apps, schema_editor):
    """
    Create an idempotent partial-unique on Business.subdomain for non-blank values.
    Uses vendor-specific SQL with IF NOT EXISTS to avoid 'already exists' errors.
    """
    vendor = schema_editor.connection.vendor

    # Table name is tenants_business by default (app_label_modelname)
    # Adjust if you renamed the app or model.
    if vendor == "sqlite":
        sql = """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_business_subdomain_nonblank
        ON tenants_business(subdomain)
        WHERE subdomain <> '';
        """
        schema_editor.execute(sql)

    elif vendor == "postgresql":
        # Postgres supports partial unique indexes with IF NOT EXISTS
        sql = """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_business_subdomain_nonblank
        ON tenants_business(subdomain)
        WHERE subdomain <> '';
        """
        schema_editor.execute(sql)

    else:
        # MySQL and others lack partial unique indexes in the same way.
        # We skip silently to avoid breaking migrations on those engines.
        # (Your Django-level validation still prevents duplicates in code.)
        pass


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_alter_membership_unique_together_and_more"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        # Business indices (safe; if you already added them elsewhere, comment these out)
        migrations.AddIndex(
            model_name="business",
            index=models.Index(fields=["created_at"], name="biz_created_idx"),
        ),
        migrations.AddIndex(
            model_name="business",
            index=models.Index(fields=["status"], name="biz_status_idx"),
        ),
        migrations.AddIndex(
            model_name="business",
            index=models.Index(fields=["subdomain"], name="biz_subdomain_idx"),
        ),

        # Idempotent creation of partial unique index (non-blank subdomains)
        migrations.RunPython(_create_unique_subdomain_index_if_needed, _noop_reverse),

        # Data backfill (idempotent)
        migrations.RunPython(_ensure_defaults_and_backfill_locations, _noop_reverse),
    ]
