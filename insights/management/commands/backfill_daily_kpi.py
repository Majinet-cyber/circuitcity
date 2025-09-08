from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, F
from django.utils import timezone
from datetime import timedelta
from inventory.models import Sale
from insights.models import DailyKPI

class Command(BaseCommand):
    help = "Backfill DailyKPI from sales (default 120 days)"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=120)

    def handle(self, *args, **opts):
        start = timezone.localdate() - timedelta(days=opts["days"])
        qs = (Sale.objects.filter(sold_at__date__gte=start)
              .annotate(d=F("sold_at__date"))
              .values("store_id","product_id","d")
              .annotate(units=Count("id"),
                        revenue=Sum("sale_price"),
                        profit=Sum(F("sale_price")-F("cost_price"))))
        count = 0
        for r in qs:
            DailyKPI.objects.update_or_create(
                store_id=r["store_id"], product_id=r["product_id"], d=r["d"],
                defaults={"units": r["units"], "revenue": r["revenue"] or 0, "profit": r["profit"] or 0}
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Upserted {count} DailyKPI rows"))
