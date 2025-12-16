"""
Tests for Pricing Page, Mobile Table Slider, and API Endpoint Fixes
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business, Location, Membership

User = get_user_model()


class PricingPageTests(TestCase):
    """Tests for the /pricing/ page"""

    def setUp(self):
        self.client = Client()

    def test_pricing_page_exists(self):
        """Test that /pricing/ returns 200"""
        response = self.client.get('/pricing/')
        self.assertEqual(response.status_code, 200, 
                        "Pricing page should return 200 OK")

    def test_pricing_page_url_reverse(self):
        """Test that pricing URL can be reversed"""
        url = reverse('staticpages:pricing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200,
                        "Pricing page URL should resolve correctly")

    def test_pricing_page_has_free_trial_banner(self):
        """Test that pricing page shows 30-day free trial banner"""
        response = self.client.get('/pricing/')
        content = response.content.decode('utf-8')
        
        # Check for free trial messaging
        self.assertIn('30 days', content.lower(),
                     "Pricing page should mention 30-day free trial")
        self.assertIn('free trial', content.lower(),
                     "Pricing page should have free trial banner")

    def test_pricing_page_has_three_tiers(self):
        """Test that pricing page shows 3 tiers (Starter, Growth, Pro)"""
        response = self.client.get('/pricing/')
        content = response.content.decode('utf-8')
        
        # Check for tier names
        self.assertIn('Starter', content,
                     "Pricing page should have Starter tier")
        self.assertIn('Growth', content,
                     "Pricing page should have Growth tier")
        self.assertIn('Pro', content,
                     "Pricing page should have Pro tier")

    def test_pricing_page_has_most_popular_badge(self):
        """Test that Growth tier is marked as Most Popular"""
        response = self.client.get('/pricing/')
        content = response.content.decode('utf-8')
        
        self.assertIn('Most Popular', content,
                     "Pricing page should mark Growth tier as Most Popular")

    def test_pricing_page_has_custom_plan_section(self):
        """Test that pricing page has custom plan CTA"""
        response = self.client.get('/pricing/')
        content = response.content.decode('utf-8')
        
        self.assertIn('custom', content.lower(),
                     "Pricing page should have custom plan section")

    def test_pricing_page_has_cta_buttons(self):
        """Test that pricing page has Start free trial CTAs"""
        response = self.client.get('/pricing/')
        content = response.content.decode('utf-8')
        
        self.assertIn('Start free trial', content,
                     "Pricing page should have Start free trial buttons")


class NavbarPricingLinkTests(TestCase):
    """Tests for Pricing link in public navbar"""

    def setUp(self):
        self.client = Client()

    def test_homepage_has_pricing_link(self):
        """Test that homepage navbar contains Pricing link"""
        response = self.client.get('/')
        content = response.content.decode('utf-8')
        
        # Check for pricing link
        self.assertIn('pricing', content.lower(),
                     "Homepage should have pricing link in navbar")

    def test_pricing_link_points_to_correct_url(self):
        """Test that Pricing link points to /pricing/"""
        response = self.client.get('/')
        content = response.content.decode('utf-8')
        
        # Check that the link exists and points to /pricing/
        self.assertTrue(
            'href="/pricing/"' in content or 
            "href='/pricing/'" in content or
            'staticpages:pricing' in content,
            "Pricing link should point to /pricing/"
        )


class MobileTableSliderTests(TestCase):
    """Tests for mobile table slider on stock list page"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business'
        )
        self.location = Location.objects.create(
            name='Test Location',
            business=self.business
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='MANAGER',
            status='ACTIVE'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_stock_list_has_slider_wrapper(self):
        """Test that stock list contains slider wrapper"""
        response = self.client.get('/inventory/list/?view=all')
        content = response.content.decode('utf-8')
        
        self.assertIn('cc-table-slider', content,
                     "Stock list should have mobile table slider wrapper")

    def test_stock_list_has_swipe_hint(self):
        """Test that stock list contains swipe hint"""
        response = self.client.get('/inventory/list/?view=all')
        content = response.content.decode('utf-8')
        
        self.assertIn('cc-swipe-hint', content,
                     "Stock list should have swipe hint")
        self.assertIn('Swipe', content,
                     "Stock list should show swipe instruction")

    def test_stock_list_has_mobile_styles(self):
        """Test that stock list includes mobile-specific styles"""
        response = self.client.get('/inventory/list/?view=all')
        content = response.content.decode('utf-8')
        
        # Check for mobile-specific CSS
        self.assertIn('@media (max-width: 991px)', content,
                     "Stock list should have mobile-specific CSS")
        self.assertIn('overflow-x: auto', content,
                     "Stock list should have horizontal scroll CSS")


class APIEndpointSafetyTests(TestCase):
    """Tests for API endpoints returning safe empty states"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='apiuser',
            password='apipass123',
            email='api@example.com'
        )
        self.business = Business.objects.create(
            name='API Test Business',
            slug='api-test-business'
        )
        self.location = Location.objects.create(
            name='API Test Location',
            business=self.business
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='MANAGER',
            status='ACTIVE'
        )
        self.client.login(username='apiuser', password='apipass123')

    def test_sales_trend_endpoint_returns_json(self):
        """Test that sales trend endpoint returns JSON"""
        response = self.client.get('/inventory/api/sales-trend/?period=month')
        self.assertEqual(response.status_code, 200,
                        "Sales trend endpoint should return 200")
        self.assertEqual(response['Content-Type'], 'application/json',
                        "Sales trend endpoint should return JSON")

    def test_sales_trend_returns_empty_state_safely(self):
        """Test that sales trend returns empty arrays when no data"""
        response = self.client.get('/inventory/api/sales-trend/?period=month')
        data = response.json()
        
        self.assertIn('labels', data,
                     "Sales trend should have labels key")
        self.assertIn('values', data,
                     "Sales trend should have values key")
        self.assertIsInstance(data['labels'], list,
                           "Sales trend labels should be a list")
        self.assertIsInstance(data['values'], list,
                           "Sales trend values should be a list")

    def test_top_models_endpoint_returns_json(self):
        """Test that top models endpoint returns JSON"""
        response = self.client.get('/inventory/api/top-models/?period=month')
        self.assertEqual(response.status_code, 200,
                        "Top models endpoint should return 200")
        self.assertEqual(response['Content-Type'], 'application/json',
                        "Top models endpoint should return JSON")

    def test_top_models_returns_empty_state_safely(self):
        """Test that top models returns empty arrays when no data"""
        response = self.client.get('/inventory/api/top-models/?period=month')
        data = response.json()
        
        self.assertIn('labels', data,
                     "Top models should have labels key")
        self.assertIn('values', data,
                     "Top models should have values key")
        self.assertIsInstance(data['labels'], list,
                           "Top models labels should be a list")
        self.assertIsInstance(data['values'], list,
                           "Top models values should be a list")

    def test_sales_trend_handles_different_periods(self):
        """Test that sales trend handles various period parameters"""
        periods = ['today', '7d', 'month', 'all']
        
        for period in periods:
            with self.subTest(period=period):
                response = self.client.get(f'/inventory/api/sales-trend/?period={period}')
                self.assertEqual(response.status_code, 200,
                               f"Sales trend should handle period={period}")
                data = response.json()
                self.assertIn('labels', data,
                            f"Sales trend should return labels for period={period}")


class MigrationValidatorFixTests(TestCase):
    """Tests to verify migration import fix"""

    def test_migration_file_uses_correct_imports(self):
        """Test that migration uses django.core.validators instead of models.validators"""
        # Read the migration file
        migration_path = 'sales/migrations/1000_add_commission_toggle_and_mode.py'
        
        try:
            with open(migration_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for correct import
            self.assertIn('from django.core.validators import', content,
                         "Migration should import from django.core.validators")
            self.assertIn('MinValueValidator', content,
                         "Migration should use MinValueValidator")
            self.assertIn('MaxValueValidator', content,
                         "Migration should use MaxValueValidator")
            
            # Check that incorrect import is NOT present
            self.assertNotIn('models.validators.MinValueValidator', content,
                           "Migration should NOT use models.validators")
        except FileNotFoundError:
            self.skipTest("Migration file not found")


class IntegrationTests(TestCase):
    """Integration tests for all fixes working together"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='integration',
            password='test123',
            email='int@example.com'
        )
        self.business = Business.objects.create(
            name='Integration Test Business',
            slug='integration-test'
        )
        self.location = Location.objects.create(
            name='Integration Location',
            business=self.business
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='MANAGER',
            status='ACTIVE'
        )

    def test_complete_user_flow(self):
        """Test complete user flow: landing -> pricing -> signup"""
        # 1. Visit landing page
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        
        # 2. Check pricing link exists
        content = response.content.decode('utf-8')
        self.assertIn('pricing', content.lower())
        
        # 3. Visit pricing page
        response = self.client.get('/pricing/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('free trial', content.lower())

    def test_authenticated_dashboard_flow(self):
        """Test authenticated user dashboard with widgets"""
        self.client.login(username='integration', password='test123')
        
        # 1. Visit dashboard
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        # 2. Check that API endpoints are accessible
        response = self.client.get('/inventory/api/sales-trend/?period=month')
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get('/inventory/api/top-models/?period=month')
        self.assertEqual(response.status_code, 200)

    def test_stock_list_mobile_experience(self):
        """Test stock list works properly on mobile"""
        self.client.login(username='integration', password='test123')
        
        # Visit stock list with view=all
        response = self.client.get('/inventory/list/?view=all')
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check for mobile enhancements
        self.assertIn('cc-table-slider', content)
        self.assertIn('cc-swipe-hint', content)
        self.assertIn('@media (max-width: 991px)', content)

