# tests/test_phones_dashboard_renders.py
"""
REGRESSION TEST: Phones dashboard must render without 500 errors.

This test prevents regressions of:
1. VariableDoesNotExist: YESTERDAY_SUMMARY not in template context
2. NoReverseMatch: 'sales' namespace not registered

RULE: This test MUST pass. If it fails, the phones dashboard is broken.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestPhonesDashboardRenders(TestCase):
    """
    Regression tests to ensure phones dashboard always renders.
    
    These tests would have caught the YESTERDAY_SUMMARY and sales namespace bugs.
    """
    
    def setUp(self):
        """Set up minimal test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Store",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        # Create manager membership
        self.membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager",
            is_active=True
        )
        
        # Create client
        self.client = Client()
    
    def test_phones_dashboard_renders_for_manager(self):
        """
        CRITICAL: Phones dashboard MUST render without 500 error.
        
        This test prevents:
        - VariableDoesNotExist crashes from missing template context
        - NoReverseMatch from unregistered URL namespaces
        - Template syntax errors
        """
        # Login as manager
        self.client.login(username="manager@test.com", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # GET phones dashboard
        url = reverse('verticals:phones_dashboard')
        response = self.client.get(url)
        
        # MUST return 200 (not 500)
        self.assertEqual(
            response.status_code, 
            200,
            f"Phones dashboard returned {response.status_code}. "
            f"Expected 200. This is a REGRESSION - the dashboard is broken!"
        )
        
        # MUST contain expected content
        self.assertContains(response, "Phones & Electronics")
        
        # MUST NOT contain error messages
        self.assertNotContains(response, "VariableDoesNotExist", status_code=200)
        self.assertNotContains(response, "NoReverseMatch", status_code=200)
    
    def test_phones_dashboard_renders_with_no_sales_data(self):
        """
        Dashboard must render even with zero sales (empty state).
        
        This ensures YESTERDAY_SUMMARY being None doesn't crash the template.
        """
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('verticals:phones_dashboard')
        response = self.client.get(url)
        
        # MUST render successfully even with no data
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phones & Electronics")
    
    def test_phones_dashboard_renders_with_date_filters(self):
        """
        Dashboard must render with all date filter options.
        
        Tests: today, 7d, mtd, custom
        """
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Test each date range filter
        date_ranges = ['today', '7d', 'mtd']
        for range_param in date_ranges:
            url = reverse('verticals:phones_dashboard') + f'?range={range_param}'
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code, 
                200,
                f"Dashboard with range={range_param} returned {response.status_code}"
            )
    
    def test_sales_namespace_is_registered(self):
        """
        CRITICAL: 'sales' namespace MUST be registered.
        
        This prevents NoReverseMatch errors from templates using {% url 'sales:...' %}
        """
        from django.urls import resolve, reverse as django_reverse
        from django.urls.exceptions import NoReverseMatch
        
        try:
            # Try to reverse a sales namespace URL
            url = django_reverse('sales:rollback_home')
            self.assertTrue(url.startswith('/sales/'), 
                           f"sales:rollback_home resolved to {url}, expected /sales/...")
        except NoReverseMatch:
            self.fail(
                "sales:rollback_home not found. "
                "The 'sales' namespace is NOT registered in cc/urls.py. "
                "This WILL cause 500 errors on any page using sales: URLs!"
            )
    
    def test_phones_dashboard_has_rollback_link_for_managers(self):
        """
        Managers should see the Rollback Sale link (which uses sales: namespace).
        
        This ensures the sales namespace registration is working in templates.
        """
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Manager should see Rollback link
        self.assertContains(response, "Rollback Sale")
        
        # Template should have rendered the URL (not errored)
        # We don't need to assert the exact href since it's enough that the page rendered
    
    def test_phones_dashboard_context_has_required_keys(self):
        """
        Dashboard context MUST include all required keys to prevent template errors.
        
        Tests presence of:
        - YESTERDAY_SUMMARY or yesterday_summary (can be None, but must exist)
        - dashboard_kpis
        - IS_MANAGER
        - IS_AGENT
        """
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check context keys exist (even if None)
        context = response.context
        
        # YESTERDAY_SUMMARY must be in context (can be None)
        self.assertIn('YESTERDAY_SUMMARY', context, 
                     "YESTERDAY_SUMMARY missing from context - will cause template crash!")
        
        # Dashboard KPIs must exist
        self.assertIn('dashboard_kpis', context)
        
        # Role flags must exist
        self.assertIn('IS_MANAGER', context)
        self.assertIn('IS_AGENT', context)
        
        # Manager should have IS_MANAGER = True
        self.assertTrue(context['IS_MANAGER'], 
                       "Manager user should have IS_MANAGER=True")


@pytest.mark.django_db
class TestPhonesDashboardTemplateFailsafe(TestCase):
    """
    Test that dashboard partials are failsafe (don't crash on missing vars).
    """
    
    def setUp(self):
        """Set up minimal test data"""
        self.business = Business.objects.create(
            name="Test Store",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main",
            is_default=True
        )
        
        self.manager = User.objects.create_user(
            username="mgr@test.com",
            email="mgr@test.com",
            password="pass123"
        )
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager",
            is_active=True
        )
        
        self.client = Client()
    
    def test_dashboard_renders_when_yesterday_summary_is_none(self):
        """
        Dashboard partial must gracefully handle YESTERDAY_SUMMARY=None.
        
        This is the core fix - template uses {% if YESTERDAY_SUMMARY %} guard.
        """
        self.client.login(username="mgr@test.com", password="pass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Must render even if YESTERDAY_SUMMARY is None
        self.assertEqual(response.status_code, 200)
        
        # Yesterday summary widget should be hidden (not crashed)
        # Check that the page doesn't have template error markers
        content = response.content.decode('utf-8')
        self.assertNotIn('VariableDoesNotExist', content)
        self.assertNotIn('Template error', content)

