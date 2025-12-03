# inventory/management/commands/seed_phone_products.py
"""
Management command to seed default phone products for a business.
Usage:
    python manage.py seed_phone_products --business-id=<id>
    python manage.py seed_phone_products --all  # seed for all PHONES businesses
    
Populates the PhoneProductCatalog with curated products from Tecno, Itel, and Samsung.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import Business
from inventory.models_phone_products import PhoneProductCatalog


# Default phone products to seed (brand, model, ram_gb, rom_gb, cost_price, sale_price)
# Format: (brand, model_name, ram_gb, rom_gb, default_cost_price, default_selling_price)
DEFAULT_PRODUCTS = [
    # Tecno
    ("TECNO", "Spark Go 1", 1, 16, 25000, 32000),
    ("TECNO", "Pop 10c", 2, 32, 30000, 38000),
    ("TECNO", "A80", 3, 64, 42000, 52000),
    ("TECNO", "Spark 40", 4, 128, 68000, 85000),
    ("TECNO", "Camon 20", 8, 128, 95000, 120000),
    ("TECNO", "Phantom X2", 12, 256, 280000, 350000),
    ("TECNO", "Pop 10", 2, 64, 32000, 40000),
    ("TECNO", "Pop 10", 3, 64, 35000, 44000),
    ("TECNO", "Camon 40", 8, 256, 120000, 155000),
    
    # Itel
    ("ITEL", "A18", 1, 16, 22000, 28000),
    ("ITEL", "P38", 2, 32, 28000, 35000),
    ("ITEL", "S18", 3, 64, 38000, 48000),
    ("ITEL", "P55", 6, 128, 55000, 70000),
    ("ITEL", "A50", 2, 64, 30000, 38000),
    ("ITEL", "A80", 3, 128, 45000, 58000),
    ("ITEL", "A90", 3, 128, 48000, 62000),
    ("ITEL", "S25", 4, 128, 52000, 68000),
    ("ITEL", "City 100", 4, 128, 58000, 75000),
    
    # Samsung
    ("SAMSUNG", "A03", 3, 32, 48000, 62000),
    ("SAMSUNG", "A13", 4, 64, 72000, 92000),
    ("SAMSUNG", "A14", 4, 128, 95000, 122000),
    ("SAMSUNG", "A54", 8, 256, 185000, 235000),
    ("SAMSUNG", "S23", 8, 256, 420000, 530000),
    ("SAMSUNG", "Galaxy A05s", 4, 64, 65000, 85000),
    ("SAMSUNG", "Galaxy A05s", 4, 128, 75000, 95000),
    ("SAMSUNG", "Galaxy A15", 4, 128, 85000, 110000),
    ("SAMSUNG", "Galaxy A15", 6, 128, 95000, 125000),
    ("SAMSUNG", "Galaxy A25", 6, 128, 125000, 160000),
    ("SAMSUNG", "Galaxy A25", 8, 256, 155000, 195000),
]


class Command(BaseCommand):
    help = "Seed default phone products (Tecno, Itel, Samsung) for a business or all phones businesses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--business-id",
            type=int,
            help="Business ID to seed products for",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Seed for all businesses with business_kind='phones'",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating",
        )

    def handle(self, *args, **options):
        business_id = options.get("business_id")
        seed_all = options.get("all")
        dry_run = options.get("dry_run")

        if not business_id and not seed_all:
            raise CommandError("Specify --business-id=<id> or --all")

        if business_id and seed_all:
            raise CommandError("Cannot specify both --business-id and --all")

        # Determine target businesses
        if seed_all:
            businesses = Business.objects.filter(business_kind="phones")
            self.stdout.write(f"Found {businesses.count()} phones businesses")
        else:
            try:
                biz = Business.objects.get(id=business_id)
                businesses = [biz]
                self.stdout.write(f"Seeding for business: {biz.name} (ID: {biz.id})")
            except Business.DoesNotExist:
                raise CommandError(f"Business with ID {business_id} does not exist")

        if not businesses:
            self.stdout.write(self.style.WARNING("No businesses to seed"))
            return

        # Seed each business
        total_created = 0
        total_skipped = 0

        for biz in businesses:
            self.stdout.write(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {biz.name} (ID: {biz.id})")
            created, skipped = self._seed_business(biz, dry_run=dry_run)
            total_created += created
            total_skipped += skipped

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'[DRY RUN] ' if dry_run else ''}Complete! "
                f"Created: {total_created}, Skipped: {total_skipped}"
            )
        )

    @transaction.atomic
    def _seed_business(self, business: Business, dry_run: bool = False) -> tuple[int, int]:
        """
        Seed products for a single business.
        Returns (created_count, skipped_count).
        """
        created = 0
        skipped = 0

        for brand, model_name, ram_gb, rom_gb, cost_price, sale_price in DEFAULT_PRODUCTS:
            variant_label = f"{ram_gb}+{rom_gb}"

            # Check if already exists
            exists = PhoneProductCatalog.objects.filter(
                business=business,
                brand=brand,
                model_name=model_name,
                ram_gb=ram_gb,
                rom_gb=rom_gb
            ).exists()

            if exists:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f"  ⏭  {brand} {model_name} ({variant_label}) (already exists)")
                )
                continue

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [DRY] Would create: {brand} {model_name} ({variant_label}) | "
                        f"Cost: {cost_price} | Sale: {sale_price}"
                    )
                )
                created += 1
                continue

            # Create the product
            try:
                PhoneProductCatalog.objects.create(
                    business=business,
                    brand=brand,
                    model_name=model_name,
                    ram_gb=ram_gb,
                    rom_gb=rom_gb,
                    variant_label=variant_label,
                    default_cost_price=Decimal(str(cost_price)),
                    default_selling_price=Decimal(str(sale_price)),
                    is_active=True,
                    is_flagship=True,
                )
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓  Created: {brand} {model_name} ({variant_label})"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗  Failed to create {brand} {model_name} ({variant_label}): {e}"
                    )
                )
                skipped += 1

        return created, skipped
