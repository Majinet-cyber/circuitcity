# inventory/management/commands/seed_accessories.py
"""
Django management command to seed starter accessory products for phone businesses.
Provides a default catalog of accessories with real wholesale prices (MWK) from Malawi market.

Usage:
    python manage.py seed_accessories [--business=ID] [--all]
    
    --business=ID  : Seed accessories for a specific business ID
    --all          : Seed accessories for all businesses with business_kind="phones"
    --overwrite    : Update prices for existing products (default: skip existing)

Accessories catalog includes:
- Batteries (BL-5C, TECNO 5C, BL-25BI)
- Chargers (ICW, OCW series, OCC car chargers)
- Data Cables (OCD series)
- Powerbanks (OPB series)
- Audio/Wearables (OEB, OHP, OTW, OSW, KV, DJK, GD, OWS series)
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import Business
from inventory.models_accessories import AccessoryProduct, AccessoryCategory
from inventory.business_kinds import BusinessKind


# Starter accessories catalog with order prices (MWK)
# Format: (name, category, brand, order_price, selling_price_suggestion)
ACCESSORIES_CATALOG: List[Tuple[str, str, str, Decimal, Decimal]] = [
    # ==========================================================================
    # BATTERIES
    # ==========================================================================
    ("BL-5C Battery", "battery", "Generic", Decimal("3900.00"), Decimal("5000.00")),
    ("TECNO 5C Battery", "battery", "Tecno", Decimal("5950.00"), Decimal("7500.00")),
    ("BL-25BI Battery", "battery", "Generic", Decimal("9900.00"), Decimal("12000.00")),
    # ==========================================================================
    # CHARGERS & CAR CHARGERS
    # ==========================================================================
    ("ICW-051EM Charger", "charger", "Oraimo", Decimal("5400.00"), Decimal("7000.00")),
    ("OCW-1111U+M53 Charger", "charger", "Oraimo", Decimal("8000.00"), Decimal("10000.00")),
    ("OCW-1111U+L53 Charger", "charger", "Oraimo", Decimal("8500.00"), Decimal("11000.00")),
    ("OCW-U37S+M53 Charger", "charger", "Oraimo", Decimal("6600.00"), Decimal("8500.00")),
    ("OCW-U67D+M53 Charger", "charger", "Oraimo", Decimal("10500.00"), Decimal("13000.00")),
    ("OCW-5184U+M53 Charger", "charger", "Oraimo", Decimal("14000.00"), Decimal("17000.00")),
    ("OCW-5183U+C53 Charger", "charger", "Oraimo", Decimal("14500.00"), Decimal("18000.00")),
    ("OCC-32D Car Charger", "charger", "Oraimo", Decimal("28500.00"), Decimal("35000.00")),
    ("OCC-1152D Car Charger", "charger", "Oraimo", Decimal("10000.00"), Decimal("12500.00")),
    # ==========================================================================
    # DATA CABLES
    # ==========================================================================
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
    # ==========================================================================
    # POWERBANKS
    # ==========================================================================
    ("OPB-P1100D Powerbank", "powerbank", "Oraimo", Decimal("31500.00"), Decimal("38000.00")),
    ("OPB-P1201 Powerbank", "powerbank", "Oraimo", Decimal("43500.00"), Decimal("52000.00")),
    ("OPB-P5101 Powerbank", "powerbank", "Oraimo", Decimal("37000.00"), Decimal("45000.00")),
    ("OPB-P7204Q Powerbank", "powerbank", "Oraimo", Decimal("59000.00"), Decimal("70000.00")),
    ("OPB-P204D Powerbank", "powerbank", "Oraimo", Decimal("43500.00"), Decimal("52000.00")),
    # ==========================================================================
    # AUDIO & WEARABLES
    # ==========================================================================
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


class Command(BaseCommand):
    help = "Seed starter accessory products for phone businesses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--business",
            type=int,
            help="Business ID to seed accessories for (optional)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Seed accessories for all businesses with business_kind='phones'",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Update prices for existing products (default: skip existing)",
        )

    def handle(self, *args, **options):
        business_id = options.get("business")
        seed_all = options.get("all")
        overwrite = options.get("overwrite")

        # Determine which businesses to seed
        if business_id:
            try:
                businesses = [Business.objects.get(id=business_id)]
            except Business.DoesNotExist:
                raise CommandError(f"Business with ID {business_id} does not exist")
        elif seed_all:
            businesses = Business.objects.filter(business_kind=BusinessKind.PHONES)
            if not businesses.exists():
                self.stdout.write(self.style.WARNING("No businesses with business_kind='phones' found"))
                return
        else:
            raise CommandError("Please specify --business=ID or --all to seed accessories")

        # Seed accessories for each business
        for business in businesses:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.SUCCESS(f"Seeding accessories for: {business.name} (ID: {business.id})"))
            self.stdout.write(f"{'='*60}\n")

            created_count = 0
            updated_count = 0
            skipped_count = 0

            with transaction.atomic():
                for name, category, brand, order_price, selling_price in ACCESSORIES_CATALOG:
                    # Check if product already exists
                    existing = AccessoryProduct.objects.filter(business=business, name=name).first()

                    if existing:
                        if overwrite:
                            # Update prices
                            existing.default_order_price = order_price
                            existing.default_selling_price = selling_price
                            existing.brand = brand
                            existing.category = category
                            existing.save()
                            updated_count += 1
                            self.stdout.write(self.style.WARNING(f"  ✓ Updated: {name} (MK {order_price})"))
                        else:
                            # Skip existing
                            skipped_count += 1
                            self.stdout.write(self.style.WARNING(f"  ⊘ Skipped: {name} (already exists)"))
                    else:
                        # Create new product
                        AccessoryProduct.objects.create(
                            business=business,
                            name=name,
                            category=category,
                            brand=brand,
                            default_order_price=order_price,
                            default_selling_price=selling_price,
                        )
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Created: {name} (MK {order_price})"))

            # Summary
            self.stdout.write(f"\n{'-'*60}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Summary for {business.name}: {created_count} created, "
                    f"{updated_count} updated, {skipped_count} skipped"
                )
            )
            self.stdout.write(f"{'-'*60}\n")

        # Final summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"✓ Accessories seeded successfully for {len(businesses)} business(es)"))
        self.stdout.write(f"{'='*60}\n")
