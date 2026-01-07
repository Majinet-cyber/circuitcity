# notifications/management/commands/send_yesterday_sales_summary.py
"""
Management command to send yesterday's sales summary emails.
Should be run daily at 01:00 Africa/Blantyre (via Celery Beat or Render Cron).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, timezone as tz
from decimal import Decimal

from tenants.models import Business
from sales.models import Sale
from notifications.services import emit_event
from notifications.selectors import get_business_manager_emails


class Command(BaseCommand):
    help = "Send yesterday sales summary emails to managers"

    def handle(self, *args, **options):
        # Calculate yesterday (local time)
        now = timezone.now()
        # Africa/Blantyre is UTC+2, so we need to use local time
        local_today = now.astimezone(timezone.get_current_timezone())
        yesterday_start = (local_today - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)

        # Convert to UTC for query
        yesterday_start_utc = yesterday_start.astimezone(tz.utc)
        yesterday_end_utc = yesterday_end.astimezone(tz.utc)

        self.stdout.write(f"Processing sales from {yesterday_start} to {yesterday_end} (local time)")

        # Get all active businesses
        businesses = Business.objects.filter(status="ACTIVE")
        total_sent = 0

        for business in businesses:
            # Get sales for yesterday (Sale has location, Location has business)
            sales = Sale.objects.filter(
                location__business=business,
                created_at__gte=yesterday_start_utc,
                created_at__lt=yesterday_end_utc,
            ).select_related("item", "item__product", "agent", "location")

            sale_count = sales.count()

            if sale_count == 0:
                continue  # Skip businesses with no sales

            # Calculate totals
            from django.db.models import Sum

            total_revenue = sales.aggregate(total=Sum("price"))["total"] or Decimal("0")

            # Calculate profit if possible (requires order_price on items)
            total_profit = None
            try:
                profit_sum = Decimal("0")
                for sale in sales:
                    if hasattr(sale, "item") and sale.item:
                        cost_price = getattr(sale.item, "order_price", None) or Decimal("0")
                        profit_sum += sale.price - cost_price
                if profit_sum != Decimal("0"):
                    total_profit = profit_sum
            except Exception:
                pass

            # Get top 5 products
            from django.db.models import Count

            top_products = []
            try:
                product_sales = (
                    sales.values("item__product__name", "item__product")
                    .annotate(quantity=Count("id"))
                    .order_by("-quantity")[:5]
                )

                for ps in product_sales:
                    product_name = ps["item__product__name"] or f"Product #{ps['item__product']}"
                    top_products.append(
                        {
                            "name": product_name,
                            "quantity": ps["quantity"],
                        }
                    )
            except Exception:
                pass

            # Get recipients
            recipients = get_business_manager_emails(
                business,
                include_owner=True,
                event_type="DAILY_SUMMARY",
            )

            if not recipients:
                continue

            # Send email
            date_str = yesterday_start.strftime("%Y-%m-%d")
            dedupe_key = f"DAILY_SUMMARY:{business.id}:{date_str}"

            emit_event(
                event_type="DAILY_SUMMARY",
                recipients=recipients,
                dedupe_key=dedupe_key,
                payload={
                    "date": yesterday_start,
                    "business_name": business.name,
                    "total_sales": sale_count,
                    "total_revenue": str(total_revenue),
                    "total_profit": str(total_profit) if total_profit is not None else None,
                    "top_products": top_products,
                },
                business=business,
            )

            total_sent += len(recipients)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent summary to {len(recipients)} managers for {business.name} "
                    f"({sale_count} sales, MK {total_revenue:,.2f})"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully sent {total_sent} daily summary emails"))

        # Exit with code 0 on success (required for cron)
        return 0
