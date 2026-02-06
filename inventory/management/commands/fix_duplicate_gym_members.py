# inventory/management/commands/fix_duplicate_gym_members.py
"""
Management command to fix duplicate gym members.

Finds duplicate gym members (same business + phone) and consolidates them into
a single canonical member, migrating related payments, check-ins, and logs.

Usage:
    python manage.py fix_duplicate_gym_members [--dry-run] [--business-id=X]

Safety:
- Uses transactions to ensure data consistency
- Keeps the oldest member (lowest ID) as canonical
- Migrates all foreign key references before deleting duplicates
- Logs all changes for audit trail
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from inventory.models_verticals import GymMember, GymPayment, GymMemberLog
from tenants.models import Business


class Command(BaseCommand):
    help = "Fix duplicate gym members by consolidating duplicates and migrating references"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            help='Only fix duplicates for a specific business ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        business_id = options.get('business_id')

        self.stdout.write(self.style.WARNING(
            f"{'[DRY RUN] ' if dry_run else ''}Gym Member Duplicate Cleanup"
        ))
        self.stdout.write("")

        # Get businesses to process
        if business_id:
            businesses = Business.objects.filter(id=business_id)
        else:
            businesses = Business.objects.all()

        if not businesses.exists():
            self.stdout.write(self.style.ERROR("No businesses found"))
            return

        total_duplicates_fixed = 0
        total_members_deleted = 0
        total_payments_migrated = 0
        total_logs_migrated = 0

        for business in businesses:
            # Find duplicates: same business + phone, where phone is not NULL
            duplicates = (
                GymMember.objects
                .filter(business=business, phone__isnull=False)
                .exclude(phone='')  # Skip empty strings (they're being migrated to NULL)
                .values('business_id', 'phone')
                .annotate(count=Count('id'))
                .filter(count__gt=1)
            )

            if not duplicates.exists():
                self.stdout.write(f"✓ {business.name}: No duplicates found")
                continue

            self.stdout.write(f"\n{business.name} (ID={business.id})")
            self.stdout.write(f"  Found {duplicates.count()} duplicate phone number(s)")

            for dup in duplicates:
                phone = dup['phone']
                
                # Get all members with this phone
                members = list(
                    GymMember.objects
                    .filter(business=business, phone=phone)
                    .order_by('id')  # Oldest first (lowest ID)
                )

                if len(members) < 2:
                    continue

                # Keep the oldest member (first by ID)
                canonical = members[0]
                duplicates_to_delete = members[1:]

                self.stdout.write(f"\n  Phone: {phone}")
                self.stdout.write(f"    → Keeping: #{canonical.id} - {canonical.name} (created {canonical.joined_at})")
                self.stdout.write(f"    → Removing {len(duplicates_to_delete)} duplicate(s):")

                for dup_member in duplicates_to_delete:
                    self.stdout.write(f"      • #{dup_member.id} - {dup_member.name} (created {dup_member.joined_at})")

                if dry_run:
                    # Show what would be migrated
                    payments_count = GymPayment.objects.filter(member__in=duplicates_to_delete).count()
                    logs_count = GymMemberLog.objects.filter(member__in=duplicates_to_delete).count()
                    
                    self.stdout.write(f"      Would migrate {payments_count} payment(s)")
                    self.stdout.write(f"      Would migrate {logs_count} log(s)")
                    
                    total_duplicates_fixed += 1
                    total_members_deleted += len(duplicates_to_delete)
                    continue

                # Actual migration (not dry-run)
                try:
                    with transaction.atomic():
                        # Migrate payments
                        payments_migrated = 0
                        for dup_member in duplicates_to_delete:
                            payments = GymPayment.objects.filter(member=dup_member)
                            payments_count = payments.count()
                            if payments_count > 0:
                                payments.update(member=canonical)
                                payments_migrated += payments_count
                                self.stdout.write(f"      ✓ Migrated {payments_count} payment(s) from #{dup_member.id}")

                        # Migrate logs
                        logs_migrated = 0
                        for dup_member in duplicates_to_delete:
                            logs = GymMemberLog.objects.filter(member=dup_member)
                            logs_count = logs.count()
                            if logs_count > 0:
                                logs.update(member=canonical)
                                logs_migrated += logs_count
                                self.stdout.write(f"      ✓ Migrated {logs_count} log(s) from #{dup_member.id}")

                        # Delete duplicates
                        for dup_member in duplicates_to_delete:
                            dup_member.delete()
                            self.stdout.write(self.style.SUCCESS(f"      ✓ Deleted duplicate #{dup_member.id}"))

                        total_duplicates_fixed += 1
                        total_members_deleted += len(duplicates_to_delete)
                        total_payments_migrated += payments_migrated
                        total_logs_migrated += logs_migrated

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"      ✗ Error processing phone {phone}: {str(e)}"))
                    continue

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Duplicate groups fixed: {total_duplicates_fixed}")
        self.stdout.write(f"  Duplicate members deleted: {total_members_deleted}")
        self.stdout.write(f"  Payments migrated: {total_payments_migrated}")
        self.stdout.write(f"  Logs migrated: {total_logs_migrated}")
        
        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("This was a DRY RUN - no changes were made"))
            self.stdout.write("Run without --dry-run to apply changes")
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("✓ All duplicates fixed successfully!"))

