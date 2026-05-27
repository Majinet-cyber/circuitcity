# inventory/management/commands/seed_default_phone_products.py
"""
Management command to seed default phone products for phone businesses.

Usage:
    python manage.py seed_default_phone_products [--business-id=N] [--force]

This creates a starter catalog of popular phone brands and models for:
  - Tecno (Spark Go 1, Spark 40, Pop10c)
  - Itel (A80, P40)
  - Samsung (A15, A25)

The command only seeds businesses that:
  1. Have business_kind = "phones" (or similar vertical), AND
  2. Have zero existing phone products

Use --force to seed even if products already exist.
Use --business-id=N to target a specific business.
"""

from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed default phone products (Tecno, Itel, Samsung) for phone businesses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--business-id",
            type=int,
            help="Seed only this specific business ID",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if products already exist (skip uniqueness checks)",
        )

    def handle(self, *args, **options):
        business_id = options.get("business_id")
        force = options.get("force", False)

        # Safe imports
        try:
            from tenants.models import Business
        except ImportError:
            self.stdout.write(self.style.ERROR("Could not import Business model."))
            return

        try:
            from inventory.models import Product
        except ImportError:
            self.stdout.write(self.style.ERROR("Could not import Product model."))
            return

        # Build catalog
        catalog = self._build_catalog()

        # Filter businesses
        if business_id:
            businesses = Business.objects.filter(pk=business_id)
            if not businesses.exists():
                self.stdout.write(self.style.ERROR(f"Business {business_id} not found."))
                return
        else:
            # All phone businesses
            businesses = Business.objects.all()
            # Filter by business_kind if available
            if hasattr(Business, "business_kind"):
                businesses = businesses.filter(business_kind__in=["phones", "electronics", "phone", "mobile"])

        total_created = 0
        businesses_seeded = 0

        for biz in businesses:
            # Check if already has products (unless --force)
            if not force:
                existing_count = Product.objects.filter(brand__in=["Tecno", "Itel", "Samsung"]).count()
                if existing_count > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{biz.name}] Already has {existing_count} phone products, skipping. Use --force to override."
                        )
                    )
                    continue

            created = self._seed_for_business(biz, catalog, force=force)
            if created > 0:
                total_created += created
                businesses_seeded += 1
                self.stdout.write(self.style.SUCCESS(f"[{biz.name}] Seeded {created} products."))

        if total_created > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✅ Done! Seeded {total_created} products across {businesses_seeded} business(es).")
            )
        else:
            self.stdout.write(self.style.WARNING("No products created (all businesses already have phone products)."))

    def _build_catalog(self) -> List[Dict]:
        """
        Returns a list of default phone product specs:
        [
            {"brand": "Tecno", "model": "Spark Go 1", "variant": "", "cost": 100000, "price": 120000},
            ...
        ]
        """
        return [
            # Tecno
            {"brand": "Tecno", "model": "Spark Go 1", "variant": "", "cost": 95000, "price": 115000},
            {"brand": "Tecno", "model": "Spark 40", "variant": "(4+128)", "cost": 120000, "price": 145000},
            {"brand": "Tecno", "model": "Pop 10c", "variant": "", "cost": 75000, "price": 95000},
            {"brand": "Tecno", "model": "Camon 20", "variant": "", "cost": 180000, "price": 220000},
            {"brand": "Tecno", "model": "Pova 5", "variant": "", "cost": 165000, "price": 200000},
            # Itel
            {"brand": "Itel", "model": "A80", "variant": "", "cost": 65000, "price": 85000},
            {"brand": "Itel", "model": "P40", "variant": "", "cost": 78000, "price": 98000},
            {"brand": "Itel", "model": "S23", "variant": "", "cost": 110000, "price": 135000},
            {"brand": "Itel", "model": "P55", "variant": "", "cost": 88000, "price": 108000},
            # Infinix
            {"brand": "Infinix", "model": "Hot 40", "variant": "", "cost": 125000, "price": 155000},
            {"brand": "Infinix", "model": "Smart 8", "variant": "", "cost": 85000, "price": 105000},
            {"brand": "Infinix", "model": "Note 30", "variant": "", "cost": 170000, "price": 210000},
            # Samsung
            {"brand": "Samsung", "model": "Galaxy A15", "variant": "", "cost": 150000, "price": 185000},
            {"brand": "Samsung", "model": "Galaxy A25", "variant": "", "cost": 220000, "price": 270000},
            {"brand": "Samsung", "model": "Galaxy M14", "variant": "", "cost": 140000, "price": 175000},
            {"brand": "Samsung", "model": "Galaxy A05", "variant": "", "cost": 110000, "price": 140000},
            # Oppo
            {"brand": "Oppo", "model": "A18", "variant": "", "cost": 135000, "price": 165000},
            {"brand": "Oppo", "model": "A78", "variant": "", "cost": 195000, "price": 240000},
            # Vivo
            {"brand": "Vivo", "model": "Y16", "variant": "", "cost": 115000, "price": 145000},
            {"brand": "Vivo", "model": "Y36", "variant": "", "cost": 185000, "price": 230000},
            # Huawei
            {"brand": "Huawei", "model": "Y6", "variant": "", "cost": 105000, "price": 130000},
            {"brand": "Huawei", "model": "Nova Y61", "variant": "", "cost": 145000, "price": 180000},
            # Xiaomi (Mi/Redmi)
            {"brand": "Xiaomi", "model": "Redmi 13C", "variant": "", "cost": 130000, "price": 160000},
            {"brand": "Xiaomi", "model": "Redmi Note 13", "variant": "", "cost": 200000, "price": 250000},
            # iPhone (Apple)
            {"brand": "Apple", "model": "iPhone 11", "variant": "(64GB)", "cost": 450000, "price": 550000},
            {"brand": "Apple", "model": "iPhone 12", "variant": "(128GB)", "cost": 600000, "price": 750000},
            {"brand": "Apple", "model": "iPhone SE 2022", "variant": "", "cost": 380000, "price": 480000},
        ]

    def _seed_for_business(self, business, catalog: List[Dict], force: bool = False) -> int:
        """
        Seed products for a single business. Returns count created.
        """
        from inventory.models import Product

        created_count = 0

        with transaction.atomic():
            for spec in catalog:
                brand = spec["brand"]
                model = spec["model"]
                variant = spec.get("variant", "")
                cost = Decimal(str(spec["cost"]))
                price = Decimal(str(spec["price"]))

                # Build unique code (SKU)
                code_parts = [brand.upper(), model.replace(" ", "")]
                if variant:
                    code_parts.append(variant.replace(" ", "").replace("(", "").replace(")", ""))
                code = "-".join(code_parts)

                # Build display name
                name_parts = [brand, model]
                if variant:
                    name_parts.append(variant)
                name = " ".join(name_parts)

                # Check if already exists (by code or by brand+model+variant)
                existing = Product.objects.filter(
                    brand=brand,
                    model=model,
                    variant=variant,
                ).first()

                if existing:
                    if force:
                        # Update prices if forcing
                        existing.cost_price = cost
                        existing.sale_price = price
                        if not existing.code:
                            existing.code = code
                        if not existing.name:
                            existing.name = name
                        existing.save()
                        self.stdout.write(self.style.WARNING(f"  Updated: {name}"))
                    continue

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
                created_count += 1

        return created_count
