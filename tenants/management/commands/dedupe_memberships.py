"""
Management command to clean up duplicate ACTIVE memberships.

This command finds cases where a user has multiple ACTIVE memberships for the same business,
keeps the "best" one (prefers those with location set, then most recent), and marks the
rest as REJECTED.

Usage:
    python manage.py dedupe_memberships          # Dry run (show what would be changed)
    python manage.py dedupe_memberships --apply  # Actually make the changes
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from tenants.models import Membership


class Command(BaseCommand):
    help = "Find and fix duplicate ACTIVE memberships for (user, business) pairs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually apply changes (default is dry-run)",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        
        if apply_changes:
            self.stdout.write(
                self.style.WARNING("Running in APPLY mode - changes will be saved to database")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Running in DRY-RUN mode - no changes will be saved")
            )
            self.stdout.write("Pass --apply to actually make changes")
        
        self.stdout.write("")
        
        # Find all (user_id, business_id) pairs with multiple ACTIVE memberships
        duplicates = (
            Membership.objects
            .filter(status="ACTIVE")
            .values("user_id", "business_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS("✓ No duplicate ACTIVE memberships found"))
            return
        
        self.stdout.write(
            self.style.WARNING(f"Found {len(duplicates)} (user, business) pairs with duplicates:")
        )
        self.stdout.write("")
        
        total_kept = 0
        total_deactivated = 0
        
        for dup in duplicates:
            user_id = dup["user_id"]
            business_id = dup["business_id"]
            count = dup["count"]
            
            # Get all ACTIVE memberships for this (user, business) pair
            memberships = list(
                Membership.objects
                .filter(user_id=user_id, business_id=business_id, status="ACTIVE")
                .select_related("user", "business", "location")
                .order_by("-location_id", "-created_at", "-id")
            )
            
            # Keep the first one (best by our ordering)
            keeper = memberships[0]
            to_deactivate = memberships[1:]
            
            self.stdout.write(
                f"User #{user_id} ({keeper.user.username}) @ Business #{business_id} ({keeper.business.name}): "
                f"{count} ACTIVE memberships"
            )
            
            # Show keeper details
            location_info = f" at {keeper.location.name}" if keeper.location else " (no location)"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ KEEP Membership #{keeper.id}{location_info} "
                    f"(created {keeper.created_at:%Y-%m-%d %H:%M})"
                )
            )
            total_kept += 1
            
            # Show what will be deactivated
            for m in to_deactivate:
                location_info = f" at {m.location.name}" if m.location else " (no location)"
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ DEACTIVATE Membership #{m.id}{location_info} "
                        f"(created {m.created_at:%Y-%m-%d %H:%M})"
                    )
                )
                total_deactivated += 1
            
            self.stdout.write("")
            
            # Actually deactivate if --apply was passed
            if apply_changes:
                with transaction.atomic():
                    for m in to_deactivate:
                        m.status = "REJECTED"
                        m.save(update_fields=["status"])
        
        # Summary
        self.stdout.write("")
        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully kept {total_kept} and deactivated {total_deactivated} memberships"
                )
            )
        else:
            self.stdout.write(
                f"Would keep {total_kept} and deactivate {total_deactivated} memberships"
            )
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("Run with --apply to actually make these changes")
            )

