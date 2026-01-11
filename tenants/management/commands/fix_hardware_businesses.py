# tenants/management/commands/fix_hardware_businesses.py
"""
Management command to fix businesses incorrectly saved as cement when they're hardware.

Usage:
    python manage.py fix_hardware_businesses --dry-run  # Preview changes
    python manage.py fix_hardware_businesses --auto     # Auto-fix with confirmation
    python manage.py fix_hardware_businesses --interactive  # Interactive fixing
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from tenants.models import Business


class Command(BaseCommand):
    help = "Fix businesses incorrectly saved as cement when they should be hardware"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )
        parser.add_argument(
            "--auto",
            action="store_true",
            help="Automatically fix (converts ALL cement to hardware - use with caution)",
        )
        parser.add_argument(
            "--interactive",
            action="store_true",
            help="Interactively review and fix each business",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        auto = options["auto"]
        interactive = options["interactive"]

        # Get all cement businesses
        cement_businesses = Business.objects.filter(business_kind="cement")

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"Found {cement_businesses.count()} businesses with business_kind='cement'")
        self.stdout.write("=" * 80 + "\n")

        if not cement_businesses.exists():
            self.stdout.write(self.style.SUCCESS("✅ No cement businesses found - nothing to fix!"))
            return

        fixed_count = 0
        skipped_count = 0

        for business in cement_businesses:
            self.stdout.write(f"\nBusiness: {business.name} (ID: {business.pk})")
            self.stdout.write(f"  business_kind: {business.business_kind}")
            self.stdout.write(f"  created_at: {business.created_at}")

            if dry_run:
                self.stdout.write(self.style.WARNING("  [DRY RUN] Would convert to 'hardware'"))
                fixed_count += 1

            elif auto:
                if not dry_run:
                    with transaction.atomic():
                        business.business_kind = "hardware"
                        business.save(update_fields=["business_kind"])
                    self.stdout.write(self.style.SUCCESS("  ✅ Converted to 'hardware'"))
                    fixed_count += 1

            elif interactive:
                response = input("\n  Convert to 'hardware'? [y/N/s(kip all)/q(uit)]: ").lower().strip()

                if response == "q":
                    self.stdout.write(self.style.WARNING("\n⚠️  Aborted by user"))
                    break
                elif response == "s":
                    self.stdout.write(self.style.WARNING("  ⏭️  Skipping remaining businesses"))
                    skipped_count += cement_businesses.count() - fixed_count
                    break
                elif response == "y":
                    with transaction.atomic():
                        business.business_kind = "hardware"
                        business.save(update_fields=["business_kind"])
                    self.stdout.write(self.style.SUCCESS("  ✅ Converted to 'hardware'"))
                    fixed_count += 1
                else:
                    self.stdout.write(self.style.WARNING("  ⏭️  Skipped"))
                    skipped_count += 1

            else:
                self.stdout.write(self.style.ERROR("  ⚠️  No action specified (use --dry-run, --auto, or --interactive)"))
                break

        # Summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("✅ Complete!"))
        self.stdout.write(f"   - Total reviewed: {cement_businesses.count()}")
        self.stdout.write(f"   - Fixed: {fixed_count}")
        self.stdout.write(f"   - Skipped: {skipped_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  This was a DRY RUN - no changes were made"))
            self.stdout.write("   Run without --dry-run to apply changes")

        self.stdout.write("=" * 80 + "\n")

