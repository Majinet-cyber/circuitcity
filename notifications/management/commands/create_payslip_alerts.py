# notifications/management/commands/create_payslip_alerts.py
"""
Django management command to create monthly payslip alerts.

Run this daily via cron:
    0 6 * * * cd /path/to/project && python manage.py create_payslip_alerts

Or schedule it in Celery Beat (see wallet/tasks.py for example).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.services import create_monthly_payslip_alerts


class Command(BaseCommand):
    help = "Create monthly payslip reminder notifications on the 27th of each month"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating notifications",
        )
        parser.add_argument(
            "--force-date",
            type=str,
            help="Force a specific date (YYYY-MM-DD) for testing",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        force_date_str = options.get("force_date")

        # Determine the date to use
        if force_date_str:
            from datetime import datetime

            try:
                today = datetime.strptime(force_date_str, "%Y-%m-%d").date()
                self.stdout.write(f"Using forced date: {today}")
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {force_date_str}. Use YYYY-MM-DD."))
                return
        else:
            today = timezone.localdate()

        self.stdout.write(f"Running payslip alert check for {today}...")

        if today.day != 27:
            self.stdout.write(
                self.style.WARNING(f"Today is the {today.day}th, not the 27th. No alerts will be created.")
            )
            if not dry_run:
                return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No notifications will be created"))
            # TODO: Implement dry-run preview if needed
            return

        # Create the alerts
        try:
            count = create_monthly_payslip_alerts(today=today)

            if count > 0:
                self.stdout.write(self.style.SUCCESS(f"✓ Successfully created {count} payslip alert(s)"))
            else:
                self.stdout.write(
                    self.style.WARNING("No new alerts created (either not the 27th or all users already notified)")
                )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error creating payslip alerts: {e}"))
            raise
