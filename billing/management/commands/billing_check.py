from django.core.management.base import BaseCommand
from billing.models import Subscription

class Command(BaseCommand):
    help = "Expire trials/subscriptions when due."

    def handle(self, *args, **options):
        n = 0
        for s in Subscription.objects.select_related('tenant', 'plan'):
            prev = s.status
            s.expire_if_needed()
            if s.status != prev:
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Checked subscriptions. Updated: {n}"))


