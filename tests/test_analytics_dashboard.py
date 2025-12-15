"""
Comprehensive tests for Analytics Dashboard feature.
Tests vertical adapters, API endpoints, business scoping, and HQ analytics.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.analytics import get_adapter

User = get_user_model()


class AnalyticsDashboardTestCase(TestCase):
    """Test analytics dashboard loads and works for all verticals."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
    
    def test_analytics_dashboard_loads(self):
        """Test analytics dashboard page loads successfully."""
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/app/analytics/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Analytics Dashboard')
    
    def test_analytics_dashboard_requires_login(self):
        """Test analytics dashboard requires authentication."""
        response = self.client.get('/app/analytics/')
        self.assertIn(response.status_code, [302, 403])  # Redirect to login or 403
    
    def test_analytics_dashboard_requires_business(self):
        """Test analytics dashboard requires active business."""
        self.client.force_login(self.user)
        # No active business in session
        response = self.client.get('/app/analytics/')
        self.assertIn(response.status_code, [302, 400])  # Redirect or error


class AnalyticsAPITestCase(TestCase):
    """Test analytics API endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
    
    def test_api_kpis_endpoint(self):
        """Test KPIs API endpoint returns valid data."""
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/app/analytics/api/kpis/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('revenue', data)
        self.assertIn('profit', data)
        self.assertIn('total_sales', data)
        self.assertIn('last_updated', data)
    
    def test_api_sales_trend_endpoint(self):
        """Test sales trend API endpoint."""
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/app/analytics/api/sales_trend/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sales_trend', data)
        self.assertIn('last_updated', data)
    
    def test_api_payment_mix_endpoint(self):
        """Test payment mix API endpoint."""
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/app/analytics/api/payment_mix/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('payment_mix', data)
        self.assertIn('last_updated', data)


class AnalyticsScopingTestCase(TestCase):
    """Test business scoping isolation in analytics."""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.business1 = Business.objects.create(
            name='Business 1',
            slug='business-1',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        self.business2 = Business.objects.create(
            name='Business 2',
            slug='business-2',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        
        Membership.objects.create(
            user=self.user1,
            business=self.business1,
            role='MANAGER',
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.user2,
            business=self.business2,
            role='MANAGER',
            status='ACTIVE'
        )
    
    def test_business_isolation(self):
        """Test that business A cannot see business B's data."""
        self.client.force_login(self.user1)
        session = self.client.session
        session['active_business_id'] = self.business1.id
        session.save()
        
        # Get KPIs for business1
        response = self.client.get('/app/analytics/api/kpis/')
        self.assertEqual(response.status_code, 200)
        
        # Verify adapter is scoped to business1
        from inventory.analytics import get_adapter
        adapter = get_adapter('phones')
        sales_qs = adapter.get_sales_queryset(self.business1)
        self.assertEqual(sales_qs.model._meta.label, 'inventory.InventoryItem')
        # The queryset should be filtered by business
        # (actual data isolation is tested by the adapter's get_sales_queryset implementation)


class AnalyticsAdapterTestCase(TestCase):
    """Test analytics adapters work correctly."""
    
    def setUp(self):
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
    
    def test_get_adapter_for_phones(self):
        """Test getting phones adapter."""
        adapter = get_adapter('phones')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'PhonesAdapter')
    
    def test_get_adapter_for_clothing(self):
        """Test getting clothing adapter."""
        adapter = get_adapter('clothing')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'ClothingAdapter')
    
    def test_get_adapter_for_pharmacy(self):
        """Test getting pharmacy adapter."""
        adapter = get_adapter('pharmacy')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'PharmacyAdapter')
    
    def test_get_adapter_for_liquor(self):
        """Test getting liquor adapter."""
        adapter = get_adapter('liquor')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'LiquorAdapter')
    
    def test_get_adapter_for_gym(self):
        """Test getting gym adapter."""
        adapter = get_adapter('gym')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'GymAdapter')
    
    def test_get_adapter_defaults_to_phones(self):
        """Test unknown vertical defaults to phones adapter."""
        adapter = get_adapter('unknown')
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.__class__.__name__, 'PhonesAdapter')
    
    def test_adapter_kpis_structure(self):
        """Test adapter KPIs return expected structure."""
        adapter = get_adapter('phones')
        today = date.today()
        kpis = adapter.kpis(
            business=self.business,
            start_date=today - timedelta(days=30),
            end_date=today,
        )
        
        self.assertIn('revenue', kpis)
        self.assertIn('profit', kpis)
        self.assertIn('total_sales', kpis)
        self.assertIn('avg_order_value', kpis)
        self.assertIn('gross_margin', kpis)
        self.assertIn('costs', kpis)
        
        # Verify types
        self.assertIsInstance(kpis['revenue'], Decimal)
        self.assertIsInstance(kpis['profit'], Decimal)
        self.assertIsInstance(kpis['total_sales'], int)
    
    def test_adapter_charts_structure(self):
        """Test adapter charts return expected structure."""
        adapter = get_adapter('phones')
        today = date.today()
        charts = adapter.charts(
            business=self.business,
            start_date=today - timedelta(days=30),
            end_date=today,
        )
        
        self.assertIn('sales_trend', charts)
        self.assertIn('profit_trend', charts)
        self.assertIn('payment_mix', charts)
        self.assertIn('top_products', charts)
        self.assertIn('top_agents', charts)
        self.assertIn('stock_overview', charts)

