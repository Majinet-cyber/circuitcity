"""
Management command: seed_tengasale_demo

Creates comprehensive synthetic demo data for TengaSale pilot use.
All names, IDs, phones, and contracts are clearly fictional.

Portfolio:
  3 pending applications (no portal contracts)
  2 active contracts (paying on time)
  1 overdue contract (missed payments)
  1 completed contract (fully paid)
  1 locked demo contract (device locked for non-payment)
  Wallet transactions
  Payment history

Seeded phones (per spec):
  Itel City 100, Tecno Pop 20, Tecno Spark 20, Tecno Spark 30,
  Infinix Smart 8, Infinix Hot 40, Samsung A05, Samsung A06,
  Redmi A3, Redmi 13C

Usage:
    python manage.py seed_tengasale_demo
    python manage.py seed_tengasale_demo --clear
    python manage.py seed_tengasale_demo --clear --quiet
"""

from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import PaymentContract, PaymentTransaction


# ---------------------------------------------------------------------------
# Demo contract data
# ---------------------------------------------------------------------------

DEMO_CONTRACTS = [
    # ── Active — paying on time ───────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000001",
        "payg_number": "TSG100001",
        "customer_name": "DEMO Chisomo Phiri",
        "customer_phone": "+265881110001",
        "customer_national_id": "DEMO-NID-0001",
        "device_model": "Tecno Spark 30",
        "total_amount": Decimal("55000"),
        "deposit_paid": Decimal("7150"),
        "amount_paid": Decimal("25000"),
        "daily_price": Decimal("153"),
        "thirty_day_price": Decimal("4583"),
        "term_months": 12,
        "start_date_offset": -90,   # days from today
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    {
        "contract_number": "TS-MW-10000002",
        "payg_number": "TSG100002",
        "customer_name": "DEMO Tandiwe Chirwa",
        "customer_phone": "+265991110002",
        "customer_national_id": "DEMO-NID-0002",
        "device_model": "Samsung A06",
        "total_amount": Decimal("72000"),
        "deposit_paid": Decimal("9360"),
        "amount_paid": Decimal("18000"),
        "daily_price": Decimal("200"),
        "thirty_day_price": Decimal("6000"),
        "term_months": 12,
        "start_date_offset": -45,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Overdue — missed payments ─────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000003",
        "payg_number": "TSG100003",
        "customer_name": "DEMO Kondwani Mwale",
        "customer_phone": "+265881110003",
        "customer_national_id": "DEMO-NID-0003",
        "device_model": "Infinix Hot 40",
        "total_amount": Decimal("68500"),
        "deposit_paid": Decimal("8905"),
        "amount_paid": Decimal("12000"),
        "daily_price": Decimal("190"),
        "thirty_day_price": Decimal("5708"),
        "term_months": 12,
        "start_date_offset": -120,
        "status": "overdue",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Completed — fully paid ───────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000004",
        "payg_number": "TSG100004",
        "customer_name": "DEMO Abigail Nyirenda",
        "customer_phone": "+265881110004",
        "customer_national_id": "DEMO-NID-0004",
        "device_model": "Itel City 100",
        "total_amount": Decimal("28000"),
        "deposit_paid": Decimal("3640"),
        "amount_paid": Decimal("28000"),
        "daily_price": Decimal("0"),
        "thirty_day_price": Decimal("0"),
        "term_months": 6,
        "start_date_offset": -200,
        "status": "completed",
        "device_lock_provider": "",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "none",
    },
    # ── Locked — device locked for non-payment ───────────────────────────
    {
        "contract_number": "TS-MW-10000005",
        "payg_number": "TSG100005",
        "customer_name": "DEMO Precious Banda",
        "customer_phone": "+265991110005",
        "customer_national_id": "DEMO-NID-0005",
        "device_model": "Redmi A3",
        "total_amount": Decimal("42000"),
        "deposit_paid": Decimal("5460"),
        "amount_paid": Decimal("8400"),
        "daily_price": Decimal("117"),
        "thirty_day_price": Decimal("3500"),
        "term_months": 12,
        "start_date_offset": -180,
        "status": "locked",
        "device_lock_provider": "mock",
        "device_lock_status": "locked",
        "device_enrollment_status": "enrolled",
    },
    # ── Active — recent contract ──────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000006",
        "payg_number": "TSG100006",
        "customer_name": "DEMO James Kaunda",
        "customer_phone": "+265881110006",
        "customer_national_id": "DEMO-NID-0006",
        "device_model": "Tecno Pop 20",
        "total_amount": Decimal("38000"),
        "deposit_paid": Decimal("4940"),
        "amount_paid": Decimal("5000"),
        "daily_price": Decimal("106"),
        "thirty_day_price": Decimal("3167"),
        "term_months": 12,
        "start_date_offset": -25,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Active — Infinix Smart ────────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000007",
        "payg_number": "TSG100007",
        "customer_name": "DEMO Grace Tembo",
        "customer_phone": "+265991110007",
        "customer_national_id": "DEMO-NID-0007",
        "device_model": "Infinix Smart 8",
        "total_amount": Decimal("32000"),
        "deposit_paid": Decimal("4160"),
        "amount_paid": Decimal("8000"),
        "daily_price": Decimal("89"),
        "thirty_day_price": Decimal("2667"),
        "term_months": 12,
        "start_date_offset": -60,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Active — Samsung A05 ──────────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000008",
        "payg_number": "TSG100008",
        "customer_name": "DEMO Peter Nkhata",
        "customer_phone": "+265881110008",
        "customer_national_id": "DEMO-NID-0008",
        "device_model": "Samsung A05",
        "total_amount": Decimal("58000"),
        "deposit_paid": Decimal("7540"),
        "amount_paid": Decimal("15000"),
        "daily_price": Decimal("161"),
        "thirty_day_price": Decimal("4833"),
        "term_months": 12,
        "start_date_offset": -75,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Active — Tecno Spark 20 ───────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000009",
        "payg_number": "TSG100009",
        "customer_name": "DEMO Dalitso Kamanga",
        "customer_phone": "+265991110009",
        "customer_national_id": "DEMO-NID-0009",
        "device_model": "Tecno Spark 20",
        "total_amount": Decimal("48000"),
        "deposit_paid": Decimal("6240"),
        "amount_paid": Decimal("9600"),
        "daily_price": Decimal("133"),
        "thirty_day_price": Decimal("4000"),
        "term_months": 12,
        "start_date_offset": -50,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
    # ── Active — Redmi 13C ────────────────────────────────────────────────
    {
        "contract_number": "TS-MW-10000010",
        "payg_number": "TSG100010",
        "customer_name": "DEMO Lovemore Dube",
        "customer_phone": "+265881110010",
        "customer_national_id": "DEMO-NID-0010",
        "device_model": "Redmi 13C",
        "total_amount": Decimal("52000"),
        "deposit_paid": Decimal("6760"),
        "amount_paid": Decimal("5200"),
        "daily_price": Decimal("144"),
        "thirty_day_price": Decimal("4333"),
        "term_months": 12,
        "start_date_offset": -20,
        "status": "active",
        "device_lock_provider": "mock",
        "device_lock_status": "unlocked",
        "device_enrollment_status": "enrolled",
    },
]


