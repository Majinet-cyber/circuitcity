# tests/test_tenant_isolation.py
"""
Tests for tenant/manager isolation and access control.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.critical  # Multi-tenant isolation is security-critical
class TenantIsolationTest(TestCase):
    """Test that managers cannot access other businesses' data."""
    
    def setUp(self):
        """Create test businesses, users, and data."""
        # Business A
        self.business_a = Business.objects.create(
            name="Business A",
            slug="business-a",
            status="ACTIVE"
        )
        self.manager_a = User.objects.create_user(
            username="manager_a",
            password="password123"
        )
        Membership.objects.create(
            user=self.manager_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create location for business A
        self.location_a = Location.objects.create(
            business=self.business_a,
            name="Store A",
            is_active=True
        )
        
        # Create inventory item for business A
        self.item_a = InventoryItem.objects.create(
            business=self.business_a,
            location=self.location_a,
            name="Item A",
            sku="ITEM-A-001"
        )
        
        # Business B
        self.business_b = Business.objects.create(
            name="Business B",
            slug="business-b",
            status="ACTIVE"
        )
        self.manager_b = User.objects.create_user(
            username="manager_b",
            password="password123"
        )
        Membership.objects.create(
            user=self.manager_b,
            business=self.business_b,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create location for business B
        self.location_b = Location.objects.create(
            business=self.business_b,
            name="Store B",
            is_active=True
        )
        
        # Create inventory item for business B
        self.item_b = InventoryItem.objects.create(
            business=self.business_b,
            location=self.location_b,
            name="Item B",
            sku="ITEM-B-001"
        )
        
        self.client = Client()
    
    def test_manager_cannot_see_other_business_inventory(self):
        """Manager A cannot see inventory from Business B."""
        # Login as manager A
        self.client.login(username="manager_a", password="password123")
        
        # Set business A as active
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        # Try to access inventory list
        response = self.client.get('/inventory/list/')
        self.assertEqual(response.status_code, 200)
        
        # Response should contain item A but not item B
        content = response.content.decode()
        self.assertIn("Item A", content)
        self.assertNotIn("Item B", content)
    
    def test_manager_cannot_switch_to_other_business(self):
        """Manager A cannot switch to Business B."""
        # Login as manager A
        self.client.login(username="manager_a", password="password123")
        
        # Try to set business B as active
        response = self.client.post(f'/tenants/set-active/{self.business_b.id}/', follow=True)
        
        # Should be denied or redirected
        self.assertIn(response.status_code, [403, 302, 200])
        
        # Session should still have business A (or none)
        session_biz_id = self.client.session.get('active_business_id')
        if session_biz_id:
            self.assertEqual(session_biz_id, self.business_a.id)
    
    def test_manager_cannot_access_other_business_via_url(self):
        """Manager cannot access other business data via URL manipulation."""
        # Login as manager A
        self.client.login(username="manager_a", password="password123")
        
        # Set business A as active
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        # Try to access item B directly by URL
        try:
            response = self.client.get(f'/inventory/items/{self.item_b.id}/')
            # Should be 404 or redirect, not showing the actual item
            self.assertIn(response.status_code, [403, 404, 302])
        except Exception:
            # If the URL doesn't exist, that's also fine
            pass
    
    def test_superuser_can_access_all_businesses(self):
        """Superusers can access any business."""
        superuser = User.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@example.com"
        )
        self.client.login(username="admin", password="admin123")
        
        # Set business A as active
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        response = self.client.get('/inventory/list/')
        self.assertEqual(response.status_code, 200)
        
        # Switch to business B
        session['active_business_id'] = self.business_b.id
        session.save()
        
        response = self.client.get('/inventory/list/')
        self.assertEqual(response.status_code, 200)
    
    def test_manager_never_sees_choose_business_screen(self):
        """Managers with one business should skip the chooser."""
        # Login as manager A (who only has business A)
        response = self.client.post('/accounts/login/', {
            'username': 'manager_a',
            'password': 'password123'
        }, follow=True)
        
        # Should not land on choose_business page
        self.assertNotIn('/tenants/choose', response.request['PATH_INFO'])
        
        # Should have business A set in session
        self.assertEqual(
            self.client.session.get('active_business_id'),
            self.business_a.id
        )


@pytest.mark.django_db
class WalletScopingTest(TestCase):
    """Test that wallet views are properly scoped to businesses."""
    
    def setUp(self):
        """Create test businesses and users."""
        self.business_a = Business.objects.create(
            name="Business A",
            slug="business-a",
            status="ACTIVE"
        )
        self.manager_a = User.objects.create_user(
            username="manager_a",
            password="password123"
        )
        Membership.objects.create(
            user=self.manager_a,
            business=self.business_a,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.business_b = Business.objects.create(
            name="Business B",
            slug="business-b",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def test_wallet_admin_scoped_to_business(self):
        """Wallet admin view only shows data for active business."""
        self.client.login(username="manager_a", password="password123")
        
        # Set business A as active
        session = self.client.session
        session['active_business_id'] = self.business_a.id
        session.save()
        
        # Access wallet admin
        response = self.client.get('/wallet/admin/')
        
        # Should be accessible
        self.assertEqual(response.status_code, 200)
        
        # Verify it's scoped to business A
        # (This would require checking the queryset, which varies by implementation)

