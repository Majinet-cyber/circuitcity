# Generated migration to seed default phone products for phone businesses

from django.db import migrations
from decimal import Decimal


def seed_phone_products(apps, schema_editor):
    """
    Seed default phone products (Tecno, Itel, Samsung, etc.) for phone businesses.
    This runs automatically during migration for businesses with business_kind='phones'.
    """
    Business = apps.get_model("tenants", "Business")
    Product = apps.get_model("inventory", "Product")

    # Define the catalog
    catalog = [
        # Tecno
        {"brand": "Tecno", "model": "Spark Go 1", "variant": "(32GB + 2GB RAM)", "cost": 95000, "price": 115000},
        {"brand": "Tecno", "model": "Pop 10C", "variant": "(32GB + 2GB RAM)", "cost": 75000, "price": 95000},
        {"brand": "Tecno", "model": "Pop 8", "variant": "(64GB + 3GB RAM)", "cost": 85000, "price": 105000},
        {"brand": "Tecno", "model": "Camon 19", "variant": "(128GB + 4GB RAM)", "cost": 180000, "price": 220000},
        {"brand": "Tecno", "model": "Spark 10C", "variant": "(128GB + 4GB RAM)", "cost": 120000, "price": 145000},
        # Itel
        {"brand": "Itel", "model": "A60", "variant": "(32GB + 2GB RAM)", "cost": 65000, "price": 85000},
        {"brand": "Itel", "model": "A70", "variant": "(64GB + 3GB RAM)", "cost": 78000, "price": 98000},
        {"brand": "Itel", "model": "P40", "variant": "(64GB + 4GB RAM)", "cost": 88000, "price": 108000},
        {"brand": "Itel", "model": "P38", "variant": "(32GB + 2GB RAM)", "cost": 70000, "price": 90000},
        # Samsung
        {
            "brand": "Samsung",
            "model": "Galaxy A03 Core",
            "variant": "(32GB + 2GB RAM)",
            "cost": 110000,
            "price": 140000,
        },
        {"brand": "Samsung", "model": "Galaxy A04", "variant": "(64GB + 3GB RAM)", "cost": 130000, "price": 160000},
        {"brand": "Samsung", "model": "Galaxy A04s", "variant": "(64GB + 4GB RAM)", "cost": 145000, "price": 175000},
        {"brand": "Samsung", "model": "Galaxy A15", "variant": "(128GB + 4GB RAM)", "cost": 150000, "price": 185000},
        # Infinix
        {"brand": "Infinix", "model": "Hot 40", "variant": "(128GB + 8GB RAM)", "cost": 125000, "price": 155000},
        {"brand": "Infinix", "model": "Smart 8", "variant": "(64GB + 3GB RAM)", "cost": 85000, "price": 105000},
        # Oppo
        {"brand": "Oppo", "model": "A18", "variant": "(128GB + 4GB RAM)", "cost": 135000, "price": 165000},
        # Xiaomi
        {"brand": "Xiaomi", "model": "Redmi 13C", "variant": "(128GB + 4GB RAM)", "cost": 130000, "price": 160000},
    ]

    # Get all phone businesses
    phone_businesses = Business.objects.filter(business_kind__in=["phones", "electronics", "phone", "mobile"])

    total_created = 0

    for biz in phone_businesses:
        # Check if this business already has products
        existing_count = Product.objects.filter(
            brand__in=["Tecno", "Itel", "Samsung", "Infinix", "Oppo", "Xiaomi"]
        ).count()

        if existing_count > 0:
            # Skip businesses that already have phone products
            continue

        # Seed products for this business
        for spec in catalog:
            brand = spec["brand"]
            model = spec["model"]
            variant = spec.get("variant", "")
            cost = Decimal(str(spec["cost"]))
            price = Decimal(str(spec["price"]))

            # Build unique code (SKU)
            code_parts = [brand.upper(), model.replace(" ", "")]
            if variant:
                clean_variant = variant.replace(" ", "").replace("(", "").replace(")", "").replace("+", "")
                code_parts.append(clean_variant)
            code = "-".join(code_parts)

            # Build display name
            name_parts = [brand, model]
            if variant:
                name_parts.append(variant)
            name = " ".join(name_parts)

            # Check if this exact product already exists
            existing = Product.objects.filter(
                brand=brand,
                model=model,
                variant=variant,
            ).first()

            if not existing:
                # Create new product
                Product.objects.create(
                    code=code,
                    name=name,
                    brand=brand,
                    model=model,
                    variant=variant,
                    cost_price=cost,
                    sale_price=price,
                    low_stock_threshold=5,
                )
                total_created += 1

    if total_created > 0:
        print(f"✅ Seeded {total_created} default phone products for phone businesses")


def reverse_seed(apps, schema_editor):
    """
    Reverse migration - optionally delete seeded products.
    We'll make this a no-op to preserve data.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0039_fix_warranty_field_names"),
        ("tenants", "0001_initial"),  # Ensure tenants.Business exists
    ]

    operations = [
        migrations.RunPython(seed_phone_products, reverse_seed),
    ]
