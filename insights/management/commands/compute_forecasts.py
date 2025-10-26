from django.core.management.base import BaseCommand
from insights.services import compute_and_store_all

class Command(BaseCommand):
    help = "Compute and store short-term sales forecasts."

    def handle(self, *args, **opts):
        n = compute_and_store_all(horizon_days=7)
        self.stdout.write(self.style.SUCCESS(f"Forecast rows upserted: {n}"))


