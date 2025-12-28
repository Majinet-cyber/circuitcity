# notifications/management/commands/send_weekly_sales_digest.py
"""
Django management command to send weekly sales digest emails to managers.

This command calculates last 7 days (Mon-Sun week ending Friday) and sends summary emails.

Run this weekly via Render Cron or system cron:
    # Every Friday at 5pm Malawi time (15:00 UTC)
    0 15 * * 5 cd /path/to/project && python manage.py send_weekly_sales_digest

Or schedule it in Celery Beat (see notifications/tasks.py).

Note: Malawi is UTC+2, so 17:00 Malawi = 15:00 UTC
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
import pytz


class Command(BaseCommand):
    help = 'Send weekly sales digest emails to managers (runs Friday 5pm Malawi time)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--business-id',
            type=int,
            help='Send digest for specific business only (for testing)',
        )
        parser.add_argument(
            '--week-ending',
            type=str,
            help='Force a specific week ending date (YYYY-MM-DD) for testing',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails',
        )
    
    def handle(self, *args, **options):
        from notifications.services import send_weekly_sales_digest
        from tenants.models import Business
        
        business_id = options.get('business_id')
        week_ending_str = options.get('week_ending')
        dry_run = options.get('dry_run', False)
        
        # Get business if specified
        business = None
        if business_id:
            try:
                business = Business.objects.get(id=business_id)
                self.stdout.write(f"Sending digest for business: {business.name}")
            except Business.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Business with ID {business_id} not found"))
                return
        
        # Parse week ending date if provided
        week_ending_date = None
        if week_ending_str:
            try:
                week_ending_date = date.fromisoformat(week_ending_str)
                self.stdout.write(f"Using forced week ending date: {week_ending_date}")
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {week_ending_str}. Use YYYY-MM-DD."))
                return
        
        # Check if it's Friday (Malawi time)
        malawi_tz = pytz.timezone('Africa/Blantyre')
        now_malawi = timezone.now().astimezone(malawi_tz)
        
        if not week_ending_date and not business_id:
            # Only check day of week if not forcing date and not testing specific business
            if now_malawi.weekday() != 4:  # 4 = Friday
                self.stdout.write(self.style.WARNING(
                    f"Today is {now_malawi.strftime('%A')}, not Friday. "
                    f"Digest is typically sent on Fridays at 5pm Malawi time."
                ))
                if not dry_run:
                    self.stdout.write("Use --week-ending to force a specific date for testing.")
                    return
            
            # Check if it's after 5pm
            if now_malawi.hour < 17:
                self.stdout.write(self.style.WARNING(
                    f"Current time is {now_malawi.strftime('%H:%M')} Malawi time. "
                    f"Digest is typically sent at 17:00 (5pm)."
                ))
                if not dry_run:
                    self.stdout.write("Use --week-ending to force a specific date for testing.")
                    return
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No emails will be sent"))
            # TODO: Implement dry-run preview if needed
            return
        
        # Send digests
        try:
            emails_sent = send_weekly_sales_digest(
                business=business,
                week_ending_date=week_ending_date
            )
            
            if emails_sent > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Successfully sent {emails_sent} weekly digest email(s)"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    "No emails sent (no businesses with sales or no managers with digest enabled)"
                ))
        
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error sending weekly digests: {e}"))
            raise

