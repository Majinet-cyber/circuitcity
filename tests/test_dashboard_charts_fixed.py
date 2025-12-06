# tests/test_dashboard_charts_fixed.py
"""
Tests for dashboard chart APIs - ensuring they return valid JSON even with no data.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from tenants.models import Business, Membership

try:
    from inventory.models import InventoryItem, Product
    HAS_INVENTORY = True
except ImportError:
    HAS_INVENTORY = False

User = get_user_model()


class DashboardChartsTestCase(TestCase):
    """Test dashboard chart APIs return valid responses."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create a manager user
        self.manager = User.objects.create_user(
            username="chartmanager",
            password="testpass123",
            email="chartmanager@test.com"
        )
        
        # Create a business
        self.business = Business.objects.create(
            name="Chart Test Shop",
            slug="chart-test-shop",
            status="ACTIVE"
        )
        
        # Create manager membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )

    def test_sales_trend_api_returns_valid_json_without_sales(self):
        """Sales trend API returns valid JSON even when there are no sales."""
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Call sales trend API
        response = self.client.get(reverse('dashboard:sales_trend'))
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Should be valid JSON
        data = response.json()
        
        # Should have expected keys
        self.assertIn('labels', data)
        self.assertIn('values', data)
        
        # Labels and values should be lists
        self.assertIsInstance(data['labels'], list)
        self.assertIsInstance(data['values'], list)
        
        # With no sales, values should be all zeros or empty
        if data['values']:
            self.assertTrue(all(v == 0 for v in data['values']))

    def test_top_models_api_returns_valid_json_without_sales(self):
        """Top models API returns valid JSON even when there are no sales."""
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Call top models API
        response = self.client.get(reverse('dashboard:top_models'))
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Should be valid JSON
        data = response.json()
        
        # Should have expected keys
        self.assertIn('labels', data)
        self.assertIn('values', data)
        
        # Labels and values should be lists
        self.assertIsInstance(data['labels'], list)
        self.assertIsInstance(data['values'], list)
        
        # With no sales, should be empty
        self.assertEqual(len(data['labels']), 0)
        self.assertEqual(len(data['values']), 0)

    def test_sales_trend_includes_manager_sales_for_business(self):
        """Sales trend includes all sales for the business (manager + agents)."""
        if not HAS_INVENTORY:
            self.skipTest("Inventory models not available")
        
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a product
        product = Product.objects.create(
            business=self.business,
            name="Test Phone",
            model="TestPhone X"
        )
        
        # Create sold items (manager sales)
        today = timezone.localdate()
        InventoryItem.objects.create(
            business=self.business,
            product=product,
            imei="111111111111111",
            status="SOLD",
            selling_price=Decimal("1000.00"),
            sold_at=timezone.now(),
            sold_by=self.manager
        )
        
        # Create agent
        agent = User.objects.create_user(
            username="chartagent",
            password="testpass123"
        )
        Membership.objects.create(
            user=agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Create sold item (agent sales)
        InventoryItem.objects.create(
            business=self.business,
            product=product,
            imei="222222222222222",
            status="SOLD",
            selling_price=Decimal("1500.00"),
            sold_at=timezone.now(),
            sold_by=agent
        )
        
        # Call sales trend API
        response = self.client.get(reverse('dashboard:sales_trend') + '?period=30d&metric=amount')
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Should be valid JSON
        data = response.json()
        
        # Should have data
        self.assertIn('labels', data)
        self.assertIn('values', data)
        self.assertTrue(len(data['values']) > 0)
        
        # Total should include both manager and agent sales
        total_sales = sum(data['values'])
        self.assertGreater(total_sales, 0)
        # Should be close to 2500 (1000 + 1500)
        self.assertGreaterEqual(total_sales, 2400)

    def test_sales_trend_with_different_periods(self):
        """Sales trend API works with different period parameters."""
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Test different periods
        periods = ['today', '7d', '30d', 'month', 'week']
        
        for period in periods:
            response = self.client.get(
                reverse('dashboard:sales_trend') + f'?period={period}'
            )
            
            self.assertEqual(response.status_code, 200, f"Failed for period: {period}")
            data = response.json()
            self.assertIn('labels', data)
            self.assertIn('values', data)

    def test_top_models_with_different_periods(self):
        """Top models API works with different period parameters."""
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Test different periods
        periods = ['today', '7d', '30d', 'month', 'week']
        
        for period in periods:
            response = self.client.get(
                reverse('dashboard:top_models') + f'?period={period}'
            )
            
            self.assertEqual(response.status_code, 200, f"Failed for period: {period}")
            data = response.json()
            self.assertIn('labels', data)
            self.assertIn('values', data)

    def test_charts_require_authentication(self):
        """Chart APIs require user to be logged in."""
        # Try without login
        response = self.client.get(reverse('dashboard:sales_trend'))
        
        # Should redirect to login or return 302/403
        self.assertIn(response.status_code, [302, 403, 401])

    def test_charts_with_sales_data(self):
        """Charts show correct data when sales exist."""
        if not HAS_INVENTORY:
            self.skipTest("Inventory models not available")
        
        # Login as manager
        self.client.login(username="chartmanager", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create products
        product1 = Product.objects.create(
            business=self.business,
            name="iPhone 13",
            model="iPhone 13"
        )
        product2 = Product.objects.create(
            business=self.business,
            name="Samsung S21",
            model="Galaxy S21"
        )
        
        # Create sold items
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                product=product1,
                imei=f"11111111111111{i}",
                status="SOLD",
                selling_price=Decimal("1000.00"),
                sold_at=timezone.now(),
                sold_by=self.manager
            )
        
        for i in range(2):
            InventoryItem.objects.create(
                business=self.business,
                product=product2,
                imei=f"22222222222222{i}",
                status="SOLD",
                selling_price=Decimal("800.00"),
                sold_at=timezone.now(),
                sold_by=self.manager
            )
        
        # Test sales trend
        response = self.client.get(reverse('dashboard:sales_trend') + '?period=today&metric=count')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have some non-zero values
        self.assertTrue(any(v > 0 for v in data['values']))
        
        # Test top models
        response = self.client.get(reverse('dashboard:top_models') + '?period=today')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have 2 models
        self.assertEqual(len(data['labels']), 2)
        self.assertEqual(len(data['values']), 2)
        
        # iPhone should be first (3 sales)
        self.assertIn('iPhone', data['labels'][0])
        self.assertEqual(data['values'][0], 3)


class DashboardChartsErrorHandlingTestCase(TestCase):
    """Test error handling in chart APIs."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test",
            slug="test",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )

    def test_charts_handle_missing_business_gracefully(self):
        """Charts return empty data when business is not set."""
        # Login but don't set active business
        self.client.login(username="testuser", password="testpass123")
        
        # Try to access charts
        response = self.client.get(reverse('dashboard:sales_trend'))
        
        # Should still return 200 with empty data (or redirect)
        if response.status_code == 200:
            data = response.json()
            self.assertEqual(data['labels'], [])
            self.assertEqual(data['values'], [])

    def test_charts_handle_invalid_period_parameter(self):
        """Charts handle invalid period parameters gracefully."""
        self.client.login(username="testuser", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try with invalid period
        response = self.client.get(reverse('dashboard:sales_trend') + '?period=invalid')
        
        # Should still return 200 (falls back to default)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('values', data)

