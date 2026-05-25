from decimal import Decimal

from django.core.management.base import BaseCommand

from deals.models import DeviceBrand, DeviceDeal


class Command(BaseCommand):
    help = "Seed initial TengaSale device brands and deals."

    def handle(self, *args, **options):
        deals = [
            ("TECNO", "Pop 10C", "2+64", 320000, 380000, 350000),
            ("TECNO", "Spark 40", "4+128", 400000, 480000, 450000),
            ("TECNO", "Spark 50", "4+128", 500000, 600000, 550000),
            ("TECNO", "Camon 40", "8+256", 700000, 850000, 780000),
            ("itel", "City 100", "4+128", 380000, 450000, 405000),
            ("itel", "A100", "4+128", 350000, 430000, 390000),
            ("itel", "A50", "3+64", 280000, 340000, 310000),
            ("Redmi", "A3", "4+128", 420000, 500000, 460000),
            ("Redmi", "13C", "6+128", 520000, 650000, 580000),
            ("Redmi", "A5", "4+128", 450000, 540000, 495000),
        ]

        brands = {}
        for brand_name in ["TECNO", "itel", "Redmi"]:
            brand, _ = DeviceBrand.objects.update_or_create(
                name=brand_name,
                defaults={"is_active": True},
            )
            brands[brand_name] = brand

        created = 0
        updated = 0
        for brand_name, model_name, specs, min_price, max_price, default_price in deals:
            total_loan = Decimal(default_price) * Decimal("2.5")
            deal, was_created = DeviceDeal.objects.update_or_create(
                brand=brands[brand_name],
                model_name=model_name,
                specs=specs,
                defaults={
                    "cash_price": Decimal(default_price),
                    "min_cash_price": Decimal(min_price),
                    "max_cash_price": Decimal(max_price),
                    "default_cash_price": Decimal(default_price),
                    "deposit_percent": Decimal("13"),
                    "loan_multiplier": Decimal("2.5"),
                    "term_months": 12,
                    "total_12_month_price": total_loan,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded TengaSale deals: {created} created, {updated} updated.")
        )
