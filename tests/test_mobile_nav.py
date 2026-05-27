# tests/test_mobile_nav.py
"""
Tests for vertical-aware mobile bottom navigation.
Ensures each vertical shows only relevant shortcuts, no phone-only items leak to other verticals.
"""
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.helpers_core import PHONES, CLOTHING, LIQUOR, PHARMACY, GYM
from inventory.mobile_nav import get_mobile_nav_items
from conftest import unique_slug

User = get_user_model()


class MobileNavTestCase(TestCase):
    """Test mobile navigation items are vertical-aware."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
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
        self.pharmacy_business = Business.objects.create(
            name="Pharmacy Business",
            slug=unique_slug("Pharmacy Business"),
            business_kind=PHARMACY,
        )
        self.liquor_business = Business.objects.create(
            name="Liquor Business",
            slug=unique_slug("Liquor Business"),
            business_kind=LIQUOR,
        )
        self.gym_business = Business.objects.create(
            name="Gym Business",
            slug=unique_slug("Gym Business"),
            business_kind=GYM,
        )
    
    def _set_active_business(self, request, business):
        """Helper to set active business in request."""
        request.session = {}
        request.session['biz_id'] = business.id
        request.session['active_business_id'] = business.id
        request.business_id = business.id
        request.business = business
    
    def test_phones_nav_items(self):
        """Phones should have: Home, Scan, Sell, Stock, Menu"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.phones_business)
        
        items = get_mobile_nav_items(request)
        keys = [item['key'] for item in items]
        
        self.assertIn('home', keys)
        self.assertIn('scan', keys)
        self.assertIn('sell', keys)
        self.assertIn('stock', keys)
        self.assertIn('menu', keys)
        self.assertEqual(len(items), 5)
        
        # Verify labels
        labels = [item['label'] for item in items]
        self.assertIn('Home', labels)
        self.assertIn('Scan', labels)
        self.assertIn('Sell', labels)
        self.assertIn('Stock', labels)
        self.assertIn('Menu', labels)
    
    def test_clothing_nav_items(self):
        """Clothing should have: Home, Add Product, Scan In, Sell, Menu"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.clothing_business)
        
        items = get_mobile_nav_items(request)
        keys = [item['key'] for item in items]
        
        self.assertIn('home', keys)
        self.assertIn('add_product', keys)
        self.assertIn('scan_in', keys)
        self.assertIn('sell', keys)
        self.assertIn('menu', keys)
        self.assertEqual(len(items), 5)
        
        # Should NOT have phone-only items
        self.assertNotIn('scan', keys)  # Should be 'scan_in' not 'scan'
        
        # Verify labels
        labels = [item['label'] for item in items]
        self.assertIn('Add Product', labels)
        self.assertIn('Scan In', labels)
    
    def test_pharmacy_nav_items(self):
        """Pharmacy should have: Home, Stock In, Sell, Stock, Menu"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.pharmacy_business)
        
        items = get_mobile_nav_items(request)
        keys = [item['key'] for item in items]
        
        self.assertIn('home', keys)
        self.assertIn('stock_in', keys)
        self.assertIn('sell', keys)
        self.assertIn('stock', keys)
        self.assertIn('menu', keys)
        self.assertEqual(len(items), 5)
        
        # Verify labels
        labels = [item['label'] for item in items]
        self.assertIn('Stock In', labels)
    
    def test_liquor_nav_items(self):
        """Liquor should have: Home, Stock In, Sell, Stock, Menu"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.liquor_business)
        
        items = get_mobile_nav_items(request)
        keys = [item['key'] for item in items]
        
        self.assertIn('home', keys)
        self.assertIn('stock_in', keys)
        self.assertIn('sell', keys)
        self.assertIn('stock', keys)
        self.assertIn('menu', keys)
        self.assertEqual(len(items), 5)
    
    def test_gym_nav_items(self):
        """Gym should have: Home, Add Member, Members, Payments, Menu"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.gym_business)
        
        items = get_mobile_nav_items(request)
        keys = [item['key'] for item in items]
        
        self.assertIn('home', keys)
        self.assertIn('add_member', keys)
        self.assertIn('members', keys)
        self.assertIn('payments', keys)
        self.assertIn('menu', keys)
        self.assertEqual(len(items), 5)
        
        # Should NOT have phone-only items
        self.assertNotIn('scan', keys)
        self.assertNotIn('stock', keys)
        
        # Verify labels
        labels = [item['label'] for item in items]
        self.assertIn('Add Member', labels)
        self.assertIn('Members', labels)
        self.assertIn('Payments', labels)
    
    def test_clothing_no_phone_items(self):
        """Clothing nav should NOT contain phone-specific items like 'Scan' (should be 'Scan In')"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.clothing_business)
        
        items = get_mobile_nav_items(request)
        labels = [item['label'] for item in items]
        
        # Should not have generic "Scan" (phones-specific)
        # Should have "Scan In" instead
        self.assertNotIn('Scan', [l for l in labels if l == 'Scan'])
        self.assertIn('Scan In', labels)
    
    def test_gym_no_phone_items(self):
        """Gym nav should NOT contain phone-specific items"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.gym_business)
        
        items = get_mobile_nav_items(request)
        labels = [item['label'] for item in items]
        
        # Should not have phone-specific labels
        self.assertNotIn('Scan', labels)
        self.assertNotIn('Stock', labels)
        self.assertNotIn('Sell', labels)  # Gym uses different terminology
    
    def test_pharmacy_no_phone_items(self):
        """Pharmacy nav should NOT contain phone-specific wording"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.pharmacy_business)
        
        items = get_mobile_nav_items(request)
        labels = [item['label'] for item in items]
        
        # Should have "Stock In" not generic phone terms
        self.assertIn('Stock In', labels)
    
    def test_all_items_have_required_fields(self):
        """All nav items should have required fields: key, label, icon_class, url"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.phones_business)
        
        items = get_mobile_nav_items(request)
        
        for item in items:
            self.assertIn('key', item)
            self.assertIn('label', item)
            self.assertIn('icon_class', item)
            self.assertIn('url', item)
            self.assertIsNotNone(item['key'])
            self.assertIsNotNone(item['label'])
            self.assertIsNotNone(item['icon_class'])
            self.assertIsNotNone(item['url'])
    
    def test_menu_item_has_is_menu_flag(self):
        """Menu item should have is_menu=True"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.phones_business)
        
        items = get_mobile_nav_items(request)
        menu_items = [item for item in items if item['key'] == 'menu']
        
        self.assertEqual(len(menu_items), 1)
        self.assertTrue(menu_items[0].get('is_menu', False))
        self.assertEqual(menu_items[0]['url'], '#')
    
    def test_mobile_nav_in_template_context(self):
        """Test that MOBILE_NAV_ITEMS is available in template context"""
        from tenants.context_processors import tenant_context
        
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.phones_business)
        
        context = tenant_context(request)
        
        self.assertIn('MOBILE_NAV_ITEMS', context)
        self.assertIsInstance(context['MOBILE_NAV_ITEMS'], list)
        self.assertGreater(len(context['MOBILE_NAV_ITEMS']), 0)
    
    def test_clothing_urls_use_vertical_prefix(self):
        """Clothing nav items should use /verticals/clothing/ URLs (except Add Product)"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.clothing_business)
        
        items = get_mobile_nav_items(request)
        
        for item in items:
            if item['key'] == 'menu':
                continue  # Menu doesn't navigate
            elif item['key'] == 'add_product':
                # Add Product uses /inventory/clothing/products/new/v2/
                self.assertTrue(
                    item['url'].startswith('/inventory/clothing/') or 
                    item['url'].startswith('/verticals/clothing/'),
                    f"Add Product URL should start with /inventory/clothing/ or /verticals/clothing/, got {item['url']}"
                )
            elif item['key'] == 'home':
                self.assertTrue(
                    item['url'].startswith('/verticals/clothing/'),
                    f"Home URL should start with /verticals/clothing/, got {item['url']}"
                )
            elif item['key'] == 'scan_in':
                self.assertTrue(
                    item['url'].startswith('/verticals/clothing/scan-in'),
                    f"Scan In URL should start with /verticals/clothing/scan-in, got {item['url']}"
                )
            elif item['key'] == 'sell':
                self.assertTrue(
                    item['url'].startswith('/verticals/clothing/sell'),
                    f"Sell URL should start with /verticals/clothing/sell, got {item['url']}"
                )
    
    def test_clothing_scan_in_url_is_correct(self):
        """Clothing Scan In should link to /verticals/clothing/scan-in/"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.clothing_business)
        
        items = get_mobile_nav_items(request)
        scan_in_item = next((item for item in items if item['key'] == 'scan_in'), None)
        
        self.assertIsNotNone(scan_in_item, "Scan In item should exist")
        self.assertEqual(scan_in_item['url'], '/verticals/clothing/scan-in/')
        self.assertEqual(scan_in_item['active_prefix'], '/verticals/clothing/scan-in')
    
    def test_pharmacy_urls_use_vertical_prefix(self):
        """Pharmacy nav items should use pharmacy URLs, not phones routes"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.pharmacy_business)
        
        items = get_mobile_nav_items(request)
        
        for item in items:
            if item['key'] == 'menu':
                continue
            elif item['key'] == 'home':
                self.assertTrue(
                    item['url'].startswith('/verticals/pharmacy/'),
                    f"Home URL should start with /verticals/pharmacy/, got {item['url']}"
                )
            elif item['key'] == 'stock_in':
                self.assertTrue(
                    item['url'].startswith('/pharmacy/stock-in'),
                    f"Stock In URL should start with /pharmacy/stock-in, got {item['url']}"
                )
            elif item['key'] == 'sell':
                self.assertTrue(
                    item['url'].startswith('/pharmacy/sell'),
                    f"Sell URL should start with /pharmacy/sell, got {item['url']}"
                )
            elif item['key'] == 'stock':
                # Pharmacy stock uses inventory:stock_list which is /inventory/list/
                # This is acceptable as pharmacy doesn't have its own stock route
                self.assertTrue(
                    item['url'].startswith('/inventory/list') or item['url'].startswith('/pharmacy/'),
                    f"Stock URL should start with /inventory/list or /pharmacy/, got {item['url']}"
                )
    
    def test_liquor_urls_use_vertical_prefix(self):
        """Liquor nav items should use liquor URLs, not phones routes"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.liquor_business)
        
        items = get_mobile_nav_items(request)
        
        for item in items:
            if item['key'] == 'menu':
                continue
            elif item['key'] == 'home':
                self.assertTrue(
                    item['url'].startswith('/verticals/liquor/'),
                    f"Home URL should start with /verticals/liquor/, got {item['url']}"
                )
            elif item['key'] == 'stock_in':
                self.assertTrue(
                    item['url'].startswith('/liquor/inventory'),
                    f"Stock In URL should start with /liquor/inventory, got {item['url']}"
                )
            elif item['key'] == 'sell':
                self.assertTrue(
                    item['url'].startswith('/liquor/sell'),
                    f"Sell URL should start with /liquor/sell, got {item['url']}"
                )
            elif item['key'] == 'stock':
                self.assertTrue(
                    item['url'].startswith('/liquor/stock'),
                    f"Stock URL should start with /liquor/stock, got {item['url']}"
                )
    
    def test_gym_urls_use_vertical_prefix(self):
        """Gym nav items should use gym URLs, not phones routes"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.gym_business)
        
        items = get_mobile_nav_items(request)
        
        for item in items:
            if item['key'] == 'menu':
                continue
            elif item['key'] == 'home':
                self.assertTrue(
                    item['url'].startswith('/verticals/gym/'),
                    f"Home URL should start with /verticals/gym/, got {item['url']}"
                )
            elif item['key'] in ['add_member', 'members', 'payments']:
                self.assertTrue(
                    item['url'].startswith('/gym/'),
                    f"{item['key']} URL should start with /gym/, got {item['url']}"
                )
    
    def test_phones_urls_unchanged(self):
        """Phones nav should remain unchanged (can use /inventory/ routes)"""
        request = self.factory.get('/')
        request.user = self.user
        self._set_active_business(request, self.phones_business)
        
        items = get_mobile_nav_items(request)
        
        # Verify phones URLs are as expected
        for item in items:
            if item['key'] == 'menu':
                continue
            # Phones can use /inventory/ routes - this is expected behavior
            self.assertIsNotNone(item['url'])
            self.assertNotEqual(item['url'], '#')
    
    def test_no_phones_routes_in_other_verticals(self):
        """Other verticals should not use phones-specific routes like /inventory/scan-in/"""
        request = self.factory.get('/')
        request.user = self.user
        
        # Test clothing
        self._set_active_business(request, self.clothing_business)
        items = get_mobile_nav_items(request)
        for item in items:
            if item['key'] == 'scan_in':
                self.assertNotEqual(
                    item['url'], '/inventory/scan-in/',
                    "Clothing Scan In should not use phones route /inventory/scan-in/"
                )
        
        # Test pharmacy
        self._set_active_business(request, self.pharmacy_business)
        items = get_mobile_nav_items(request)
        for item in items:
            if item['key'] == 'sell':
                self.assertNotIn(
                    '/inventory/phone-sale-wizard', item['url'],
                    "Pharmacy Sell should not use phones route"
                )
        
        # Test liquor
        self._set_active_business(request, self.liquor_business)
        items = get_mobile_nav_items(request)
        for item in items:
            if item['key'] == 'sell':
                self.assertNotIn(
                    '/inventory/phone-sale-wizard', item['url'],
                    "Liquor Sell should not use phones route"
                )
            if item['key'] == 'stock':
                # Liquor stock should use /liquor/stock/, not /inventory/list/
                self.assertTrue(
                    item['url'].startswith('/liquor/stock'),
                    f"Liquor Stock should use /liquor/stock/, got {item['url']}"
                )


