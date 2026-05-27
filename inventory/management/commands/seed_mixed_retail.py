# inventory/management/commands/seed_mixed_retail.py
"""
Management command to seed Mixed Retail departments and categories.

Usage:
    python manage.py seed_mixed_retail

Idempotent: safe to run multiple times without duplicating data.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed Mixed Retail global departments and categories (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be seeded without writing to database",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        if dry_run:
            from inventory.mixed_retail_seed import SEED_CATALOG
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made\n"))
            total_cats = sum(len(d.get("categories", [])) for d in SEED_CATALOG)
            self.stdout.write(
                f"Would seed {len(SEED_CATALOG)} departments "
                f"and {total_cats} categories\n"
            )
            for dept in SEED_CATALOG:
                self.stdout.write(
                    f"  [{dept['slug']}] {dept['name']} "
                    f"({len(dept.get('categories', []))} categories)"
                )
            return

        self.stdout.write("Seeding Mixed Retail catalog...")

        with transaction.atomic():
            from inventory.mixed_retail_seed import seed_mixed_retail_catalog
            result = seed_mixed_retail_catalog()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Done!\n"
                f"  Departments: {result['depts_created']} created, "
                f"{result['depts_skipped']} already existed\n"
                f"  Categories:  {result['cats_created']} created, "
                f"{result['cats_skipped']} already existed"
            )
        )
