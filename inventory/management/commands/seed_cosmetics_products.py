# inventory/management/commands/seed_cosmetics_products.py
"""
Management command to seed default cosmetics products for pharmacy businesses.

Usage:
    python manage.py seed_cosmetics_products [--business-id=N] [--force]

This creates a starter catalog of popular cosmetics products for:
  - Perfumes: Arabic, Emerald, Monalisa, Pure Black
  - Skin Care: CeraVe Lotion, Nivea Soft Cream, Dove Beauty Cream

The command only seeds businesses that:
  1. Have business_kind = "pharmacy", AND
  2. Have zero existing cosmetics products in those categories

Use --force to seed even if products already exist.
Use --business-id=N to target a specific business.
"""

from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed default cosmetics products (Perfumes, Skin Care) for pharmacy businesses."

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
            from inventory.models import MerchProduct
        except ImportError:
            self.stdout.write(self.style.ERROR("Could not import MerchProduct model."))
            return

        try:
            from inventory.models_pharmacy import PharmacyCategory
        except ImportError:
            self.stdout.write(self.style.ERROR("Could not import PharmacyCategory."))
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
            # All pharmacy businesses
            businesses = Business.objects.all()
            # Filter by business_kind if available
            if hasattr(Business, "business_kind"):
                businesses = businesses.filter(business_kind="pharmacy")

        total_created = 0
        businesses_seeded = 0

        for biz in businesses:
            # Check if already has cosmetics products (unless --force)
            if not force:
                existing_count = MerchProduct.objects.filter(
                    business=biz,
                    kind="pharmacy",
                    category__in=[
                        PharmacyCategory.BEAUTY_MAKEUP,
                        PharmacyCategory.SKIN_CARE,
                    ],
                    is_active=True,
                ).count()
                if existing_count > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{biz.name}] Already has {existing_count} cosmetics products, skipping. Use --force to override."
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
            self.stdout.write(
                self.style.WARNING("No products created (all businesses already have cosmetics products).")
            )

    def _build_catalog(self) -> List[Dict]:
        """
        Returns a list of default cosmetics product specs (Malawi-relevant):
        [
            {"name": "Arabic", "category": "beauty_makeup", "cost": 5000, "price": 8000},
            ...
        ]
        """
        return [
            # Perfumes (under beauty_makeup category) - exactly 4 items
            {"name": "Arabic", "category": "beauty_makeup", "cost": Decimal("5000.00"), "price": Decimal("8000.00")},
            {"name": "Emerald", "category": "beauty_makeup", "cost": Decimal("4500.00"), "price": Decimal("7000.00")},
            {"name": "Monalisa", "category": "beauty_makeup", "cost": Decimal("5500.00"), "price": Decimal("8500.00")},
            {
                "name": "Pure Black",
                "category": "beauty_makeup",
                "cost": Decimal("6000.00"),
                "price": Decimal("9000.00"),
            },
            # Skin Care - exactly 4 items
            {"name": "CeraVe Lotion", "category": "skin_care", "cost": Decimal("3500.00"), "price": Decimal("5500.00")},
            {
                "name": "Nivea Soft Cream",
                "category": "skin_care",
                "cost": Decimal("2500.00"),
                "price": Decimal("4000.00"),
            },
            {
                "name": "Vaseline Body Lotion",
                "category": "skin_care",
                "cost": Decimal("2000.00"),
                "price": Decimal("3500.00"),
            },
            {
                "name": "Dove Beauty Cream",
                "category": "skin_care",
                "cost": Decimal("1800.00"),
                "price": Decimal("3000.00"),
            },
            # Hair Care
            {
                "name": "Dark & Lovely Relaxer",
                "category": "hair_care",
                "cost": Decimal("2800.00"),
                "price": Decimal("4500.00"),
            },
            {
                "name": "Olive Oil Hair Food",
                "category": "hair_care",
                "cost": Decimal("1500.00"),
                "price": Decimal("2500.00"),
            },
            # Body Care (Personal Care)
            {"name": "Dove Soap", "category": "personal_care", "cost": Decimal("800.00"), "price": Decimal("1500.00")},
            {
                "name": "Imperial Leather Soap",
                "category": "personal_care",
                "cost": Decimal("700.00"),
                "price": Decimal("1300.00"),
            },
        ]

    def _seed_for_business(self, business, catalog: List[Dict], force: bool = False) -> int:
        """
        Seed products for a single business. Returns count created.
        """
        from inventory.models import MerchProduct

        created_count = 0

        with transaction.atomic():
            for spec in catalog:
                name = spec["name"]
                category = spec["category"]
                cost = spec["cost"]
                price = spec["price"]

                # Check if already exists (by name and category for this business)
                existing = MerchProduct.objects.filter(
                    business=business,
                    name=name,
                    kind="pharmacy",
                    category=category,
                ).first()

                if existing:
                    if force:
                        # Update prices if forcing
                        existing.cost_price = cost
                        existing.selling_price = price
                        existing.is_active = True
                        existing.save()
                        self.stdout.write(self.style.WARNING(f"  Updated: {name}"))
                    continue

                # Create new product
                MerchProduct.objects.create(
                    business=business,
                    name=name,
                    kind="pharmacy",
                    category=category,
                    cost_price=cost,
                    selling_price=price,
                    is_active=True,
                    track_inventory=True,
                )
                created_count += 1

        return created_count
