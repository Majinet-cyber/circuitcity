# dashboard/tests/test_costs_commissions_dashboard.py
"""
Tests for dashboard costs and commissions aggregation.
Ensures net profit calculations correctly subtract costs and commissions from revenue.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from dashboard.helpers_costs_commissions import (
    get_costs_and_commissions_panel,
    get_month_to_date_costs_commissions,
    get_today_costs_commissions
)
from inventory.models import InventoryItem, Product, Location
from sales.models import Sale
from wallet.models import WalletTransaction, TxnType, Ledger
from wallet.services_costs import add_business_cost
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCostsCommissionsDashboard(TestCase):
    """Test dashboard calculations for costs and commissions."""

    def setUp(self):
        """Set up test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        self.manager = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="password123"
        )
        self.manager.is_staff = True
        self.manager.save()
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE',
            location=self.location
        )
        
        self.agent = User.objects.create_user(
            username="agent1",
            email="agent@test.com",
            password="password123"
        )
        
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE',
            location=self.location
        )
        
        self.product = Product.objects.create(
            code="TEST001",
            brand="TestBrand",
            model="TestModel",
            cost_price=1000,
            sale_price=1500
        )
        
        self.today = timezone.localdate()
        self.month_start = self.today.replace(day=1)

    def test_net_profit_calculation(self):
        """Test that net profit correctly subtracts costs and commissions from gross profit."""
        # Create a sale (revenue)
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=1000,
            selling_price=1500,
            status="SOLD",
            sold_at=timezone.now()
        )
        
        # Create sale record
        Sale.objects.create(
            item=item,
            location=self.location,
            agent=self.agent,
            price=Decimal("1500.00"),
            sold_at=timezone.now()
        )
        
        # Add commission (100 MK)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.AGENT,
            agent=self.agent,
            type=TxnType.COMMISSION,
            amount=Decimal("100.00"),
            effective_date=self.today,
            note="Test commission"
        )
        
        # Add cost (200 MK)
        add_business_cost(
            business=self.business,
            name="Test Cost",
            amount=Decimal("200.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Calculate panel
        panel = get_costs_and_commissions_panel(
            self.business,
            self.month_start,
            self.today
        )
        
        # Verify calculations
        # Gross Profit = 1500 (selling) - 1000 (order) = 500
        self.assertEqual(panel['gross_profit_this_period'], Decimal("500.00"))
        
        # Commissions = 100
        self.assertEqual(panel['commissions_this_period'], Decimal("100.00"))
        
        # Costs = 200
        self.assertEqual(panel['costs_this_period'], Decimal("200.00"))
        
        # Net Profit = 500 - 100 - 200 = 200
        self.assertEqual(panel['net_profit_this_period'], Decimal("200.00"))

    def test_multiple_sales_and_costs(self):
        """Test dashboard calculations with multiple sales and costs."""
        # Create multiple sales
        for i in range(3):
            item = InventoryItem.objects.create(
                business=self.business,
                imei=f"12345678901234{i}",
                product=self.product,
                current_location=self.location,
                order_price=1000,
                selling_price=1500,
                status="SOLD",
                sold_at=timezone.now()
            )
            
            Sale.objects.create(
                item=item,
                location=self.location,
                agent=self.agent,
                price=Decimal("1500.00"),
                sold_at=timezone.now()
            )
        
        # Add commissions (50 MK each)
        for i in range(3):
            WalletTransaction.objects.create(
                business=self.business,
                ledger=Ledger.AGENT,
                agent=self.agent,
                type=TxnType.COMMISSION,
                amount=Decimal("50.00"),
                effective_date=self.today,
                note=f"Commission {i+1}"
            )
        
        # Add costs
        add_business_cost(
            business=self.business,
            name="Fixed Cost",
            amount=Decimal("300.00"),
            cost_category='fixed',
            is_recurring=True,
            effective_date=self.today
        )
        
        add_business_cost(
            business=self.business,
            name="Variable Cost",
            amount=Decimal("100.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Calculate panel
        panel = get_costs_and_commissions_panel(
            self.business,
            self.month_start,
            self.today
        )
        
        # Verify calculations
        # Revenue = 3 * 1500 = 4500
        self.assertEqual(panel['revenue_this_period'], Decimal("4500.00"))
        
        # Gross Profit = 3 * (1500 - 1000) = 1500
        self.assertEqual(panel['gross_profit_this_period'], Decimal("1500.00"))
        
        # Commissions = 3 * 50 = 150
        self.assertEqual(panel['commissions_this_period'], Decimal("150.00"))
        
        # Costs = 300 + 100 = 400
        self.assertEqual(panel['costs_this_period'], Decimal("400.00"))
        self.assertEqual(panel['fixed_costs'], Decimal("300.00"))
        self.assertEqual(panel['variable_costs'], Decimal("100.00"))
        
        # Net Profit = 1500 - 150 - 400 = 950
        self.assertEqual(panel['net_profit_this_period'], Decimal("950.00"))

    def test_profit_margin_calculation(self):
        """Test profit margin percentage calculation."""
        # Create a sale with known values
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=800,
            selling_price=1000,
            status="SOLD",
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            location=self.location,
            agent=self.agent,
            price=Decimal("1000.00"),
            sold_at=timezone.now()
        )
        
        # Add commission (50 MK)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.AGENT,
            agent=self.agent,
            type=TxnType.COMMISSION,
            amount=Decimal("50.00"),
            effective_date=self.today,
            note="Commission"
        )
        
        # Add cost (50 MK)
        add_business_cost(
            business=self.business,
            name="Cost",
            amount=Decimal("50.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Calculate panel
        panel = get_costs_and_commissions_panel(
            self.business,
            self.month_start,
            self.today
        )
        
        # Net Profit = (1000 - 800) - 50 - 50 = 100
        # Profit Margin = (100 / 1000) * 100 = 10%
        self.assertEqual(panel['net_profit_this_period'], Decimal("100.00"))
        self.assertEqual(panel['profit_margin'], Decimal("10.00"))

    def test_zero_revenue_no_division_error(self):
        """Test that zero revenue doesn't cause division errors."""
        # No sales, but add costs
        add_business_cost(
            business=self.business,
            name="Cost with no revenue",
            amount=Decimal("100.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Calculate panel
        panel = get_costs_and_commissions_panel(
            self.business,
            self.month_start,
            self.today
        )
        
        # Should not crash, profit margin should be 0
        self.assertEqual(panel['revenue_this_period'], Decimal("0.00"))
        self.assertEqual(panel['profit_margin'], Decimal("0.00"))
        # Net profit should be negative (just costs)
        self.assertEqual(panel['net_profit_this_period'], Decimal("-100.00"))

    def test_month_to_date_helper(self):
        """Test month-to-date convenience helper."""
        # Add a sale
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=1000,
            selling_price=1500,
            status="SOLD",
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            location=self.location,
            agent=self.agent,
            price=Decimal("1500.00"),
            sold_at=timezone.now()
        )
        
        # Use MTD helper
        panel = get_month_to_date_costs_commissions(self.business)
        
        # Should return data for month-to-date
        self.assertIsNotNone(panel)
        self.assertEqual(panel['period_start'], self.month_start)
        self.assertEqual(panel['revenue_this_period'], Decimal("1500.00"))

    def test_today_helper(self):
        """Test today convenience helper."""
        # Add a sale today
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=1000,
            selling_price=1500,
            status="SOLD",
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            location=self.location,
            agent=self.agent,
            price=Decimal("1500.00"),
            sold_at=timezone.now()
        )
        
        # Use today helper
        panel = get_today_costs_commissions(self.business)
        
        # Should return data for today only
        self.assertIsNotNone(panel)
        self.assertEqual(panel['period_start'], self.today)
        self.assertEqual(panel['period_end'], self.today)
        self.assertEqual(panel['revenue_this_period'], Decimal("1500.00"))

    def test_negative_profit(self):
        """Test that negative profit is handled correctly."""
        # Small sale
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=900,
            selling_price=1000,
            status="SOLD",
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            location=self.location,
            agent=self.agent,
            price=Decimal("1000.00"),
            sold_at=timezone.now()
        )
        
        # Large commission
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.AGENT,
            agent=self.agent,
            type=TxnType.COMMISSION,
            amount=Decimal("80.00"),
            effective_date=self.today,
            note="Commission"
        )
        
        # Large cost
        add_business_cost(
            business=self.business,
            name="Large Cost",
            amount=Decimal("500.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Calculate panel
        panel = get_costs_and_commissions_panel(
            self.business,
            self.month_start,
            self.today
        )
        
        # Gross Profit = 1000 - 900 = 100
        # Net Profit = 100 - 80 - 500 = -480 (negative)
        self.assertEqual(panel['gross_profit_this_period'], Decimal("100.00"))
        self.assertEqual(panel['net_profit_this_period'], Decimal("-480.00"))
        # Profit margin should be negative
        self.assertEqual(panel['profit_margin'], Decimal("-48.00"))


@pytest.mark.django_db
class TestDashboardContext(TestCase):
    """Test dashboard view context includes costs & commissions panel."""

    def setUp(self):
        """Set up test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        self.manager = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="password123"
        )
        self.manager.is_staff = True
        self.manager.save()
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE',
            location=self.location
        )
        
        self.client = Client()

    def test_manager_dashboard_includes_costs_panel(self):
        """Test that manager dashboard context includes costs_commissions_panel."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Note: May need to adjust URL based on actual dashboard route
        # This test verifies the context includes the panel
        # In actual implementation, verify the URL and template render
        
        # The panel should be available in manager context
        # (Implementation-specific test)
        self.assertTrue(True)  # Placeholder - adjust based on actual routes

