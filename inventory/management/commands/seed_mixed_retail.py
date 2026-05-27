# inventory/management/commands/seed_mixed_retail.py
"""
Management command to seed Mixed Retail departments, categories, and product templates.

Usage:
    python manage.py seed_mixed_retail
    python manage.py seed_mixed_retail --dry-run

Idempotent: safe to run multiple times without duplicating data.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed Mixed Retail global departments, categories, and product templates (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be seeded without writing to database",
        )
        parser.add_argument(
            "--ensure-defaults",
            metavar="BUSINESS_ID",
            type=int,
            help="After seeding, call ensure_mixed_retail_defaults for a specific business ID",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        if dry_run:
            from inventory.mixed_retail_seed import SEED_CATALOG, PRODUCT_TEMPLATE_CATALOG
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made\n"))
            total_cats = sum(len(d.get("categories", [])) for d in SEED_CATALOG)
            total_tpls = sum(len(v) for v in PRODUCT_TEMPLATE_CATALOG.values())
            self.stdout.write(
                f"Would seed:\n"
                f"  {len(SEED_CATALOG)} departments\n"
                f"  {total_cats} categories\n"
                f"  {total_tpls} product templates\n"
            )
            for dept in SEED_CATALOG:
                tpl_count = len(PRODUCT_TEMPLATE_CATALOG.get(dept["slug"], []))
                self.stdout.write(
                    f"  [{dept['slug']:30s}] {dept['name']:35s} "
                    f"({len(dept.get('categories', []))} categories, {tpl_count} templates)"
                )
            return

        self.stdout.write("Seeding Mixed Retail catalog...")

        with transaction.atomic():
            from inventory.mixed_retail_seed import seed_mixed_retail_catalog
            result = seed_mixed_retail_catalog()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone!\n"
                f"  Departments : {result['depts_created']} created, "
                f"{result['depts_skipped']} already existed\n"
                f"  Categories  : {result['cats_created']} created, "
                f"{result['cats_skipped']} already existed\n"
                f"  Templates   : {result['templates_created']} created, "
                f"{result['templates_skipped']} already existed"
            )
        )

        biz_id = options.get("ensure_defaults")
        if biz_id:
            try:
                from tenants.models import Business
                from inventory.mixed_retail_seed import ensure_mixed_retail_defaults
                biz = Business.objects.get(pk=biz_id)
                ensure_mixed_retail_defaults(biz)
                self.stdout.write(self.style.SUCCESS(
                    f"  ensure_mixed_retail_defaults applied to business #{biz_id} ({biz.name})"
                ))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  ensure_mixed_retail_defaults failed: {exc}"))
