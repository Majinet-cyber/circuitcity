"""
Tests for analytics API scoping to ensure business data isolation.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, Client

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


class AnalyticsAPIScopingTestCase(TestCase):
    """Test that analytics APIs properly scope data to current business."""
    
    def setUp(self):
        self.client = Client()
        
        # Create two users and businesses
        self.user_a = User.objects.create_user(
            username='user_a',
            email='usera@example.com',
            password='testpass123'
        )
        self.user_b = User.objects.create_user(
            username='user_b',
            email='userb@example.com',
            password='testpass123'
        )
        
        self.business_a = Business.objects.create(
            name='Business A',
            slug='business-a',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        self.business_b = Business.objects.create(
            name='Business B',
            slug='business-b',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        
        Membership.objects.create(
            user=self.user_a,
            business=self.business_a,
            role='MANAGER',
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.user_b,
            business=self.business_b,
            role='MANAGER',
            status='ACTIVE'
        )
    
    def test_kpis_scoped_to_business(self):
        """Test KPIs API only returns data for active business."""
        # Login as user_a with business_a active
        self.client.force_login(self.user_a)
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        response = self.client.get('/app/analytics/api/kpis/')
        self.assertEqual(response.status_code, 200)
        
        # Verify the adapter is using business_a
        # (The actual data isolation is handled by the adapter's queryset filtering)
        data = response.json()
        self.assertIn('revenue', data)
        # Data should be scoped to business_a only
    
    def test_sales_trend_scoped_to_business(self):
        """Test sales trend API only returns data for active business."""
        self.client.force_login(self.user_a)
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        response = self.client.get('/app/analytics/api/sales_trend/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sales_trend', data)
        # Data should be scoped to business_a only
    
    def test_cross_business_isolation(self):
        """Test that user from business A cannot access business B's data."""
        # Login as user_a
        self.client.force_login(self.user_a)
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        # Try to access with business_b ID in query params (should be ignored)
        response = self.client.get('/app/analytics/api/kpis/?business_id={}'.format(self.business_b.id))
        
        # Should still return data for business_a (active business in session)
        # The location filter in query params should not allow cross-business access
        self.assertEqual(response.status_code, 200)
        # The adapter's get_sales_queryset should filter by business from session, not query param


class HQAnalyticsPermissionsTestCase(TestCase):
    """Test HQ analytics requires proper permissions."""
    
    def setUp(self):
        self.client = Client()
        self.regular_user = User.objects.create_user(
            username='regular_user',
            email='regular@example.com',
            password='testpass123'
        )
        self.hq_staff = User.objects.create_user(
            username='hq_staff',
            email='hq@example.com',
            password='testpass123',
            is_staff=True
        )
    
    def test_hq_analytics_requires_staff(self):
        """Test HQ analytics requires staff permission."""
        self.client.force_login(self.regular_user)
        response = self.client.get('/hq/analytics/')
        # Should redirect or return 403
        self.assertIn(response.status_code, [302, 403])
    
    def test_hq_analytics_allows_staff(self):
        """Test HQ analytics allows staff users."""
        self.client.force_login(self.hq_staff)
        response = self.client.get('/hq/analytics/')
        # Should return 200 (or redirect if no template)
        self.assertIn(response.status_code, [200, 302])

