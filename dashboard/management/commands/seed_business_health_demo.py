from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Create safe, explicit demo data for Business Health scoring."

    def add_arguments(self, parser):
        parser.add_argument("--business-id", type=int, required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        from inventory.models import (
            InventoryItem,
            Location,
            Product,
            RecurringCost,
            RecurringCostCategory,
            RecurringCostFrequency,
        )
        from sales.models import Sale
        from tenants.models import Business, Membership

        business_id = options["business_id"]
        try:
            business = Business.objects.get(pk=business_id)
        except Business.DoesNotExist as exc:
            raise CommandError(f"Business {business_id} does not exist.") from exc

        user = (
            Membership.objects.filter(business=business, status="ACTIVE")
            .select_related("user")
            .order_by("id")
            .first()
        )
        user = user.user if user else getattr(business, "created_by", None)

        location = Location.ensure_default_for_business(business)
        if location is None:
            location = Location.objects.create(
                business=business,
                name="Demo Store",
                city="Lilongwe",
                is_default=True,
            )

        product, _ = Product.objects.get_or_create(
            code=f"BH-DEMO-{business.pk}",
            defaults={
                "name": "Business Health Demo Phone",
                "brand": "Emajinet",
                "model": f"Health Demo {business.pk}",
                "variant": "Standard",
                "cost_price": Decimal("85000.00"),
                "sale_price": Decimal("125000.00"),
                "low_stock_threshold": 4,
            },
        )

        today = timezone.localdate()
        sold_created = 0
        stock_created = 0

        for index in range(24):
            sold_date = today - timedelta(days=(index * 3) % 72)
            imei = f"86{business.pk:04d}{index:09d}"[-15:]
            item, created = InventoryItem.all_objects.get_or_create(
                imei=imei,
                defaults={
                    "business": business,
                    "product": product,
                    "received_at": sold_date - timedelta(days=12),
                    "order_price": Decimal("85000.00") + Decimal(index % 4) * Decimal("2500.00"),
                    "selling_price": Decimal("120000.00") + Decimal(index % 5) * Decimal("4000.00"),
                    "status": "SOLD",
                    "current_location": location,
                    "sold_at": timezone.make_aware(datetime.combine(sold_date, time.min)),
                    "sold_by": user,
                    "is_active": True,
                },
            )
            if created:
                sold_created += 1
            Sale.objects.get_or_create(
                item=item,
                defaults={
                    "agent": user,
                    "location": location,
                    "sold_at": sold_date,
                    "price": item.selling_price or Decimal("0.00"),
                    "payment_method": "CASH",
                },
            )

        for index in range(10):
            imei = f"87{business.pk:04d}{index:09d}"[-15:]
            _, created = InventoryItem.all_objects.get_or_create(
                imei=imei,
                defaults={
                    "business": business,
                    "product": product,
                    "received_at": today - timedelta(days=index + 5),
                    "order_price": Decimal("86000.00"),
                    "selling_price": Decimal("128000.00"),
                    "status": "IN_STOCK",
                    "current_location": location,
                    "is_active": True,
                },
            )
            if created:
                stock_created += 1

        recurring_specs = [
            ("Demo Rent", RecurringCostCategory.RENT, Decimal("180000.00")),
            ("Demo Utilities", RecurringCostCategory.UTILITIES, Decimal("45000.00")),
            ("Demo Internet", RecurringCostCategory.INTERNET, Decimal("35000.00")),
        ]
        recurring_created = 0
        for name, category, amount in recurring_specs:
            _, created = RecurringCost.objects.get_or_create(
                business=business,
                name=name,
                defaults={
                    "category": category,
                    "amount": amount,
                    "frequency": RecurringCostFrequency.MONTHLY,
                    "is_active": True,
                    "next_run_date": today + timedelta(days=30),
                    "created_by": user,
                    "notes": "Created by seed_business_health_demo for development/demo use.",
                },
            )
            if created:
                recurring_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded business health demo data for "
                f"{business.name}: {sold_created} sold items, {stock_created} stock items, "
                f"{recurring_created} recurring costs."
            )
        )