# ---------------------------------------------------------------------------
# Demo payment history
# ---------------------------------------------------------------------------

DEMO_PAYMENTS = [
    # Contract 1 — Tecno Spark 30, active
    ("TS-MW-10000001", Decimal("5000"), "paid", "+265881110001", -85),
    ("TS-MW-10000001", Decimal("5000"), "paid", "+265881110001", -55),
    ("TS-MW-10000001", Decimal("5000"), "paid", "+265881110001", -25),
    ("TS-MW-10000001", Decimal("5000"), "paid", "+265881110001", -5),
    ("TS-MW-10000001", Decimal("5000"), "paid", "+265881110001", 0),

    # Contract 2 — Samsung A06, active
    ("TS-MW-10000002", Decimal("6000"), "paid", "+265991110002", -40),
    ("TS-MW-10000002", Decimal("6000"), "paid", "+265991110002", -10),
    ("TS-MW-10000002", Decimal("6000"), "failed", "+265991110002", -7),   # failed attempt

    # Contract 3 — Infinix Hot 40, overdue
    ("TS-MW-10000003", Decimal("5800"), "paid", "+265881110003", -115),
    ("TS-MW-10000003", Decimal("6200"), "paid", "+265881110003", -85),
    ("TS-MW-10000003", Decimal("5000"), "failed", "+265881110003", -50),  # failed

    # Contract 4 — Itel City 100, completed
    ("TS-MW-10000004", Decimal("5000"), "paid", "+265881110004", -190),
    ("TS-MW-10000004", Decimal("5000"), "paid", "+265881110004", -160),
    ("TS-MW-10000004", Decimal("5000"), "paid", "+265881110004", -130),
    ("TS-MW-10000004", Decimal("5000"), "paid", "+265881110004", -100),
    ("TS-MW-10000004", Decimal("5000"), "paid", "+265881110004", -70),
    ("TS-MW-10000004", Decimal("3000"), "paid", "+265881110004", -40),

    # Contract 5 — Redmi A3, locked
    ("TS-MW-10000005", Decimal("4200"), "paid", "+265991110005", -170),
    ("TS-MW-10000005", Decimal("4200"), "paid", "+265991110005", -140),
    ("TS-MW-10000005", Decimal("4000"), "failed", "+265991110005", -110),  # missed
    ("TS-MW-10000005", Decimal("4000"), "failed", "+265991110005", -80),   # missed

    # Contract 6 — Tecno Pop 20, active recent
    ("TS-MW-10000006", Decimal("5000"), "paid", "+265881110006", -20),

    # Contract 7 — Infinix Smart 8
    ("TS-MW-10000007", Decimal("4000"), "paid", "+265991110007", -55),
    ("TS-MW-10000007", Decimal("4000"), "paid", "+265991110007", -25),

    # Contract 8 — Samsung A05
    ("TS-MW-10000008", Decimal("5000"), "paid", "+265881110008", -70),
    ("TS-MW-10000008", Decimal("5000"), "paid", "+265881110008", -40),
    ("TS-MW-10000008", Decimal("5000"), "paid", "+265881110008", -10),

    # Contract 9 — Tecno Spark 20
    ("TS-MW-10000009", Decimal("4800"), "paid", "+265991110009", -45),
    ("TS-MW-10000009", Decimal("4800"), "paid", "+265991110009", -15),

    # Contract 10 — Redmi 13C
    ("TS-MW-10000010", Decimal("5200"), "paid", "+265881110010", -15),
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Create comprehensive synthetic demo data for TengaSale pilot. "
        "All names, IDs, and phones are fictional and clearly marked DEMO."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing demo contracts before seeding (TS-MW-100000xx range).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-record output.",
        )

    def handle(self, *args, **options):
        quiet = options["quiet"]

        if options["clear"]:
            demo_numbers = [c["contract_number"] for c in DEMO_CONTRACTS]
            deleted, _ = PaymentContract.objects.filter(
                contract_number__in=demo_numbers
            ).delete()
            self.stdout.write(f"Cleared {deleted} existing demo contracts.")

        today = date.today()
        created_count = 0
        updated_count = 0

        for raw in DEMO_CONTRACTS:
            data = dict(raw)
            contract_number = data.pop("contract_number")
            payg_number = data.pop("payg_number")
            start_offset = data.pop("start_date_offset", 0)

            start_date = today + timedelta(days=start_offset)
            data["start_date"] = start_date

            daily_price = data.get("daily_price", Decimal("0"))
            amount_paid = data.get("amount_paid", Decimal("0"))

            if daily_price > 0:
                days_paid = int(amount_paid / daily_price)
            else:
                days_paid = int((today - start_date).days)

            data["due_date"] = start_date + timedelta(days=days_paid)
            data["lock_date"] = start_date + timedelta(days=days_paid + 3)

            contract, created = PaymentContract.objects.update_or_create(
                contract_number=contract_number,
                defaults={"payg_number": payg_number, **data},
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            if not quiet:
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"  {action}: {contract.contract_number} "
                    f"({contract.status}) — {contract.customer_name} — {contract.device_model}"
                )

        # Seed demo payments
        tx_count = 0
        for contract_number, amount, status, phone, day_offset in DEMO_PAYMENTS:
            try:
                contract = PaymentContract.objects.get(contract_number=contract_number)
            except PaymentContract.DoesNotExist:
                continue

            paid_at = None
            if status == "paid":
                payment_date = today + timedelta(days=day_offset)
                paid_at = timezone.make_aware(
                    timezone.datetime(
                        payment_date.year, payment_date.month, payment_date.day,
                        10, 30, 0
                    )
                )

            PaymentTransaction.objects.create(
                payment_contract=contract,
                provider="mock",
                amount=amount,
                currency="MWK",
                phone=phone,
                status=status,
                paid_at=paid_at,
                raw_response={"demo": True, "seeded": True},
            )
            tx_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDemo data seeded: "
                f"{created_count} created, {updated_count} updated, "
                f"{tx_count} transactions."
            )
        )
        self.stdout.write("\nDemo contract access (test at /pay/):")
        for c in DEMO_CONTRACTS:
            self.stdout.write(
                f"  {c['contract_number']} / {c['payg_number']} — "
                f"{c['customer_name'].replace('DEMO ', '')} — {c['status'].upper()}"
            )
        self.stdout.write(
            "\n  Payment portal: http://localhost:8000/pay/"
            "\n  Admin: http://localhost:8000/admin/portal/paymentcontract/"
        )
