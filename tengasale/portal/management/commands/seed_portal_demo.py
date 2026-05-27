"""
Management command: seed_portal_demo

Creates 3 safe synthetic demo PaymentContracts for testing the customer portal.
All data is fictional — no real customer IDs or faces.

Usage:
    python manage.py seed_portal_demo
    python manage.py seed_portal_demo --clear
"""

from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import PaymentContract, PaymentTransaction


DEMO_CONTRACTS = [
    {
        "contract_number": "TS-MW-00000001",
        "payg_number": "TSG000001",
        "customer_name": "Demo Customer A",
        "customer_phone": "+265881000001",
        "customer_national_id": "DEM00001",
        "device_model": "Tecno Pop 20 4G",
        "total_amount": Decimal("45000.00"),
        "deposit_paid": Decimal("5850.00"),
        "amount_paid": Decimal("28000.00"),
        "daily_price": Decimal("117.00"),
        "thirty_day_price": Decimal("3500.00"),
        "term_months": 12,
        "start_date": date.today() - timedelta(days=100),
        "status": "active",
    },
    {
        "contract_number": "TS-MW-00000002",
        "payg_number": "TSG000002",
        "customer_name": "Demo Customer B",
        "customer_phone": "+265991000002",
        "customer_national_id": "DEM00002",
        "device_model": "Samsung Galaxy A15",
        "total_amount": Decimal("72500.00"),
        "deposit_paid": Decimal("9425.00"),
        "amount_paid": Decimal("10000.00"),
        "daily_price": Decimal("173.00"),
        "thirty_day_price": Decimal("5208.00"),
        "term_months": 12,
        "start_date": date.today() - timedelta(days=30),
        "status": "overdue",
    },
    {
        "contract_number": "TS-MW-00000003",
        "payg_number": "TSG000003",
        "customer_name": "Demo Customer C",
        "customer_phone": "+265881000003",
        "customer_national_id": "DEM00003",
        "device_model": "Itel City 100",
        "total_amount": Decimal("28000.00"),
        "deposit_paid": Decimal("3640.00"),
        "amount_paid": Decimal("28000.00"),
        "daily_price": Decimal("0.00"),
        "thirty_day_price": Decimal("0.00"),
        "term_months": 6,
        "start_date": date.today() - timedelta(days=180),
        "status": "completed",
    },
]

DEMO_PAYMENTS = [
    # Payments for contract 1
    ("TS-MW-00000001", Decimal("3500.00"), "paid", "+265881000001"),
    ("TS-MW-00000001", Decimal("3500.00"), "paid", "+265881000001"),
    ("TS-MW-00000001", Decimal("7000.00"), "paid", "+265881000001"),
    ("TS-MW-00000001", Decimal("7000.00"), "paid", "+265881000001"),
    ("TS-MW-00000001", Decimal("3500.00"), "paid", "+265881000001"),
    ("TS-MW-00000001", Decimal("3500.00"), "failed", "+265881000001"),
    # Payments for contract 2
    ("TS-MW-00000002", Decimal("5200.00"), "paid", "+265991000002"),
    ("TS-MW-00000002", Decimal("4800.00"), "paid", "+265991000002"),
    # Payments for contract 3 (completed)
    ("TS-MW-00000003", Decimal("5000.00"), "paid", "+265881000003"),
    ("TS-MW-00000003", Decimal("5000.00"), "paid", "+265881000003"),
    ("TS-MW-00000003", Decimal("5000.00"), "paid", "+265881000003"),
    ("TS-MW-00000003", Decimal("5000.00"), "paid", "+265881000003"),
    ("TS-MW-00000003", Decimal("5000.00"), "paid", "+265881000003"),
    ("TS-MW-00000003", Decimal("3000.00"), "paid", "+265881000003"),
]


class Command(BaseCommand):
    help = "Create synthetic demo contracts for portal testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing demo contracts before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            demo_numbers = [c["contract_number"] for c in DEMO_CONTRACTS]
            deleted, _ = PaymentContract.objects.filter(contract_number__in=demo_numbers).delete()
            self.stdout.write(f"Deleted {deleted} existing demo contracts.")

        created_count = 0
        for raw in DEMO_CONTRACTS:
            data = dict(raw)
            contract_number = data.pop("contract_number")
            payg_number = data.pop("payg_number")

            daily_price = data.get("daily_price", Decimal("0"))
            amount_paid = data.get("amount_paid", Decimal("0"))
            start_date = data.get("start_date", date.today())

            if daily_price > 0:
                days_paid = int(amount_paid / daily_price)
            else:
                days_paid = 360

            data["due_date"] = start_date + timedelta(days=days_paid)
            data["lock_date"] = start_date + timedelta(days=days_paid + 3)

            contract, created = PaymentContract.objects.update_or_create(
                contract_number=contract_number,
                defaults={
                    "payg_number": payg_number,
                    **data,
                },
            )

            if created:
                created_count += 1
                self.stdout.write(f"  Created: {contract.contract_number} / {contract.payg_number} — {contract.customer_name}")
            else:
                self.stdout.write(f"  Updated: {contract.contract_number} — {contract.customer_name}")

        # Seed demo payments
        tx_count = 0
        for contract_number, amount, status, phone in DEMO_PAYMENTS:
            try:
                contract = PaymentContract.objects.get(contract_number=contract_number)
            except PaymentContract.DoesNotExist:
                continue
            tx = PaymentTransaction.objects.create(
                payment_contract=contract,
                provider="mock",
                amount=amount,
                currency="MWK",
                phone=phone,
                status=status,
                paid_at=timezone.now() if status == "paid" else None,
                raw_response={"demo": True},
            )
            tx_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeded {created_count} new contracts and {tx_count} demo transactions."
            )
        )
        self.stdout.write("\nDemo access:")
        for c in DEMO_CONTRACTS:
            self.stdout.write(f"  Contract: TS-MW-{c.get('contract_number', '?')[-8:]}")
        self.stdout.write(
            "\nTest the portal at: http://localhost:8000/pay/"
        )
