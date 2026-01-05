# Generated migration to normalize business_kind values for hardware businesses
from __future__ import annotations

from django.db import migrations


def normalize_business_kind_forward(apps, schema_editor):
    """
    Normalize business_kind values to canonical codes.

    CRITICAL: Hardware & General Dealers businesses should have business_kind='hardware',
    not 'cement' or display labels like "Hardware & General Dealers".
    """
    Business = apps.get_model("tenants", "Business")

    # Migration-safe normalization mapping (do NOT import app code in migrations)
    # This is a subset focused on hardware normalization
    normalization_map = {
        # Hardware variants → hardware
        "hardware": "hardware",
        "hardware & general dealers": "hardware",
        "hardware and general dealers": "hardware",
        "hardware / general dealers": "hardware",
        "general dealers": "hardware",
        "general dealer": "hardware",
        "hardware store": "hardware",
        # Keep cement separate
        "cement": "cement",
        "cement / building materials": "cement",
        "cement store": "cement",
        "building materials": "cement",
        "construction": "cement",
        # Other verticals (pass-through)
        "phones": "phones",
        "liquor": "liquor",
        "grocery": "grocery",
        "pharmacy": "pharmacy",
        "clothing": "clothing",
        "gym": "gym",
    }

    businesses_updated = 0

    for business in Business.objects.all():
        if not business.business_kind:
            # Skip NULL/blank values (they should trigger settings redirect)
            continue

        # Normalize to lowercase for matching
        current_kind = str(business.business_kind).strip().lower()

        if not current_kind:
            # Skip empty strings
            continue

        # Get canonical value
        canonical = normalization_map.get(current_kind)

        if canonical and canonical != business.business_kind:
            # Update to canonical value
            print(
                f"Normalizing business_kind: '{business.business_kind}' → '{canonical}' for business: {business.name}"
            )
            business.business_kind = canonical
            business.save(update_fields=["business_kind"])
            businesses_updated += 1

    if businesses_updated > 0:
        print(f"✅ Normalized {businesses_updated} business(es) to canonical business_kind values")
    else:
        print("✅ All businesses already have canonical business_kind values")


def normalize_business_kind_reverse(apps, schema_editor):
    """
    Reverse migration: No-op (we don't want to un-normalize).

    This is a data cleanup migration, so reverting it would re-introduce
    the inconsistency. Better to keep the normalized values.
    """
    print("⚠️  Reverse migration is a no-op (keeping normalized values)")
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0022_business_hq_notified_signup_at"),
    ]

    operations = [
        migrations.RunPython(
            normalize_business_kind_forward,
            normalize_business_kind_reverse,
        ),
    ]
