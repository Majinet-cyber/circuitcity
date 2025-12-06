# tests/test_wallet_costs_integration.py
"""
Integration tests for wallet costs feature.
Tests the complete flow from creating costs to viewing them in dashboard.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from wallet.models import WalletTransaction, Ledger, TxnType
from wallet.services_costs import (
    add_business_cost,
    get_business_costs_for_period,
    get_cost_breakdown_by_category
)
from wallet.utils import compute_revenue_costs_profit

User = get_user_model()


@pytest.fixture
def business(db):
    """Create a test business."""
    from tenants.models import Business
    return Business.objects.create(
        name="Test Business",
        subdomain="test",
        status="ACTIVE"
    )


@pytest.fixture
def manager_user(db, business):
    """Create a manager user."""
    user = User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123",
        is_staff=True
    )
    return user


@pytest.mark.django_db
class TestWalletCostsViews(TestCase):
    """Test wallet costs views and templates."""
    
    def setUp(self):
        """Set up test data."""
        from tenants.models import Business
        
        self.business = Business.objects.create(
            name="Test Shop",
            subdomain="shop",
            status="ACTIVE"
        )
        
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123",
            is_staff=True
        )
        
        self.client = Client()
        self.client.login(username="manager", password="testpass123")
    
    def test_admin_costs_list_loads_without_error(self):
        """Test that admin costs list page loads successfully."""
        # Create some test costs
        add_business_cost(
            business=self.business,
            name="Rent",
            amount=Decimal("50000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=timezone.localdate(),
            created_by=self.manager
        )
        
        add_business_cost(
            business=self.business,
            name="Office supplies",
            amount=Decimal("5000.00"),
            cost_category="variable",
            is_recurring=False,
            effective_date=timezone.localdate(),
            created_by=self.manager
        )
        
        # Simulate request with business context
        response = self.client.get(
            reverse('wallet:admin_cost_list'),
            HTTP_HOST=f"{self.business.subdomain}.example.com"
        )
        
        # Should NOT raise TemplateSyntaxError for abs filter
        self.assertEqual(response.status_code, 200)
    
    def test_admin_costs_template_renders_abs_filter(self):
        """Test that abs filter works correctly in template."""
        # Create a cost with negative amount (as stored)
        cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-25000.00"),  # Stored as negative
            note="Test Cost",
            effective_date=timezone.localdate(),
            meta={"cost_category": "variable", "cost_name": "Test Cost"}
        )
        
        response = self.client.get(
            reverse('wallet:admin_cost_list'),
            HTTP_HOST=f"{self.business.subdomain}.example.com"
        )
        
        # Check that the absolute value is displayed (not negative)
        self.assertContains(response, "25,000")  # Formatted with comma
        self.assertNotContains(response, "-25,000")  # Should not show negative


@pytest.mark.django_db
class TestDashboardCostsIntegration(TestCase):
    """Test that costs are integrated into dashboard metrics."""
    
    def setUp(self):
        """Set up test data."""
        from tenants.models import Business
        
        self.business = Business.objects.create(
            name="Phone Shop",
            subdomain="phones",
            status="ACTIVE"
        )
        
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123",
            is_staff=False,  # Regular manager, not staff
        )
        
        # Make user a manager via profile
        if hasattr(self.manager, 'profile'):
            self.manager.profile.is_manager = True
            self.manager.profile.save()
        
        self.client = Client()
        self.client.login(username="manager", password="testpass123")
    
    def test_dashboard_includes_costs_and_profit(self):
        """Test that dashboard context includes costs and net profit."""
        today = timezone.localdate()
        
        # Add a cost
        add_business_cost(
            business=self.business,
            name="Rent",
            amount=Decimal("100000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=today,
            created_by=self.manager
        )
        
        # Simulate revenue (would come from sales in real scenario)
        revenue = Decimal("500000.00")
        
        # Compute profit
        metrics = compute_revenue_costs_profit(
            self.business,
            revenue,
            today.replace(day=1),
            today
        )
        
        self.assertEqual(metrics['revenue'], Decimal("500000.00"))
        self.assertEqual(metrics['costs'], Decimal("100000.00"))
        self.assertEqual(metrics['profit'], Decimal("400000.00"))
        self.assertEqual(metrics['profit_margin'], Decimal("80.00"))  # 400k/500k = 80%


@pytest.mark.django_db
class TestChartAPIs(TestCase):
    """Test that chart APIs handle empty data gracefully."""
    
    def setUp(self):
        """Set up test data."""
        from tenants.models import Business
        
        self.business = Business.objects.create(
            name="Test Business",
            subdomain="test",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="user",
            email="user@test.com",
            password="testpass123"
        )
        
        self.client = Client()
        self.client.login(username="user", password="testpass123")
    
    def test_sales_trend_api_returns_empty_gracefully(self):
        """Test that sales trend API returns 200 with empty data when no sales exist."""
        # No sales data exists
        
        response = self.client.get(
            '/dashboard/api/sales-trend/',
            HTTP_HOST=f"{self.business.subdomain}.example.com"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should return empty arrays, not error
        self.assertIn('labels', data)
        self.assertIn('values', data)
        self.assertIsInstance(data['labels'], list)
        self.assertIsInstance(data['values'], list)
    
    def test_top_models_api_returns_empty_gracefully(self):
        """Test that top models API returns 200 with empty data when no sales exist."""
        response = self.client.get(
            '/dashboard/api/top-models/',
            HTTP_HOST=f"{self.business.subdomain}.example.com"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should return empty arrays, not error
        self.assertIn('labels', data)
        self.assertIn('values', data)
        self.assertIsInstance(data['labels'], list)
        self.assertIsInstance(data['values'], list)
    
    def test_profit_data_api_returns_valid_json(self):
        """Test that profit data API returns valid JSON."""
        response = self.client.get(
            '/dashboard/api/profit-data/',
            HTTP_HOST=f"{self.business.subdomain}.example.com"
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have labels and data
        self.assertIn('labels', data)
        self.assertIn('data', data)


@pytest.mark.django_db
def test_costs_contribute_to_profit_calculation(business, manager_user):
    """Test that costs are correctly subtracted from revenue to compute profit."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    
    # Create costs
    add_business_cost(
        business=business,
        name="Fixed Cost - Rent",
        amount=Decimal("50000.00"),
        cost_category="fixed",
        is_recurring=True,
        effective_date=today,
        created_by=manager_user
    )
    
    add_business_cost(
        business=business,
        name="Variable Cost - Supplies",
        amount=Decimal("15000.00"),
        cost_category="variable",
        is_recurring=False,
        effective_date=today,
        created_by=manager_user
    )
    
    # Simulated revenue
    revenue = Decimal("1000000.00")
    
    # Calculate profit
    result = compute_revenue_costs_profit(business, revenue, month_start, today)
    
    # Revenue - Costs = Profit
    assert result["revenue"] == Decimal("1000000.00")
    assert result["costs"] == Decimal("65000.00")  # 50k + 15k
    assert result["profit"] == Decimal("935000.00")  # 1M - 65k
    assert result["profit_margin"] == Decimal("93.50")  # (935k/1M) * 100


@pytest.mark.django_db
def test_cost_breakdown_by_category(business, manager_user):
    """Test that costs are correctly categorized as fixed vs variable."""
    today = timezone.localdate()
    
    # Create fixed costs
    add_business_cost(
        business=business,
        name="Rent",
        amount=Decimal("100000.00"),
        cost_category="fixed",
        is_recurring=True,
        effective_date=today,
        created_by=manager_user
    )
    
    # Create variable costs
    add_business_cost(
        business=business,
        name="Marketing",
        amount=Decimal("25000.00"),
        cost_category="variable",
        is_recurring=False,
        effective_date=today,
        created_by=manager_user
    )
    
    add_business_cost(
        business=business,
        name="Supplies",
        amount=Decimal("10000.00"),
        cost_category="variable",
        is_recurring=False,
        effective_date=today,
        created_by=manager_user
    )
    
    # Get breakdown
    month_end = today + timedelta(days=30)
    breakdown = get_cost_breakdown_by_category(business, today, month_end)
    
    assert breakdown['fixed_total'] == Decimal("100000.00")
    assert breakdown['variable_total'] == Decimal("35000.00")  # 25k + 10k
    assert len(breakdown['fixed']) == 1
    assert len(breakdown['variable']) == 2

