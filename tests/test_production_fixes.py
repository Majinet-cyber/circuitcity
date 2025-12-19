# tests/test_production_fixes.py
"""
Targeted tests for production fixes:
1. Phone Scanner: Scan In uses same scanner as Scan & Sell
2. Fast Sell: Always shows inventory check message
3. Liquor: Stock In page with crate/bottle support
4. HQ Admin: Agents and Stock Trends pages render without 500 errors
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind


User = get_user_model()


class PhoneScannerUnificationTests(TestCase):
    """Test that Scan In and Scan & Sell use identical scanner component"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='agent', password='test123')
        self.business = Business.objects.create(
            name='Test Phones',
            business_kind=BusinessKind.PHONES
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='AGENT'
        )
        self.client.login(username='agent', password='test123')
    
    def test_scan_in_uses_phones_imei_scanner_js(self):
        """Scan In page must include phones-imei-scanner.js"""
        response = self.client.get(reverse('inventory:phone_scan_in'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'phones-imei-scanner.js')
        self.assertContains(response, 'data-imei-scan-trigger')
    
    def test_scan_sell_uses_phones_imei_scanner_js(self):
        """Scan & Sell page must include phones-imei-scanner.js"""
        response = self.client.get(reverse('inventory:phone_scan_sell'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'phones-imei-scanner.js')
        self.assertContains(response, 'data-imei-scan-trigger')
    
    def test_both_use_same_scanner_modal_css(self):
        """Both pages must use imei-scanner-modal.css"""
        scan_in = self.client.get(reverse('inventory:phone_scan_in'))
        scan_sell = self.client.get(reverse('inventory:phone_scan_sell'))
        
        self.assertContains(scan_in, 'imei-scanner-modal.css')
        self.assertContains(scan_sell, 'imei-scanner-modal.css')


class FastSellInventoryCheckTests(TestCase):
    """Test that Fast Sell always shows inventory check messages"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='agent', password='test123')
        self.business = Business.objects.create(
            name='Test Pharmacy',
            business_kind=BusinessKind.PHARMACY
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='AGENT'
        )
        self.client.login(username='agent', password='test123')
    
    def test_fast_sell_lookup_not_found_message(self):
        """Fast Sell API must return 'Not found in your inventory' message"""
        response = self.client.get(
            reverse('inventory:api_fast_sell_lookup'),
            {'barcode': 'NONEXISTENT123', 'vertical': 'pharmacy'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['found'])
        self.assertIn('Not found in your inventory', data['message'])
    
    def test_fast_sell_template_shows_checking_state(self):
        """Fast Sell template must show 'Checking inventory...' state"""
        response = self.client.get(reverse('verticals:pharmacy_fast_sell'))
        self.assertEqual(response.status_code, 200)
        # Check for the checking state in JavaScript
        self.assertContains(response, 'Checking inventory')


class LiquorStockInTests(TestCase):
    """Test Liquor Stock In page with gamified UI and crate/bottle support"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='manager', password='test123')
        self.business = Business.objects.create(
            name='Test Bar',
            business_kind=BusinessKind.LIQUOR
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER'
        )
        self.product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('5000.00')
        )
        self.client.login(username='manager', password='test123')
    
    def test_stock_in_page_exists(self):
        """Liquor Stock In page must be accessible"""
        response = self.client.get(reverse('liquor:stock_in'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stock In Liquor')
    
    def test_stock_in_has_crate_bottle_toggle(self):
        """Stock In page must have crate/bottle quantity type toggle"""
        response = self.client.get(reverse('liquor:stock_in'))
        self.assertContains(response, 'Crates')
        self.assertContains(response, 'Bottles')
        self.assertContains(response, 'quantity_type')
    
    def test_stock_in_has_editable_crate_size(self):
        """Stock In page must have editable crate size field"""
        response = self.client.get(reverse('liquor:stock_in'))
        self.assertContains(response, 'crate_size')
        self.assertContains(response, 'Bottles per Crate')
    
    def test_stock_in_crates_submission(self):
        """Stock In must accept crate-based submissions"""
        response = self.client.post(reverse('liquor:stock_in'), {
            'product_id': self.product.id,
            'quantity_type': 'crates',
            'crates_count': 2,
            'crate_size': 24,
            'price_per_bottle': '5000.00'
        })
        self.assertEqual(response.status_code, 302)  # Redirect on success
    
    def test_stock_in_bottles_submission(self):
        """Stock In must accept bottle-based submissions"""
        response = self.client.post(reverse('liquor:stock_in'), {
            'product_id': self.product.id,
            'quantity_type': 'bottles',
            'bottles_count': 48,
            'price_per_bottle': '5000.00'
        })
        self.assertEqual(response.status_code, 302)  # Redirect on success
    
    def test_stock_in_gamified_ui(self):
        """Stock In page must have gamified product cards"""
        response = self.client.get(reverse('liquor:stock_in'))
        self.assertContains(response, 'product-card')
        self.assertContains(response, 'gamification-bar')


class HQAdminPagesTests(TestCase):
    """Test that HQ Admin pages render without 500 errors"""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.login(username='hqadmin', password='test123')
    
    def test_agents_page_renders(self):
        """HQ Agents page must render without 500 error"""
        response = self.client.get(reverse('hq:agents'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agents')
    
    def test_stock_trends_page_renders(self):
        """HQ Stock Trends page must render without 500 error"""
        response = self.client.get(reverse('hq:stock_trends'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stock Trends')
    
    def test_hq_has_unified_sidebar(self):
        """HQ pages must use unified sidebar (not duplicate)"""
        agents_response = self.client.get(reverse('hq:agents'))
        stock_response = self.client.get(reverse('hq:stock_trends'))
        
        # Check both pages include the HQ sidebar
        self.assertContains(agents_response, 'hqSidebar')
        self.assertContains(stock_response, 'hqSidebar')
        
        # Check they use the same sidebar template
        self.assertContains(agents_response, 'Emajinet HQ')
        self.assertContains(stock_response, 'Emajinet HQ')
    
    def test_hq_sidebar_mobile_responsive(self):
        """HQ sidebar must be mobile-responsive (off-canvas)"""
        response = self.client.get(reverse('hq:agents'))
        # Check for mobile toggle button
        self.assertContains(response, 'hqSidebarToggle')
        # Check for backdrop
        self.assertContains(response, 'hqBackdrop')


class IntegrationSmokeTests(TestCase):
    """Smoke tests to ensure no regressions"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='user', password='test123')
        self.business = Business.objects.create(
            name='Test Business',
            business_kind=BusinessKind.PHONES
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='AGENT'
        )
        self.client.login(username='user', password='test123')
    
    def test_no_regression_inventory_dashboard(self):
        """Inventory dashboard must still work"""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_no_regression_scan_in(self):
        """Scan In must still work"""
        response = self.client.get(reverse('inventory:scan_in'))
        self.assertEqual(response.status_code, 200)
    
    def test_no_regression_scan_sold(self):
        """Scan Sold must still work"""
        response = self.client.get(reverse('inventory:scan_sold'))
        self.assertEqual(response.status_code, 200)

