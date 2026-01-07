# inventory/management/commands/backfill_gym_member_identifiers.py
"""
Management command to backfill member_number and qr_token for existing gym members.
Safely handles existing data and avoids duplicates.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models_verticals import GymMember


class Command(BaseCommand):
    help = "Backfill member_number and qr_token for existing gym members"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--business-id",
            type=int,
            help="Only backfill members for a specific business ID",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        business_id = options.get("business_id")

        self.stdout.write(self.style.WARNING(f"{'DRY RUN: ' if dry_run else ''}Backfilling gym member identifiers..."))

        # Get members that need backfilling
        members_qs = GymMember.objects.all()
        if business_id:
            members_qs = members_qs.filter(business_id=business_id)

        # Find members missing member_number or qr_token
        members_to_update = []
        for member in members_qs:
            needs_update = False
            if not member.member_number:
                needs_update = True
            if not member.qr_token:
                needs_update = True
            if needs_update:
                members_to_update.append(member)

        total_count = len(members_to_update)

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("✓ All members already have identifiers"))
            return

        self.stdout.write(f"Found {total_count} members needing updates")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            for member in members_to_update[:10]:  # Show first 10
                status = []
                if not member.member_number:
                    status.append("missing member_number")
                if not member.qr_token:
                    status.append("missing qr_token")
                self.stdout.write(f"  - {member.name} ({member.business.name}): {', '.join(status)}")
            if total_count > 10:
                self.stdout.write(f"  ... and {total_count - 10} more")
            return

        # Perform backfill
        updated_count = 0
        error_count = 0

        with transaction.atomic():
            for member in members_to_update:
                try:
                    # Generate missing identifiers
                    if not member.member_number:
                        member.member_number = member._generate_unique_member_number()
                    if not member.qr_token:
                        member.qr_token = member._generate_unique_qr_token()

                    # Save without triggering full save logic
                    member.save(update_fields=["member_number", "qr_token"])
                    updated_count += 1

                    if updated_count % 100 == 0:
                        self.stdout.write(f"  Updated {updated_count}/{total_count}...")

                except Exception as e:
                    error_count += 1
                    self.stdout.write(self.style.ERROR(f"  Error updating {member.name} (ID: {member.id}): {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"✓ Backfill complete: {updated_count} members updated"))

        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"✗ {error_count} errors occurred"))