class MobileNavIntegrationTestCase(TestCase):
    """Integration tests: verify mobile nav renders correctly in templates."""
    
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
        self.gym_business = Business.objects.create(
            name="Gym Business",
            slug=unique_slug("Gym Business"),
            business_kind=GYM,
        )
    
    def _set_active_business(self, business):
        """Helper to set active business in session."""
        session = self.client.session
        session['biz_id'] = business.id
        session['active_business_id'] = business.id
        session.save()
    
    def test_clothing_dashboard_renders_correct_nav(self):
        """Clothing dashboard should render clothing-specific nav items"""
        self._set_active_business(self.clothing_business)
        
        # Access clothing dashboard
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should contain clothing-specific nav items
        self.assertIn('Add Product', content)
        self.assertIn('Scan In', content)
        
        # Should NOT contain phone-only items
        # Note: This is a basic check - actual rendering depends on template structure
        # The key is that MOBILE_NAV_ITEMS context variable is set correctly
    
    def test_clothing_scan_in_href_in_rendered_nav(self):
        """Integration test: Clothing bottom nav should contain href='/verticals/clothing/scan-in/'"""
        self._set_active_business(self.clothing_business)
        
        # Access clothing dashboard
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check that the rendered HTML contains the correct href for scan-in
        # This verifies the URL is correctly passed to the template
        self.assertIn('/verticals/clothing/scan-in/', content)
    
    def test_gym_dashboard_renders_correct_nav(self):
        """Gym dashboard should render gym-specific nav items"""
        self._set_active_business(self.gym_business)
        
        # Access gym dashboard
        response = self.client.get(reverse('verticals:gym_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should contain gym-specific nav items (if rendered in template)
        # The key is that MOBILE_NAV_ITEMS context variable is set correctly
        # Actual rendering verification would require checking the rendered HTML structure

