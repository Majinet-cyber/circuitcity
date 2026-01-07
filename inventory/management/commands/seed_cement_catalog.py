# inventory/management/commands/seed_cement_catalog.py
"""
Management command to seed cement catalog for cement businesses.
Usage: python manage.py seed_cement_catalog [--business=SLUG]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import seed_cement_defaults
from tenants.models import Business


class Command(BaseCommand):
    help = "Seed cement catalog (sand, stones, iron bars, etc.) for cement businesses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--business",
            type=str,
            help="Business slug to seed (if omitted, seeds all cement businesses)",
        )

    def handle(self, *args, **options):
        business_slug = options.get("business")

        if business_slug:
            # Seed specific business
            try:
                business = Business.objects.get(slug=business_slug)
                if business.business_kind != BusinessKind.CEMENT:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Business '{business_slug}' is not a cement business (kind: {business.business_kind})"
                        )
                    )
                    return

                result = seed_cement_defaults(business)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Seeded {result['created']} products for '{business.name}' (skipped {result['skipped']} existing)"
                    )
                )
            except Business.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Business '{business_slug}' not found"))
        else:
            # Seed all cement businesses
            cement_businesses = Business.objects.filter(business_kind=BusinessKind.CEMENT, status="ACTIVE")
            total_created = 0
            total_skipped = 0

            for business in cement_businesses:
                result = seed_cement_defaults(business)
                total_created += result.get("created", 0)
                total_skipped += result.get("skipped", 0)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  - {business.name}: +{result['created']} products (skipped {result['skipped']})"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✅ Total: {total_created} products created, {total_skipped} skipped across {cement_businesses.count()} businesses"
                )
            )
