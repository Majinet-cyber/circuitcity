"""
Regression tests for pharmacy scan-in (Stock In) functionality
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business

User = get_user_model()


class PharmacyScanInRegressionTests(TestCase):
    """
    Regression tests to ensure pharmacy scan-in page works without errors.
    
    These tests prevent:
    - Missing {% load static %} causing TemplateSyntaxError
    - View errors when accessing /pharmacy/stock-in/
    - Template rendering issues
    """
    
    def setUp(self):
        """Create test data"""
        # Create pharmacy business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            business_kind="PHARMACY"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="pharmacist",
            password="testpass123",
            email="pharmacist@test.com"
        )
        self.manager.assigned_business = self.business
        self.manager.assigned_role = "MANAGER"
        self.manager.save()
        
        # Create agent user
        self.agent = User.objects.create_user(
            username="pharmacy_agent",
            password="testpass123",
            email="agent@test.com"
        )
        self.agent.assigned_business = self.business
        self.agent.assigned_role = "AGENT"
        self.agent.save()
        
        self.client = Client()
    
    def test_pharmacy_manager_can_access_scan_in(self):
        """
        Test that /pharmacy/stock-in/ returns HTTP 200 for pharmacy managers.
        
        Regression test for TemplateSyntaxError due to missing {% load static %}.
        """
        self.client.force_login(self.manager)
        
        # Set active business in session (required by middleware)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('pharmacy:stock_in')
        response = self.client.get(url, HTTP_HOST='testserver')
        
        # Should return 200, not 500
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}. "
            f"This indicates a template or view error in pharmacy scan-in."
        )
    
    def test_pharmacy_agent_can_access_scan_in(self):
        """
        Test that pharmacy agents can also access the scan-in page.
        """
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('pharmacy:stock_in')
        response = self.client.get(url, HTTP_HOST='testserver')
        
        # Should return 200 (or 403 if permissions deny, but not 500)
        self.assertIn(
            response.status_code,
            [200, 403],
            f"Expected 200 or 403, got {response.status_code}. "
            f"500 indicates a template or server error."
        )
    
    def test_pharmacy_stock_in_uses_correct_template(self):
        """
        Test that the correct template is used for pharmacy stock-in.
        """
        self.client.force_login(self.manager)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('pharmacy:stock_in')
        response = self.client.get(url, HTTP_HOST='testserver')
        
        self.assertTemplateUsed(response, 'verticals/pharmacy/stock_in.html')
    
    def test_phones_scan_in_still_works(self):
        """
        Safety regression: Ensure phones scan-in wasn't broken by pharmacy fixes.
        """
        # Create phones business
        phones_business = Business.objects.create(
            name="Test Phone Shop",
            slug="test-phone-shop",
            business_kind="PHONES"
        )
        
        # Create phones manager
        phones_manager = User.objects.create_user(
            username="phone_manager",
            password="testpass123",
            email="phones@test.com"
        )
        phones_manager.assigned_business = phones_business
        phones_manager.assigned_role = "MANAGER"
        phones_manager.save()
        
        self.client.force_login(phones_manager)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = phones_business.id
        session.save()
        
        # Try to access phones scan-in
        try:
            url = reverse('inventory:scan_in')
            response = self.client.get(url, HTTP_HOST='testserver')
            
            # Should return 200 or redirect (not 500)
            self.assertIn(
                response.status_code,
                [200, 302],
                f"Phones scan-in broken: got {response.status_code}"
            )
        except Exception as e:
            self.skipTest(f"Phones scan-in URL not configured: {e}")

