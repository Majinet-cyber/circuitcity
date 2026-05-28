"""
seed_tengasale_demo — Phase 7 demo data seeder.

Usage:
    python manage.py seed_tengasale_demo
    python manage.py seed_tengasale_demo --clear

Creates:
  - Merchant, underwriter/manager, and agent users
  - Queue applications (pending_review) visible in /sales/
  - Active applications (under_review) claimed by the manager
  - Manager wallet with commission transactions
  - Monthly ManagerPayout records showing gross / WHT 20% / net
  - MerchantPayout records (cash price, no WHT)
  - Contracts with payment history
"""
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.utils import assign_role
from applications.models import FinancingApplication
from core.models import QueueRule
from deals.models import DeviceBrand, DeviceDeal
from earnings.models import ManagerPayout, MerchantPayout, Wallet, WalletTransaction
from geography.models import District, Region

User = get_user_model()


class Command(BaseCommand):
    help = "Seed Phase 7 demo data: applications, wallets, payouts with WHT."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing demo data before seeding.")

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear()

        self._ensure_queue_rule()
        merchant, manager, agent = self._create_users()
        deals = self._get_or_create_deals()
        self._create_applications(merchant, manager, agent, deals)
        self._create_manager_wallet(manager)
        self._create_merchant_payouts(merchant, deals)

        self.stdout.write(self.style.SUCCESS("\nDemo seed complete. Open /sales/ to see the queue."))

    # ─────────────────────────────────────────────────────────────────────────

    def _clear(self):
        self.stdout.write("Clearing existing demo data...")
        for username in ("demo_merchant", "demo_manager", "demo_agent"):
            User.objects.filter(username=username).delete()
        QueueRule.objects.filter(country="MW").delete()
        self.stdout.write(self.style.WARNING("  Cleared."))

    def _ensure_queue_rule(self):
        QueueRule.objects.get_or_create(
            country="MW",
            defaults={
                "max_active_applications": 5,
                "cooldown_minutes": 0,
            },
        )

    def _create_users(self):
        def _get_or_create(username, first, last, role):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@tengasale.demo",
                    "is_active": True,
                },
            )
            if created:
                user.set_password("demo1234!")
                user.save()
                assign_role(user, role)
                self.stdout.write(f"  Created user: {username} (role={role})")
            return user

        merchant = _get_or_create("demo_merchant", "Moses", "Banda", "merchant")
        manager = _get_or_create("demo_manager", "Grace", "Phiri", "underwriter")
        agent = _get_or_create("demo_agent", "John", "Tembo", "merchant")
        return merchant, manager, agent

    def _get_or_create_deals(self):
        brand, _ = DeviceBrand.objects.get_or_create(name="TECNO", defaults={"is_active": True})
        deals = []
        specs_list = [
            ("Spark 40", "4+128", 450000),
            ("Camon 40", "8+256", 780000),
            ("Pop 10C", "2+64", 350000),
            ("Spark 50", "4+128", 550000),
            ("itel City 100", "4+128", 405000),
        ]
        for model_name, specs, price in specs_list:
            total_loan = Decimal(price) * Decimal("2.5")
            deal, _ = DeviceDeal.objects.get_or_create(
                brand=brand,
                model_name=model_name,
                specs=specs,
                defaults={
                    "cash_price": Decimal(price),
                    "min_cash_price": Decimal(price),
                    "max_cash_price": Decimal(price),
                    "default_cash_price": Decimal(price),
                    "deposit_percent": Decimal("13"),
                    "loan_multiplier": Decimal("2.5"),
                    "term_months": 12,
                    "total_12_month_price": total_loan,
                    "is_active": True,
                },
            )
            deals.append(deal)
        return deals

    def _create_applications(self, merchant, manager, agent, deals):
        now = timezone.now()
        created = 0

        # Applications pending in queue (visible in /sales/)
        pending_customers = [
            ("Chisomo Banda", "265991234001", "MW-NID-001", deals[0]),
            ("Mphatso Phiri", "265991234002", "MW-NID-002", deals[1]),
            ("Thandiwe Mvula", "265991234003", "MW-NID-003", deals[2]),
            ("Felix Lungu",   "265991234004", "MW-NID-004", deals[3]),
            ("Grace Mwale",   "265991234005", "MW-NID-005", deals[4]),
        ]
        for i, (name, phone, nid, deal) in enumerate(pending_customers):
            app_num = f"TS-DEMO-{2600 + i}"
            if not FinancingApplication.objects.filter(application_number=app_num).exists():
                FinancingApplication.objects.create(
                    application_number=app_num,
                    created_by=merchant,
                    status="pending_review",
                    review_status="pending_review",
                    customer_name=name,
                    customer_phone=phone,
                    national_id=nid,
                    deal=deal,
                    calculated_monthly_payment=Decimal(deal.cash_price) * Decimal("2.5") / 12,
                    calculated_total_loan=Decimal(deal.cash_price) * Decimal("2.5"),
                    exact_monthly_income=Decimal("150000"),
                    submitted_at=now - timedelta(hours=i + 1),
                )
                created += 1

        # One application under review by the manager
        app_num = "TS-DEMO-9001"
        if not FinancingApplication.objects.filter(application_number=app_num).exists():
            FinancingApplication.objects.create(
                application_number=app_num,
                created_by=merchant,
                claimed_by=manager,
                claimed_at=now - timedelta(minutes=30),
                status="under_review",
                review_status="under_review",
                customer_name="Patrick Nkhoma",
                customer_phone="265991299999",
                national_id="MW-NID-999",
                deal=deals[0],
                calculated_monthly_payment=Decimal(deals[0].cash_price) * Decimal("2.5") / 12,
                calculated_total_loan=Decimal(deals[0].cash_price) * Decimal("2.5"),
                exact_monthly_income=Decimal("200000"),
                submitted_at=now - timedelta(hours=2),
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"  Created {created} demo applications."))

    def _create_manager_wallet(self, manager):
        wallet, _ = Wallet.objects.get_or_create(user=manager)

        # Ensure wallet has some balance
        if wallet.balance == 0 and wallet.total_earned == 0:
            wallet.balance = Decimal("210000.00")
            wallet.total_earned = Decimal("350000.00")
            wallet.total_paid = Decimal("112000.00")
            wallet.total_wht_withheld = Decimal("28000.00")
            wallet.save()

            # Commission transaction
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="commission_credit",
                amount=Decimal("30000.00"),
                description="Commission: TS-DEMO-8001",
                contract_number="TS-DEMO-8001",
            )
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="commission_credit",
                amount=Decimal("28000.00"),
                description="Commission: TS-DEMO-8002",
                contract_number="TS-DEMO-8002",
            )
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="wht_deduction",
                amount=Decimal("-14000.00"),
                description="WHT Deduction: Apr 2026 payout",
            )
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="payout_debit",
                amount=Decimal("-56000.00"),
                description="Payout: Apr 2026",
            )
            self.stdout.write("  Created wallet transactions for demo_manager.")

        # Monthly payout records
        if not ManagerPayout.objects.filter(wallet=wallet).exists():
            # April 2026 — paid
            p1 = ManagerPayout(
                wallet=wallet,
                period_start=date(2026, 4, 1),
                period_end=date(2026, 4, 30),
                gross_amount=Decimal("70000.00"),
                wht_rate=Decimal("0.2000"),
                destination_phone="+265991111222",
                provider="airtel",
                reference="PAY-APR-2026-001",
            )
            p1.save()
            p1.mark_paid(reference="PAY-APR-2026-001", provider="airtel", paid_at=timezone.now() - timedelta(days=27))

            # May 2026 — pending
            p2 = ManagerPayout(
                wallet=wallet,
                period_start=date(2026, 5, 1),
                period_end=date(2026, 5, 31),
                gross_amount=Decimal("58000.00"),
                wht_rate=Decimal("0.2000"),
                destination_phone="+265991111222",
                provider="airtel",
            )
            p2.save()

            self.stdout.write(self.style.SUCCESS(
                f"  Created ManagerPayout records: "
                f"Apr gross=70,000 WHT=14,000 net=56,000 (PAID), "
                f"May gross=58,000 WHT=11,600 net=46,400 (PENDING)"
            ))

    def _create_merchant_payouts(self, merchant, deals):
        if MerchantPayout.objects.filter(merchant=merchant).exists():
            return

        contracts = [
            ("TS-C-8001", deals[0]),
            ("TS-C-8002", deals[1]),
            ("TS-C-8003", deals[4]),
        ]
        for contract_num, deal in contracts:
            payout = MerchantPayout.objects.create(
                merchant=merchant,
                contract_number=contract_num,
                device_description=f"{deal.brand.name} {deal.model_name} {deal.specs}",
                cash_price=deal.cash_price,
            )

        # Mark one as paid
        paid = MerchantPayout.objects.filter(merchant=merchant).first()
        if paid and paid.status == "pending":
            paid.mark_paid(reference="MPAY-001", provider="airtel")

        self.stdout.write(self.style.SUCCESS(
            f"  Created {len(contracts)} MerchantPayout records for demo_merchant (no WHT)."
        ))
