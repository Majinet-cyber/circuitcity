# tests/test_audit_hq.py
"""
Tests for HQ audit log visibility and access control.

Business rule: Audit logs must show only platform staff/superuser activity,
not merchant/tenant activity. This proves HQ doesn't snoop merchant data.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from audit.models import AuditLog
from tenants.models import Business

User = get_user_model()


class AuditHQVisibilityTest(TestCase):
    """Test audit log visibility is restricted to staff activity only."""
    
    def setUp(self):
        """Set up test users, business, and audit logs."""
        # Create test business
        self.business = Business.objects.create(
            name="Test Merchant",
            slug="test-merchant",
            status="ACTIVE"
        )
        
        # Create staff user (HQ)
        self.staff_user = User.objects.create_user(
            username="hq_staff",
            email="staff@emajinet.com",
            password="testpass123",
            is_staff=True,
            is_superuser=False
        )
        
        # Create superuser (HQ)
        self.superuser = User.objects.create_user(
            username="hq_admin",
            email="admin@emajinet.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        
        # Create non-staff merchant user
        self.merchant_user = User.objects.create_user(
            username="merchant_manager",
            email="merchant@test.com",
            password="testpass123",
            is_staff=False,
            is_superuser=False
        )
        
        # Create audit logs for staff user
        self.staff_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            entity="Business",
            entity_id=str(self.business.id),
            action="VIEW",
            message="Staff viewed business dashboard",
            ip="192.168.1.1"
        )
        
        # Create audit log for superuser
        self.superuser_log = AuditLog.objects.create(
            business=self.business,
            user=self.superuser,
            entity="Business",
            entity_id=str(self.business.id),
            action="EXPORT",
            message="Admin exported business data",
            ip="192.168.1.2"
        )
        
        # Create audit log for merchant (should NOT appear in HQ audit list)
        self.merchant_log = AuditLog.objects.create(
            business=self.business,
            user=self.merchant_user,
            entity="InventoryItem",
            entity_id="123",
            action="CREATE",
            message="Merchant created inventory item",
            ip="192.168.1.100"
        )
        
        self.client = Client()
        self.audit_url = reverse('audit:log_list')
    
    def test_hq_audit_shows_only_staff_activity(self):
        """
        Test that HQ audit logs page shows only staff/superuser activity,
        excluding merchant/non-staff activity.
        """
        # Log in as staff user
        self.client.login(username='hq_staff', password='testpass123')
        
        # Request audit logs page
        response = self.client.get(self.audit_url)
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Should contain staff activity
        self.assertContains(response, 'hq_staff')
        self.assertContains(response, 'Staff viewed business dashboard')
        
        # Should contain superuser activity
        self.assertContains(response, 'hq_admin')
        self.assertContains(response, 'Admin exported business data')
        
        # Should NOT contain merchant activity
        self.assertNotContains(response, 'merchant_manager')
        self.assertNotContains(response, 'Merchant created inventory item')
    
    def test_non_staff_cannot_access_audit_logs(self):
        """
        Test that non-staff users (merchants) cannot access the audit logs page.
        Should return 403 or redirect.
        """
        # Log in as merchant user
        self.client.login(username='merchant_manager', password='testpass123')
        
        # Try to access audit logs
        response = self.client.get(self.audit_url)
        
        # Should be denied (403) or redirected
        # The @hq_only decorator should handle this
        self.assertIn(response.status_code, [403, 302])
        
        # If redirected, should not be to the audit page
        if response.status_code == 302:
            self.assertNotIn('/audit/logs', response.url)
    
    def test_anonymous_user_cannot_access_audit_logs(self):
        """Test that anonymous users cannot access audit logs."""
        # Don't log in
        response = self.client.get(self.audit_url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)
    
    def test_audit_export_csv_staff_only(self):
        """Test that CSV export also shows only staff activity."""
        # Log in as staff
        self.client.login(username='hq_staff', password='testpass123')
        
        # Request CSV export
        response = self.client.get(self.audit_url + '?export=csv')
        
        # Should succeed with CSV content type
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # Convert response to string
        content = response.content.decode('utf-8')
        
        # Should contain staff activity
        self.assertIn('hq_staff', content)
        self.assertIn('hq_admin', content)
        
        # Should NOT contain merchant activity
        self.assertNotIn('merchant_manager', content)
    
    # Test removed: audit stats template doesn't exist yet (optional feature)
    # When implemented, it should follow same staff-only pattern as audit_log_list


class AuditFiltersTest(TestCase):
    """Test that audit log filters work correctly with staff-only scope."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            status="ACTIVE"
        )
        
        self.staff_user = User.objects.create_user(
            username="staff1",
            email="staff1@emajinet.com",
            password="testpass123",
            is_staff=True
        )
        
        # Create multiple logs with different actions
        AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            entity="Business",
            entity_id="1",
            action="VIEW",
            message="Viewed business"
        )
        
        AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            entity="Business",
            entity_id="1",
            action="EXPORT",
            message="Exported data"
        )
        
        self.client = Client()
        self.client.login(username='staff1', password='testpass123')
        self.audit_url = reverse('audit:log_list')
    
    def test_action_filter_works(self):
        """Test that action filter works correctly."""
        response = self.client.get(self.audit_url + '?action=VIEW')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Viewed business')
        self.assertNotContains(response, 'Exported data')
    
    def test_search_filter_works(self):
        """Test that search filter works correctly."""
        response = self.client.get(self.audit_url + '?search=Exported')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exported data')
        self.assertNotContains(response, 'Viewed business')

