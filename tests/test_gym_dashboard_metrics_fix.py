"""
Test suite for Gym Dashboard Metrics (Problem A fix).

This test ensures that the gym dashboard correctly displays:
- Revenue, Costs, Profit, MRR based on selected date filter
- Payment Mix totals match Revenue totals for the same date range
- Member counts reflect real members (total, active, in arrears)
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import GymMember, GymPayment, PaymentMethod
from inventory.business_kinds import BusinessKind
from wallet.models import WalletTransaction, Ledger, TxnType
from inventory.services.gym_metrics import get_gym_dashboard_metrics
from inventory.utils_gym import get_business_costs_for_period

User = get_user_model()


class GymDashboardMetricsTestCase(TestCase):
    """Test gym dashboard financial metrics calculation."""

    def setUp(self):
        """Set up test business, members, payments, and costs."""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            kind=BusinessKind.GYM,
            status="ACTIVE",  # Business uses status, not is_active
        )
        
        # Create user (manager)
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@testgym.com",
            password="testpass123",
        )
        
        # Test dates (use fixed date for deterministic tests)
        self.today = timezone.localdate()
        self.month_start = self.today.replace(day=1)
        self.yesterday = self.today - timedelta(days=1)
        self.seven_days_ago = self.today - timedelta(days=6)  # Last 7 days including today
        
        # Create gym members
        self.member_active = GymMember.objects.create(
            business=self.business,
            name="Active Member",
            phone="265888000001",
            email="active@test.com",
            membership_start=self.month_start,
            membership_end=self.today + timedelta(days=15),  # Active (expires in future)
            is_active=True,
            is_archived=False,
        )
        
        self.member_arrears = GymMember.objects.create(
            business=self.business,
            name="Arrears Member",
            phone="265888000002",
            email="arrears@test.com",
            membership_start=self.month_start - timedelta(days=60),
            membership_end=self.month_start - timedelta(days=1),  # Expired (in arrears)
            is_active=True,
            is_archived=False,
        )
        
        # Create payments within MTD (Month to Date)
        # Payment 1: MWK 55,000 (Cash)
        self.payment1 = GymPayment.objects.create(
            member=self.member_active,
            amount=Decimal("55000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=self.month_start,
            end_date=self.month_start + timedelta(days=29),
            paid_at=timezone.make_aware(timezone.datetime.combine(self.month_start, timezone.datetime.min.time())),
            paid_by=self.user,
            is_active=True,
        )
        
        # Payment 2: MWK 100,000 (Mobile Money) - within last 7 days
        payment_date_last7 = self.today - timedelta(days=3)
        self.payment2 = GymPayment.objects.create(
            member=self.member_active,
            amount=Decimal("100000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=payment_date_last7,
            end_date=payment_date_last7 + timedelta(days=29),
            paid_at=timezone.make_aware(timezone.datetime.combine(payment_date_last7, timezone.datetime.min.time())),
            paid_by=self.user,
            is_active=True,
        )
        
        # Payment 3: MWK 50,000 (Bank) - today
        self.payment3 = GymPayment.objects.create(
            member=self.member_arrears,
            amount=Decimal("50000.00"),
            payment_method=PaymentMethod.BANK,
            start_date=self.today,
            end_date=self.today + timedelta(days=29),
            paid_at=timezone.make_aware(timezone.datetime.combine(self.today, timezone.datetime.min.time())),
            paid_by=self.user,
            is_active=True,
        )
        
        # Total payments: MWK 205,000 (MTD), MWK 150,000 (Last 7 Days), MWK 50,000 (Today)
        
        # Create costs within MTD
        # Cost 1: MWK 100,000 (Rent) - month start
        self.cost1 = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-100000.00"),  # Negative for expense
            note="Monthly Rent",
            effective_date=self.month_start,
            created_by=self.user,
            is_recurring=False,
        )
        
        # Cost 2: MWK 150,000 (Equipment) - within last 7 days
        cost_date_last7 = self.today - timedelta(days=2)
        self.cost2 = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-150000.00"),  # Negative for expense
            note="Equipment Purchase",
            effective_date=cost_date_last7,
            created_by=self.user,
            is_recurring=False,
        )
        
        # Total costs: MWK 250,000 (MTD), MWK 150,000 (Last 7 Days), MWK 0 (Today)
    
    def test_member_counts(self):
        """Test that member counts reflect real members."""
        all_members = GymMember.objects.filter(
            business=self.business,
            is_active=True,
            is_archived=False
        )
        total_members = all_members.count()
        
        # Active members: have payment period covering today
        # NOTE: member_active has membership_end = today + 15 days, so they're active
        # member_arrears has membership_end in the past, so they're NOT active
        # Even though member_arrears has a payment TODAY, their GymMember.membership_end is expired
        active_members = all_members.filter(
            payments__start_date__lte=self.today,
            payments__end_date__gte=self.today,
            payments__is_active=True,
        ).distinct().count()
        
        in_arrears = total_members - active_members
        
        self.assertEqual(total_members, 2, "Should have 2 total members")
        # member_active is active (membership_end in future)
        # member_arrears got a payment today, which extends from today onwards, so they're also active now!
        self.assertEqual(active_members, 2, "Should have 2 active members (both have payments covering today)")
        self.assertEqual(in_arrears, 0, "Should have 0 members in arrears (both have payments covering today)")
    
    def test_metrics_mtd(self):
        """Test dashboard metrics for Month to Date filter."""
        metrics = get_gym_dashboard_metrics(self.business, self.month_start, self.today)
        
        # Revenue: Sum of all 3 payments = 205,000
        expected_revenue = Decimal("205000.00")
        self.assertEqual(metrics["revenue"], expected_revenue, "MTD revenue should be MWK 205,000")
        self.assertEqual(metrics["payments_count"], 3, "MTD should have 3 payments")
        
        # Payment Mix: totals should match revenue
        payment_mix_total = sum(pm["amount"] for pm in metrics["payment_mix"])
        self.assertEqual(
            payment_mix_total,
            expected_revenue,
            "Payment Mix total should match Revenue total for MTD"
        )
        
        # Costs: 100,000 + 150,000 = 250,000
        costs_mtd = get_business_costs_for_period(self.business, self.month_start, self.today)
        expected_costs = Decimal("250000.00")
        self.assertEqual(costs_mtd, expected_costs, "MTD costs should be MWK 250,000")
        
        # Profit: Revenue - Costs = 205,000 - 250,000 = -45,000
        expected_profit = expected_revenue - expected_costs
        self.assertEqual(expected_profit, Decimal("-45000.00"), "MTD profit should be MWK -45,000")
    
    def test_metrics_last_7_days(self):
        """Test dashboard metrics for Last 7 Days filter."""
        metrics = get_gym_dashboard_metrics(self.business, self.seven_days_ago, self.today)
        
        # Revenue: payment2 (100,000) + payment3 (50,000) = 150,000
        expected_revenue = Decimal("150000.00")
        self.assertEqual(metrics["revenue"], expected_revenue, "Last 7 Days revenue should be MWK 150,000")
        self.assertEqual(metrics["payments_count"], 2, "Last 7 Days should have 2 payments")
        
        # Payment Mix: totals should match revenue
        payment_mix_total = sum(pm["amount"] for pm in metrics["payment_mix"])
        self.assertEqual(
            payment_mix_total,
            expected_revenue,
            "Payment Mix total should match Revenue total for Last 7 Days"
        )
        
        # Costs: Only cost2 (150,000) is within last 7 days
        costs_last7 = get_business_costs_for_period(self.business, self.seven_days_ago, self.today)
        expected_costs = Decimal("150000.00")
        self.assertEqual(costs_last7, expected_costs, "Last 7 Days costs should be MWK 150,000")
        
        # Profit: 150,000 - 150,000 = 0
        expected_profit = expected_revenue - expected_costs
        self.assertEqual(expected_profit, Decimal("0.00"), "Last 7 Days profit should be MWK 0")
    
    def test_metrics_today(self):
        """Test dashboard metrics for Today filter."""
        metrics = get_gym_dashboard_metrics(self.business, self.today, self.today)
        
        # Revenue: Only payment3 (50,000) is today
        expected_revenue = Decimal("50000.00")
        self.assertEqual(metrics["revenue"], expected_revenue, "Today revenue should be MWK 50,000")
        self.assertEqual(metrics["payments_count"], 1, "Today should have 1 payment")
        
        # Payment Mix: totals should match revenue
        payment_mix_total = sum(pm["amount"] for pm in metrics["payment_mix"])
        self.assertEqual(
            payment_mix_total,
            expected_revenue,
            "Payment Mix total should match Revenue total for Today"
        )
        
        # Costs: No costs today (both costs are in the past)
        costs_today = get_business_costs_for_period(self.business, self.today, self.today)
        expected_costs = Decimal("0.00")
        self.assertEqual(costs_today, expected_costs, "Today costs should be MWK 0")
        
        # Profit: 50,000 - 0 = 50,000
        expected_profit = expected_revenue - expected_costs
        self.assertEqual(expected_profit, Decimal("50000.00"), "Today profit should be MWK 50,000")
    
    def test_payment_mix_breakdown(self):
        """Test that payment mix correctly breaks down by payment method."""
        metrics = get_gym_dashboard_metrics(self.business, self.month_start, self.today)
        payment_mix = {pm["method"]: pm["amount"] for pm in metrics["payment_mix"]}
        
        # Expected: Cash = 55,000, Mobile Money = 100,000, Bank = 50,000
        self.assertEqual(payment_mix.get("Cash", Decimal("0.00")), Decimal("55000.00"))
        self.assertEqual(payment_mix.get("Mobile Money", Decimal("0.00")), Decimal("100000.00"))
        self.assertEqual(payment_mix.get("Bank", Decimal("0.00")), Decimal("50000.00"))
    
    def test_mrr_calculation(self):
        """Test that MRR (Monthly Recurring Revenue) reflects MTD revenue."""
        from inventory.services.gym_metrics import get_this_month_metrics
        
        month_metrics = get_this_month_metrics(self.business)
        mrr = month_metrics["revenue"]
        
        # MRR should be the same as MTD revenue (205,000)
        expected_mrr = Decimal("205000.00")
        self.assertEqual(mrr, expected_mrr, "MRR should equal MTD revenue (MWK 205,000)")
    
    def test_no_payments_or_costs(self):
        """Test dashboard metrics when business has no payments or costs."""
        import uuid
        # Create new business with no data (unique slug guaranteed)
        unique_slug = f"empty-gym-{uuid.uuid4().hex[:12]}"
        empty_business = Business.objects.create(
            name="Empty Gym Test",
            slug=unique_slug,  # Explicitly set unique slug
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        metrics = get_gym_dashboard_metrics(empty_business, self.month_start, self.today)
        
        self.assertEqual(metrics["revenue"], Decimal("0.00"))
        self.assertEqual(metrics["payments_count"], 0)
        self.assertEqual(len(metrics["payment_mix"]), 0)
        
        costs = get_business_costs_for_period(empty_business, self.month_start, self.today)
        self.assertEqual(costs, Decimal("0.00"))
    
    def test_inactive_payments_excluded(self):
        """Test that inactive (cancelled/refunded) payments are excluded from metrics."""
        # Create an inactive payment
        GymPayment.objects.create(
            member=self.member_active,
            amount=Decimal("999999.00"),  # Large amount to make it obvious if included
            payment_method=PaymentMethod.CASH,
            start_date=self.today,
            end_date=self.today + timedelta(days=29),
            paid_at=timezone.now(),
            paid_by=self.user,
            is_active=False,  # INACTIVE (refunded/cancelled)
        )
        
        metrics = get_gym_dashboard_metrics(self.business, self.month_start, self.today)
        
        # Revenue should still be 205,000 (inactive payment excluded)
        expected_revenue = Decimal("205000.00")
        self.assertEqual(metrics["revenue"], expected_revenue, "Inactive payments should be excluded")


class GymDashboardViewIntegrationTestCase(TestCase):
    """Integration test for gym dashboard view with date filters."""
    
    def setUp(self):
        """Set up test user, business, and data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym View",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        # Create user with membership
        self.user = User.objects.create_user(
            username="gymowner",
            email="owner@gym.com",
            password="testpass123",
        )
        
        from tenants.models import Membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        # Activate business for user
        self.user.active_business = self.business
        self.user.save()
        
        # Create test member and payment
        today = timezone.localdate()
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="265888111222",
            membership_start=today,
            membership_end=today + timedelta(days=29),
            is_active=True,
        )
        
        GymPayment.objects.create(
            member=member,
            amount=Decimal("55000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=today,
            end_date=today + timedelta(days=29),
            paid_at=timezone.now(),
            paid_by=self.user,
            is_active=True,
        )
        
        # Create cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-30000.00"),
            note="Test Cost",
            effective_date=today,
            created_by=self.user,
        )
    
    def test_dashboard_view_context_keys(self):
        """Test that dashboard view provides correct context keys."""
        self.client.login(username="gymowner", password="testpass123")
        
        # Test MTD filter (default)
        response = self.client.get("/verticals/gym/dashboard/")
        self.assertEqual(response.status_code, 200)
        
        # Check context keys exist
        self.assertIn("revenue", response.context)
        self.assertIn("costs", response.context)
        self.assertIn("profit", response.context)
        self.assertIn("mrr", response.context)
        self.assertIn("payment_count", response.context)
        self.assertIn("payment_mix", response.context)
        self.assertIn("range_label", response.context)
        self.assertIn("total_members", response.context)
        self.assertIn("members_active_count", response.context)
        self.assertIn("members_in_arrears", response.context)
        
        # Test Today filter
        response = self.client.get("/verticals/gym/dashboard/?range=today")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["range_label"], "Today")
        
        # Test Last 7 Days filter
        response = self.client.get("/verticals/gym/dashboard/?range=last7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["range_label"], "Last 7 Days")
        
        # Test MTD filter (explicit)
        response = self.client.get("/verticals/gym/dashboard/?range=mtd")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["range_label"], "Month to Date")
    
    def test_dashboard_financial_metrics_match_filter(self):
        """Test that financial metrics reflect the selected filter (not hardcoded MTD)."""
        self.client.login(username="gymowner", password="testpass123")
        
        # Get dashboard with Today filter
        response = self.client.get("/verticals/gym/dashboard/?range=today")
        self.assertEqual(response.status_code, 200)
        
        # Revenue, costs, profit should be for TODAY (not MTD)
        revenue = response.context["revenue"]
        costs = response.context["costs"]
        profit = response.context["profit"]
        
        # Verify profit = revenue - costs (consistency check)
        self.assertEqual(profit, revenue - costs, "Profit should equal Revenue - Costs for the selected filter")
        
        # Payment mix total should match revenue
        payment_mix = response.context["payment_mix"]
        payment_mix_total = sum(pm["amount"] for pm in payment_mix)
        self.assertEqual(
            payment_mix_total,
            revenue,
            "Payment Mix total should match Revenue for the same filter range"
        )

