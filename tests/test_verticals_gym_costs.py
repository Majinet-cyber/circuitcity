"""
Tests for verticals gym dashboard cost integration with admin wallet.

This ensures that /verticals/gym/dashboard/ correctly displays costs
added in /wallet/admin/costs/, fixing the bug where costs were showing MK 0.00.
"""
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.models_verticals import (
    GymMember, GymPayment, GymSettings,
    GymMemberStatus, PaymentMethod
)
from wallet.models import WalletTransaction, Ledger, TxnType

User = get_user_model()


class TestVerticalsGymDashboardCosts(TestCase):
    """Test that /verticals/gym/dashboard/ shows admin wallet costs correctly"""
    
    def setUp(self):
        """Set up test data"""
        # Create gym business
        self.business = Business.objects.create(
            name="Test Gym",
            slug="test-gym-vertical",
            business_kind="gym",
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Gym"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@gym.com",
            email="manager@gym.com",
            password="testpass123"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create gym settings
        self.settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("55000.00"),
            default_trainer_fee=Decimal("15000.00")
        )
        
        # Set up client and login
        self.client = Client()
        self.client.force_login(self.manager)
    
    def test_verticals_gym_dashboard_shows_admin_wallet_costs(self):
        """
        Test that /verticals/gym/dashboard/ correctly shows costs from admin wallet.
        
        This is the PRIMARY test for the bug fix:
        - Add costs in /wallet/admin/costs/
        - Verify they appear on /verticals/gym/dashboard/
        """
        today = timezone.now().date()
        
        # Create admin wallet cost (as if added via /wallet/admin/costs/)
        # Rent: 150,000 MWK
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-150000.00"),  # Negative for expense
            note="Rent",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager,
            meta={"cost_category": "fixed", "cost_name": "Rent"}
        )
        
        # Add another cost
        # Utilities: 25,000 MWK
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-25000.00"),
            note="Utilities",
            effective_date=today,
            effective_from=today,
            is_recurring=True,
            created_by=self.manager,
            meta={"cost_category": "fixed", "cost_name": "Utilities"}
        )
        
        # Get /verticals/gym/dashboard/
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # ✅ CRITICAL: Costs must be visible on dashboard
        self.assertIn("costs_this_month", response.context)
        
        # Total costs should be 150k + 25k = 175k
        expected_costs = Decimal("175000.00")
        actual_costs = response.context["costs_this_month"]
        
        self.assertEqual(
            actual_costs,
            expected_costs,
            f"Expected costs to be {expected_costs}, but got {actual_costs}. "
            f"Dashboard should reflect admin wallet costs immediately."
        )
        
        # Also check legacy context variable
        self.assertEqual(response.context["costs"], expected_costs)
    
    def test_verticals_gym_dashboard_profit_calculation(self):
        """
        Test that profit = revenue - costs on /verticals/gym/dashboard/.
        """
        today = timezone.now().date()
        now = timezone.now()
        
        # Add a cost (50,000 MWK)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Marketing",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Add revenue through gym payment
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="123456789",
            membership_fee=Decimal("55000.00"),
            status=GymMemberStatus.ACTIVE
        )
        
        payment = GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("100000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("100000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=today,
            end_date=today + timedelta(days=30),
            paid_at=now,
            paid_by=self.manager,
            is_active=True
        )
        
        # Get dashboard
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify costs, revenue, and profit
        costs = response.context["costs_this_month"]
        revenue = response.context["revenue_this_month"]
        profit = response.context["profit_this_month"]
        
        self.assertEqual(costs, Decimal("50000.00"))
        self.assertGreaterEqual(revenue, Decimal("100000.00"))
        
        # ✅ CRITICAL: Profit must equal revenue - costs
        expected_profit = revenue - costs
        self.assertEqual(
            profit,
            expected_profit,
            f"Profit should be revenue ({revenue}) - costs ({costs}) = {expected_profit}, "
            f"but got {profit}"
        )
    
    def test_verticals_gym_dashboard_costs_scoped_to_business(self):
        """
        Test that costs from other businesses don't leak into gym dashboard.
        
        Business isolation is critical for multi-tenant systems.
        """
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            slug="other-gym",
            business_kind="gym",
            status="ACTIVE"
        )
        
        today = timezone.now().date()
        
        # Create cost for THIS gym (50k)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="This Gym Cost",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Create cost for OTHER business (999k - should NOT appear)
        WalletTransaction.objects.create(
            business=other_business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-999999.00"),
            note="Other Business Cost",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Get dashboard
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # ✅ CRITICAL: Should only show cost from THIS business (50k), not other (999k)
        actual_costs = response.context["costs_this_month"]
        self.assertEqual(
            actual_costs,
            Decimal("50000.00"),
            f"Dashboard should only show costs for active business (50k), "
            f"but got {actual_costs}. Costs from other businesses leaked!"
        )
    
    def test_verticals_gym_dashboard_costs_by_period(self):
        """
        Test that costs are correctly filtered by time period (today, yesterday, this month).
        """
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        last_month = today - timedelta(days=35)
        
        # Cost today (10k)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-10000.00"),
            note="Today Cost",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Cost yesterday (20k)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-20000.00"),
            note="Yesterday Cost",
            effective_date=yesterday,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Cost last month (should NOT appear in "this month")
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-99999.00"),
            note="Last Month Cost",
            effective_date=last_month,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Get dashboard
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify period-specific costs
        costs_today = response.context.get("costs_today", Decimal("0.00"))
        costs_yesterday = response.context.get("costs_yesterday", Decimal("0.00"))
        costs_this_month = response.context.get("costs_this_month", Decimal("0.00"))
        
        # Today's costs should be 10k
        self.assertEqual(costs_today, Decimal("10000.00"))
        
        # Yesterday's costs should be 20k
        self.assertEqual(costs_yesterday, Decimal("20000.00"))
        
        # This month's costs should include today + yesterday (30k)
        # but NOT last month (99999)
        self.assertGreaterEqual(costs_this_month, Decimal("30000.00"))
        self.assertLess(costs_this_month, Decimal("99999.00"))
    
    def test_both_gym_dashboards_show_same_costs(self):
        """
        Test that BOTH gym dashboards show identical costs:
        - /gym/dashboard/ (inventory gym dashboard)
        - /verticals/gym/dashboard/ (verticals gym dashboard)
        
        This is the REGRESSION test to ensure consistency.
        """
        today = timezone.now().date()
        
        # Add admin wallet cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-75000.00"),
            note="Test Cost",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Get BOTH dashboards
        inventory_url = reverse("gym:dashboard")
        verticals_url = reverse("verticals:gym_dashboard")
        
        inventory_response = self.client.get(inventory_url)
        verticals_response = self.client.get(verticals_url)
        
        self.assertEqual(inventory_response.status_code, 200)
        self.assertEqual(verticals_response.status_code, 200)
        
        # ✅ CRITICAL: Both dashboards must show the same costs
        inventory_costs = inventory_response.context["costs_this_month"]
        verticals_costs = verticals_response.context["costs_this_month"]
        
        self.assertEqual(
            inventory_costs,
            verticals_costs,
            f"Both gym dashboards must show identical costs! "
            f"Inventory dashboard: {inventory_costs}, "
            f"Verticals dashboard: {verticals_costs}"
        )
        
        # Verify the expected amount
        self.assertEqual(inventory_costs, Decimal("75000.00"))
        self.assertEqual(verticals_costs, Decimal("75000.00"))


class TestAdminWalletCostsSource(TestCase):
    """
    Test that costs are correctly created in the admin wallet system.
    
    This verifies the SOURCE of truth for costs (WalletTransaction with COMPANY ledger).
    """
    
    def setUp(self):
        """Set up test data"""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business-costs",
            business_kind="gym",
            status="ACTIVE"
        )
        
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
    
    def test_admin_wallet_cost_creation(self):
        """
        Test that costs are created correctly in WalletTransaction.
        
        This is how /wallet/admin/costs/ creates costs.
        """
        today = timezone.now().date()
        
        # Create a cost as the admin wallet system does
        txn = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-100000.00"),  # Negative for expense
            note="Rent",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager,
            meta={"cost_category": "fixed", "cost_name": "Rent"}
        )
        
        # Verify the cost was created correctly
        self.assertEqual(txn.business, self.business)
        self.assertEqual(txn.ledger, Ledger.COMPANY)
        self.assertEqual(txn.type, TxnType.COST_ONCE_OFF)
        self.assertEqual(txn.amount, Decimal("-100000.00"))
        
        # Verify it can be queried
        costs = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        self.assertEqual(costs.count(), 1)
        self.assertEqual(abs(costs.first().amount), Decimal("100000.00"))
    
    def test_recurring_vs_once_off_costs(self):
        """
        Test that both recurring and once-off costs are correctly identified.
        """
        today = timezone.now().date()
        
        # Once-off cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Equipment Purchase",
            effective_date=today,
            is_recurring=False,
            created_by=self.manager
        )
        
        # Recurring cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-30000.00"),
            note="Monthly Subscription",
            effective_date=today,
            effective_from=today,
            is_recurring=True,
            created_by=self.manager
        )
        
        # Query both types
        costs = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        
        self.assertEqual(costs.count(), 2)
        
        # Verify types
        once_off = costs.filter(type=TxnType.COST_ONCE_OFF)
        recurring = costs.filter(type=TxnType.COST_RECURRING)
        
        self.assertEqual(once_off.count(), 1)
        self.assertEqual(recurring.count(), 1)
        self.assertFalse(once_off.first().is_recurring)
        self.assertTrue(recurring.first().is_recurring)

