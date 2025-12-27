# notifications/management/commands/retry_failed_emails.py
"""
Management command to retry failed email notifications.

Usage:
    python manage.py retry_failed_emails --limit 100

This command safely retries FAILED NotificationEvent records, respecting
deduplication keys to prevent duplicate sends.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from notifications.models import NotificationEvent
from notifications.services import dispatch_event


class Command(BaseCommand):
    help = 'Retry failed email notification events'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of failed events to retry (default: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be retried without actually retrying'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        
        if limit < 1:
            raise CommandError('Limit must be at least 1')
        
        # Get failed events, ordered by most recent first
        failed_events = NotificationEvent.objects.filter(
            status='FAILED'
        ).order_by('-created_at')[:limit]
        
        count = failed_events.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('No failed email events found.')
            )
            return
        
        self.stdout.write(
            f'Found {count} failed email event(s) to retry.'
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: Would retry the following events:')
            )
            for event in failed_events:
                self.stdout.write(
                    f'  - {event.event_type} -> {event.recipient_email} '
                    f'(created: {event.created_at}, error: {event.last_error[:100] if event.last_error else "N/A"})'
                )
            return
        
        # Retry each event
        retried = 0
        failed = 0
        
        for event in failed_events:
            try:
                # Reset status to PENDING and clear error
                event.status = 'PENDING'
                event.last_error = None
                event.save(update_fields=['status', 'last_error'])
                
                # Dispatch the event (will respect dedupe_key)
                dispatch_event(event.id)
                
                retried += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Retried: {event.event_type} -> {event.recipient_email}'
                    )
                )
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Failed to retry event {event.id}: {e}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nRetry complete: {retried} succeeded, {failed} failed'
            )
        )

