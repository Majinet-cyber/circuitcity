# Generated migration to seed default accessories for phone businesses

from django.db import migrations
from decimal import Decimal


def seed_accessories(apps, schema_editor):
    """
    Seed default accessories (batteries, chargers, powerbanks, etc.) for phone businesses.
    This runs automatically during migration for businesses with business_kind='phones'.
    """
    Business = apps.get_model("tenants", "Business")
    AccessoryProduct = apps.get_model("inventory", "AccessoryProduct")

    # Define the accessories catalog (same as seed_accessories command)
    # Format: (name, category, brand, order_price, selling_price)
    accessories_catalog = [
        # BATTERIES
        ("BL-5C Battery", "battery", "Generic", Decimal("3900.00"), Decimal("5000.00")),
        ("TECNO 5C Battery", "battery", "Tecno", Decimal("5950.00"), Decimal("7500.00")),
        ("BL-25BI Battery", "battery", "Generic", Decimal("9900.00"), Decimal("12000.00")),
        # CHARGERS & CAR CHARGERS
        ("ICW-051EM Charger", "charger", "Oraimo", Decimal("5400.00"), Decimal("7000.00")),
        ("OCW-1111U+M53 Charger", "charger", "Oraimo", Decimal("8000.00"), Decimal("10000.00")),
        ("OCW-1111U+L53 Charger", "charger", "Oraimo", Decimal("8500.00"), Decimal("11000.00")),
        ("OCW-U37S+M53 Charger", "charger", "Oraimo", Decimal("6600.00"), Decimal("8500.00")),
        ("OCW-U67D+M53 Charger", "charger", "Oraimo", Decimal("10500.00"), Decimal("13000.00")),
        ("OCW-5184U+M53 Charger", "charger", "Oraimo", Decimal("14000.00"), Decimal("17000.00")),
        ("OCW-5183U+C53 Charger", "charger", "Oraimo", Decimal("14500.00"), Decimal("18000.00")),
        ("OCC-32D Car Charger", "charger", "Oraimo", Decimal("28500.00"), Decimal("35000.00")),
        ("OCC-1152D Car Charger", "charger", "Oraimo", Decimal("10000.00"), Decimal("12500.00")),
        # DATA CABLES
        ("OCD-M22P Data Cable", "cable", "Oraimo", Decimal("3000.00"), Decimal("4000.00")),
        ("OCD-L53 Data Cable", "cable", "Oraimo", Decimal("5000.00"), Decimal("6500.00")),
        ("OCD-M56 Data Cable", "cable", "Oraimo", Decimal("5400.00"), Decimal("7000.00")),
        ("OCD-C53 Data Cable", "cable", "Oraimo", Decimal("4500.00"), Decimal("6000.00")),
        ("OCD-114CC Data Cable", "cable", "Oraimo", Decimal("5900.00"), Decimal("7500.00")),
        ("OCD-114L Data Cable", "cable", "Oraimo", Decimal("5000.00"), Decimal("6500.00")),
        ("OCD-114C Data Cable", "cable", "Oraimo", Decimal("4000.00"), Decimal("5500.00")),
        ("OCD-C32 Data Cable", "cable", "Oraimo", Decimal("6800.00"), Decimal("8500.00")),
        ("OCD-114C2 Data Cable", "cable", "Oraimo", Decimal("6000.00"), Decimal("7500.00")),
        ("OCD-C22P Data Cable", "cable", "Oraimo", Decimal("4000.00"), Decimal("5500.00")),
        # POWERBANKS
        ("OPB-P1100D Powerbank", "powerbank", "Oraimo", Decimal("31500.00"), Decimal("38000.00")),
        ("OPB-P1201 Powerbank", "powerbank", "Oraimo", Decimal("43500.00"), Decimal("52000.00")),
        ("OPB-P5101 Powerbank", "powerbank", "Oraimo", Decimal("37000.00"), Decimal("45000.00")),
        ("OPB-P7204Q Powerbank", "powerbank", "Oraimo", Decimal("59000.00"), Decimal("70000.00")),
        ("OPB-P204D Powerbank", "powerbank", "Oraimo", Decimal("43500.00"), Decimal("52000.00")),
        # AUDIO & WEARABLES
        ("OEB-311 Earbuds", "headset", "Oraimo", Decimal("35000.00"), Decimal("42000.00")),
        ("OHP-317 Headphones", "headset", "Oraimo", Decimal("66000.00"), Decimal("78000.00")),
        ("OTW-323 TWS Earbuds", "headset", "Oraimo", Decimal("39500.00"), Decimal("48000.00")),
        ("OTW-324 TWS Earbuds", "headset", "Oraimo", Decimal("40500.00"), Decimal("49000.00")),
        ("OTW-330S TWS Earbuds", "headset", "Oraimo", Decimal("47500.00"), Decimal("56000.00")),
        ("OTW-625 TWS Earbuds", "headset", "Oraimo", Decimal("78500.00"), Decimal("92000.00")),
        ("OSW-805 Smart Watch", "other", "Oraimo", Decimal("83000.00"), Decimal("98000.00")),
        ("KV-11 Headset", "headset", "Generic", Decimal("5000.00"), Decimal("6500.00")),
        ("DJK-50J Speaker", "speaker", "Generic", Decimal("175000.00"), Decimal("200000.00")),
        ("GD-120 Speaker", "speaker", "Generic", Decimal("22000.00"), Decimal("28000.00")),
        ("OWS-E351 Earbuds", "headset", "Oraimo", Decimal("33000.00"), Decimal("40000.00")),
    ]

    # Find phone businesses
    phone_businesses = Business.objects.filter(business_kind__in=["phones", "electronics", "phone", "mobile"])

    total_created = 0

    for biz in phone_businesses:
        # Check if this business already has accessories
        existing_count = AccessoryProduct.objects.filter(business=biz).count()

        if existing_count > 0:
            # Skip businesses that already have accessories
            continue

        # Seed accessories for this business
        for name, category, brand, order_price, selling_price in accessories_catalog:
            # Check if this exact accessory already exists
            existing = AccessoryProduct.objects.filter(business=biz, name=name).first()

            if not existing:
                # Create new accessory product
                AccessoryProduct.objects.create(
                    business=biz,
                    name=name,
                    category=category,
                    brand=brand,
                    default_order_price=order_price,
                    default_selling_price=selling_price,
                    sku=f"ACC-{name.replace(' ', '-')[:20]}-{biz.id}",  # Simple SKU generation
                )
                total_created += 1

    if total_created > 0:
        print(f"✓ Seeded {total_created} accessories across {phone_businesses.count()} phone businesses")


def reverse_seed_accessories(apps, schema_editor):
    """
    Reverse the seeding by deleting accessories created by this migration.
    Only deletes accessories with SKUs matching the pattern we created.
    """
    AccessoryProduct = apps.get_model("inventory", "AccessoryProduct")

    # Delete accessories with SKUs starting with "ACC-"
    deleted_count = AccessoryProduct.objects.filter(sku__startswith="ACC-").delete()[0]

    if deleted_count > 0:
        print(f"✓ Deleted {deleted_count} seeded accessories")


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0057_add_gym_member_code"),
    ]

    operations = [
        migrations.RunPython(seed_accessories, reverse_seed_accessories),
    ]
