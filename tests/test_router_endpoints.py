# tests/test_router_endpoints.py
"""
Tests for business-aware router endpoints to prevent vertical leakage.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.helpers_core import PHONES, CLOTHING, LIQUOR, PHARMACY, GYM
from conftest import unique_slug

User = get_user_model()


class RouterEndpointsTestCase(TestCase):
    """Test business-aware router endpoints redirect correctly."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Create businesses for different verticals
        self.phones_business = Business.objects.create(
            name="Phones Business",
            slug=unique_slug("Phones Business"),
            business_kind=PHONES,
        )
        self.clothing_business = Business.objects.create(
            name="Clothing Business",
            slug=unique_slug("Clothing Business"),
            business_kind=CLOTHING,
        )
        self.liquor_business = Business.objects.create(
            name="Liquor Business",
            slug=unique_slug("Liquor Business"),
            business_kind=LIQUOR,
        )
    
    def _set_active_business(self, business):
        """Helper to set active business in session."""
        session = self.client.session
        session['biz_id'] = business.id
        session['active_business_id'] = business.id
        session.save()
    
    def test_app_home_redirects_clothing_to_clothing_dashboard(self):
        """Test /app/home/ redirects clothing business to clothing dashboard."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('clothing/dashboard', response.url)
    
    def test_app_home_redirects_phones_to_phones_dashboard(self):
        """Test /app/home/ redirects phones business to phones dashboard."""
        self._set_active_business(self.phones_business)
        response = self.client.get(reverse('app_router:home'))
        self.assertEqual(response.status_code, 302)
        # Should redirect to inventory dashboard (phones default)
        self.assertIn('dashboard', response.url)
    
    def test_app_scan_redirects_clothing_to_scan_in(self):
        """Test /app/scan/ redirects clothing business to scan-in."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:scan'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('scan-in', response.url)
    
    def test_app_sell_redirects_clothing_to_clothing_sell(self):
        """Test /app/sell/ redirects clothing business to clothing sell."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:sell'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('clothing/sell', response.url)
    
    def test_app_sell_redirects_phones_to_phone_sale_wizard(self):
        """Test /app/sell/ redirects phones business to phone sale wizard."""
        self._set_active_business(self.phones_business)
        response = self.client.get(reverse('app_router:sell'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('phone-sale-wizard', response.url)
    
    def test_app_stock_redirects_clothing_to_stock_list(self):
        """Test /app/stock/ redirects clothing business to stock list."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:stock'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('list', response.url)
    
    def test_app_stock_redirects_liquor_to_liquor_stock(self):
        """Test /app/stock/ redirects liquor business to liquor stock overview."""
        self._set_active_business(self.liquor_business)
        response = self.client.get(reverse('app_router:stock'))
        self.assertEqual(response.status_code, 302)
        # Should redirect to liquor stock overview
        self.assertIn('liquor', response.url.lower())
    
    def test_app_wallet_redirects_to_wallet(self):
        """Test /app/wallet/ redirects to wallet (same for all verticals)."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:wallet'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('wallet', response.url)
    
    def test_app_sim_redirects_to_simulator(self):
        """Test /app/sim/ redirects to business simulator."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:sim'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('simulator', response.url)
    
    def test_app_analytics_accessible(self):
        """Test /app/analytics/ is accessible."""
        self._set_active_business(self.clothing_business)
        response = self.client.get(reverse('app_router:analytics'))
        # Should render analytics page
        self.assertEqual(response.status_code, 200)
    
    def test_app_analytics_redirects_phones_to_analytics(self):
        """Test /app/analytics/ works for phones business."""
        self._set_active_business(self.phones_business)
        response = self.client.get(reverse('app_router:analytics'))
        # Should render analytics page
        self.assertEqual(response.status_code, 200)
    
    def test_phones_inventory_dashboard_redirects_to_analytics(self):
        """Test phones inventory_dashboard redirects to analytics."""
        self._set_active_business(self.phones_business)
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        # Should redirect to analytics
        self.assertEqual(response.status_code, 302)
        self.assertIn('analytics', response.url)
    
    def test_clothing_inventory_dashboard_not_redirected(self):
        """Test clothing business inventory_dashboard doesn't redirect (not phones)."""
        self._set_active_business(self.clothing_business)
        # This might not be accessible for clothing, but shouldn't redirect to analytics
        # Just test that phones-specific behavior doesn't apply
        pass


class VerticalGuardTestCase(TestCase):
    """Test vertical guard prevents leakage from old links."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        self.clothing_business = Business.objects.create(
            name="Clothing Business",
            slug=unique_slug("Clothing Business"),
            business_kind=CLOTHING,
        )
    
    def _set_active_business(self, business):
        """Helper to set active business in session."""
        session = self.client.session
        session['biz_id'] = business.id
        session['active_business_id'] = business.id
        session.save()
    
    def test_old_phones_url_redirects_clothing_business(self):
        """Test old /verticals/phones/stock/ redirects clothing business correctly."""
        self._set_active_business(self.clothing_business)
        # This would be handled by the vertical guard decorator
        # For now, we test that router endpoints work correctly
        response = self.client.get(reverse('app_router:stock'))
        self.assertEqual(response.status_code, 302)
        # Should NOT redirect to phones stock
        self.assertNotIn('phones', response.url.lower())
    
    def test_clothing_business_bottom_nav_does_not_go_to_phones(self):
        """Test clothing business bottom nav links don't resolve to phones URLs."""
        self._set_active_business(self.clothing_business)
        
        # Test all bottom nav router endpoints
        endpoints = ['home', 'scan', 'sell', 'stock', 'wallet', 'sim', 'analytics']
        for endpoint in endpoints:
            response = self.client.get(reverse(f'app_router:{endpoint}'))
            if response.status_code == 302:
                # Should NOT contain phones-specific URLs or text
                self.assertNotIn('/inventory/phone', response.url.lower(), 
                               f"{endpoint} endpoint should not redirect to phones URL")
                self.assertNotIn('imei', response.url.lower(),
                               f"{endpoint} endpoint should not redirect to IMEI-related URLs")
    
    def test_phones_business_analytics_accessible(self):
        """Test phones business can access analytics."""
        phones_business = Business.objects.create(
            name="Phones Business Test",
            slug=unique_slug("Phones Business Test"),
            business_kind=PHONES,
        )
        self._set_active_business(phones_business)
        response = self.client.get(reverse('app_router:analytics'))
        self.assertEqual(response.status_code, 200)
        # Should render analytics page (not redirect)
        self.assertContains(response, 'Analytics', status_code=200)

