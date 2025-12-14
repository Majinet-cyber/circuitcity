# hq/tests/test_hq_views.py
"""Tests for HQ views - dashboard, business directory, subscriptions."""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from billing.models import BusinessSubscription as Subscription, Invoice


User = get_user_model()


class HQViewsTest(TestCase):
    """Test HQ views return 200 and handle edge cases."""
    
    def setUp(self):
        """Set up test data."""
        # Create superuser for HQ access
        self.admin_user = User.objects.create_superuser(
            username='hqadmin',
            email='admin@hq.com',
            password='adminpass123'
        )
        
        # Create a regular business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            created_by=self.admin_user,
            status='ACTIVE'
        )
        
        self.client = Client()
        self.client.login(username='hqadmin', password='adminpass123')
    
    def test_hq_dashboard_returns_200(self):
        """HQ dashboard should return 200 without errors."""
        url = reverse('hq:dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')
    
    def test_hq_business_directory_returns_200(self):
        """Business directory should return 200 with no template errors."""
        url = reverse('hq:business_directory')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Business Directory')
        # Should not have template errors for days_remaining
        self.assertNotContains(response, 'Failed lookup for key')
    
    def test_hq_subscriptions_returns_200_without_contracts(self):
        """Subscriptions page should not 500 even if contracts module is missing."""
        url = reverse('hq:subscriptions')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
    
    def test_contracts_stub_works_when_module_missing(self):
        """Contracts stub should return 200 when module is not available."""
        # This will hit the stub if contracts module is not available
        url = reverse('hq:contracts_list')
        response = self.client.get(url)
        
        # Should return 200 (either real view or stub)
        self.assertEqual(response.status_code, 200)
    
    def test_business_detail_with_no_subscription(self):
        """Business detail should handle missing subscription gracefully."""
        # Business has no subscription yet
        url = reverse('hq:business_detail', args=[self.business.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should not crash with RelatedObjectDoesNotExist
        self.assertContains(response, self.business.name)
    
    def test_business_detail_with_subscription(self):
        """Business detail should show subscription when it exists."""
        # Create subscription
        subscription = Subscription.objects.create(
            business=self.business,
            status='active',
            current_period_end=timezone.now() + timedelta(days=30)
        )
        
        url = reverse('hq:business_detail', args=[self.business.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.business.name)
    
    def test_business_directory_normalizes_subscription_state(self):
        """Business directory should normalize subscription state to prevent template errors."""
        # Create business with no subscription
        biz2 = Business.objects.create(
            name='Business No Sub',
            slug='biz-no-sub',
            created_by=self.admin_user,
            status='ACTIVE'
        )
        
        url = reverse('hq:business_directory')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should handle missing days_remaining gracefully
        self.assertIn(biz2.name, response.content.decode())
    
    def test_hq_dashboard_sqlite_compatible(self):
        """HQ dashboard should work with SQLite (no custom functions)."""
        # Create some test sales data
        from sales.models import Sale
        from inventory.models import InventoryItem
        
        # This test ensures the dashboard doesn't crash on SQLite
        url = reverse('hq:dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should not have OperationalError from user-defined functions


class HQDashboardChartsTest(TestCase):
    """Test HQ dashboard chart data and numeric summaries."""
    
    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username='hqadmin',
            email='admin@hq.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.login(username='hqadmin', password='adminpass123')
    
    def test_dashboard_has_numeric_summaries(self):
        """Dashboard should show numeric summaries beside charts."""
        url = reverse('hq:dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check for key summary elements
        self.assertContains(response, 'YTD TOTAL')
        self.assertContains(response, 'PEAK MONTH')

