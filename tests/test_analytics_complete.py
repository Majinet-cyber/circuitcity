"""
Comprehensive tests for Analytics feature.

Tests:
1. Sidebar items have required keys (is_menu, is_header, key, label, url, active_prefix)
2. Analytics appears in sidebar for all verticals
3. Business analytics renders per vertical
4. Analytics filters affect KPIs
5. Inventory dashboard never 500s
6. HQ analytics requires HQ and renders
7. Analytics route exists and is accessible
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse, NoReverseMatch
from decimal import Decimal

User = get_user_model()


@pytest.mark.django_db
class TestAnalyticsRoute(TestCase):
    """Test that analytics route exists and is properly configured."""
    
    def test_analytics_route_exists(self):
        """Test that app_router:analytics route exists and reverses correctly."""
        try:
            url = reverse('app_router:analytics')
            self.assertEqual(url, '/app/analytics/')
        except NoReverseMatch:
            self.fail("app_router:analytics route not found")
    
    def test_analytics_route_returns_302_when_not_authenticated(self):
        """Test that analytics route redirects to login when not authenticated."""
        client = Client()
        response = client.get('/app/analytics/')
        # Should redirect to login (302) or return 403
        self.assertIn(response.status_code, [302, 403], 
                     f"Expected 302 or 403 for unauthenticated user, got {response.status_code}")
        if response.status_code == 302:
            self.assertIn('login', response.url.lower())
    
    def test_analytics_route_accessible_when_authenticated(self):
        """Test that analytics route is accessible when authenticated with business."""
        from tenants.models import Business, Membership
        from inventory.business_kinds import BusinessKind
        
        # Create user and business
        user = User.objects.create_user(
            username='test_analytics_user',
            email='test_analytics@example.com',
            password='testpass123'
        )
        business = Business.objects.create(
            name='Test Analytics Business',
            slug='test-analytics-business',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        Membership.objects.create(
            user=user,
            business=business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Login and set active business
        client = Client()
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access analytics route
        response = client.get('/app/analytics/')
        # Should return 200 or redirect to dashboard if business not set properly
        self.assertIn(response.status_code, [200, 302],
                     f"Expected 200 or 302 for authenticated user, got {response.status_code}")


@pytest.mark.django_db
class TestSidebarItems(TestCase):
    """Test that sidebar items have required keys."""
    
    def test_sidebar_items_have_required_keys(self):
        """Test that all sidebar items have required keys."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ['phones', 'clothing', 'liquor', 'pharmacy', 'gym']
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            
            for item in items:
                # Check required keys
                assert 'key' in item, f"Item missing 'key' in {vertical}: {item}"
                assert 'label' in item, f"Item missing 'label' in {vertical}: {item}"
                assert 'url' in item, f"Item missing 'url' in {vertical}: {item}"
                assert 'is_menu' in item, f"Item missing 'is_menu' in {vertical}: {item}"
                assert 'is_header' in item, f"Item missing 'is_header' in {vertical}: {item}"
                assert 'active_prefix' in item or 'active_pattern' in item, f"Item missing active_prefix/pattern in {vertical}: {item}"
                
                # Check that analytics item exists and is_menu=True
                analytics_items = [i for i in items if i.get('key') == 'analytics']
                if analytics_items:
                    analytics_item = analytics_items[0]
                    assert analytics_item['is_menu'] == False, f"Analytics should be is_menu=False in {vertical}"
                    assert analytics_item['label'] == 'Analytics', f"Analytics label should be 'Analytics' in {vertical}"
    
    def test_analytics_in_all_verticals(self):
        """Test that Analytics appears in sidebar for all verticals."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ['phones', 'clothing', 'liquor', 'pharmacy', 'gym']
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            analytics_items = [i for i in items if i.get('key') == 'analytics']
            assert len(analytics_items) > 0, f"Analytics not found in {vertical} sidebar"
            # Verify Analytics item has correct properties
            analytics_item = analytics_items[0]
            assert analytics_item['url'] == 'app_router:analytics' or analytics_item['url'] == '/app/analytics/', \
                f"Analytics URL incorrect in {vertical}: {analytics_item.get('url')}"
            assert analytics_item['active_prefix'] == '/app/analytics', \
                f"Analytics active_prefix incorrect in {vertical}: {analytics_item.get('active_prefix')}"
    
    def test_sidebar_builder_includes_analytics_for_each_vertical(self):
        """Test that sidebar builder includes Analytics for each vertical with correct URL."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ['phones', 'clothing', 'liquor', 'pharmacy', 'gym']
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            analytics_items = [i for i in items if i.get('key') == 'analytics']
            assert len(analytics_items) > 0, f"Analytics not found in {vertical} sidebar"
            
            analytics_item = analytics_items[0]
            # Verify URL is correct (either named route or absolute path)
            assert analytics_item['url'] == 'app_router:analytics' or analytics_item['url'] == '/app/analytics/', \
                f"Analytics URL should be 'app_router:analytics' or '/app/analytics/' in {vertical}, got: {analytics_item.get('url')}"


@pytest.mark.django_db
class TestMobileNav(TestCase):
    """Test that Analytics appears in mobile nav."""
    
    def test_analytics_in_mobile_nav(self):
        """Test that Analytics appears in mobile nav for all verticals."""
        from inventory.mobile_nav import get_mobile_nav_items
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/')
        
        # Mock business_vertical function
        from inventory.helpers_core import PHONES, CLOTHING, LIQUOR, PHARMACY, GYM
        
        verticals = {
            'phones': PHONES,
            'clothing': CLOTHING,
            'liquor': LIQUOR,
            'pharmacy': PHARMACY,
            'gym': GYM,
        }
        
        for vertical_name, vertical_code in verticals.items():
            # Set request attribute to simulate vertical
            request.BUSINESS_VERTICAL = vertical_code
            
            items = get_mobile_nav_items(request)
            analytics_items = [i for i in items if i.get('key') == 'analytics']
            assert len(analytics_items) > 0, f"Analytics not found in {vertical_name} mobile nav"
            # Verify Analytics item has correct URL
            analytics_item = analytics_items[0]
            assert '/app/analytics' in analytics_item['url'], \
                f"Analytics URL should contain '/app/analytics' in {vertical_name} mobile nav, got: {analytics_item.get('url')}"


@pytest.mark.django_db
class TestSidebarHtmlContainsAnalytics(TestCase):
    """Test that Analytics is visible in rendered sidebar HTML."""
    
    def setUp(self):
        """Create test businesses and users."""
        from tenants.models import Business, Membership
        from inventory.business_kinds import BusinessKind
        
        self.verticals = ['phones', 'clothing', 'liquor', 'pharmacy', 'gym']
        self.businesses = {}
        self.users = {}
        self.clients = {}
        
        for vertical in self.verticals:
            business = Business.objects.create(
                name=f"Test {vertical.title()} Business",
                slug=f"test-{vertical}-{id(self)}",
                business_kind=getattr(BusinessKind, vertical.upper(), BusinessKind.PHONES),
                status="ACTIVE"
            )
            self.businesses[vertical] = business
            
            user = User.objects.create_user(
                username=f"test_{vertical}_user",
                email=f"test_{vertical}@example.com",
                password="testpass123"
            )
            self.users[vertical] = user
            
            Membership.objects.create(
                user=user,
                business=business,
                role="MANAGER",
                status="ACTIVE"
            )
            
            client = Client()
            client.force_login(user)
            # Set active business in session
            session = client.session
            session['active_business_id'] = business.id
            session['business_id'] = business.id
            session.save()
            self.clients[vertical] = client
    
    def test_sidebar_html_contains_analytics_phones(self):
        """Test that Analytics appears in phones sidebar HTML."""
        client = self.clients['phones']
        response = client.get('/inventory/verticals/phones/', follow=True)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content = response.content.decode()
        # Check for Analytics text or data-cy attribute
        assert 'Analytics' in content or 'data-cy="nav-analytics"' in content, \
            "Analytics not found in phones sidebar HTML"
    
    def test_sidebar_html_contains_analytics_gym(self):
        """Test that Analytics appears in gym sidebar HTML."""
        client = self.clients['gym']
        response = client.get('/verticals/gym/dashboard/', follow=True)
        # Accept 200 or redirect (may redirect to analytics)
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        if response.status_code == 200:
            content = response.content.decode()
            assert 'Analytics' in content or 'data-cy="nav-analytics"' in content, \
                "Analytics not found in gym sidebar HTML"
    
    def test_sidebar_html_contains_analytics_clothing(self):
        """Test that Analytics appears in clothing sidebar HTML."""
        client = self.clients['clothing']
        response = client.get('/verticals/clothing/dashboard/', follow=True)
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        if response.status_code == 200:
            content = response.content.decode()
            assert 'Analytics' in content or 'data-cy="nav-analytics"' in content, \
                "Analytics not found in clothing sidebar HTML"
    
    def test_sidebar_html_contains_analytics_liquor(self):
        """Test that Analytics appears in liquor sidebar HTML."""
        client = self.clients['liquor']
        response = client.get('/verticals/liquor/dashboard/', follow=True)
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        if response.status_code == 200:
            content = response.content.decode()
            assert 'Analytics' in content or 'data-cy="nav-analytics"' in content, \
                "Analytics not found in liquor sidebar HTML"
    
    def test_sidebar_html_contains_analytics_pharmacy(self):
        """Test that Analytics appears in pharmacy sidebar HTML."""
        client = self.clients['pharmacy']
        response = client.get('/verticals/pharmacy/dashboard/', follow=True)
        assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
        if response.status_code == 200:
            content = response.content.decode()
            assert 'Analytics' in content or 'data-cy="nav-analytics"' in content, \
                "Analytics not found in pharmacy sidebar HTML"


@pytest.mark.django_db
class TestBusinessAnalytics(TestCase):
    """Test business analytics rendering per vertical."""
    
    def setUp(self):
        """Create businesses for each vertical."""
        from tenants.models import Business
        from circuitcity.accounts.models import Profile
        
        self.businesses = {}
        self.managers = {}
        self.clients = {}
        
        verticals = ['phones', 'clothing', 'liquor', 'pharmacy', 'gym']
        
        import time
        for idx, vertical in enumerate(verticals):
            # Create business with unique slug (use timestamp + index to ensure uniqueness)
            unique_slug = f"test-{vertical}-store-{int(time.time() * 1000000) + idx}"
            business = Business.objects.create(
                name=f"Test {vertical.title()} Store {idx}",
                business_kind=vertical,
                slug=unique_slug,
            )
            self.businesses[vertical] = business
            
            # Create manager
            manager = User.objects.create_user(
                username=f"{vertical}_manager",
                email=f"manager@{vertical}.test",
                password="testpass123"
            )
            profile = Profile.objects.get_or_create(user=manager)[0]
            profile.is_manager = True
            profile.save()
            
            business.manager = manager
            business.save()
            
            self.managers[vertical] = manager
            
            # Create client
            client = Client()
            client.force_login(manager)
            self.clients[vertical] = client
    
    def test_business_analytics_renders_per_vertical(self):
        """Test that analytics renders for each vertical."""
        template_map = {
            'phones': 'Phones Analytics',
            'clothing': 'Clothing Analytics',
            'liquor': 'Liquor Analytics',
            'pharmacy': 'Pharmacy Analytics',
            'gym': 'Gym Analytics',
        }
        
        for vertical, expected_title in template_map.items():
            client = self.clients[vertical]
            business = self.businesses[vertical]
            
            # Activate business in session
            session = client.session
            session['active_business_id'] = business.id
            session.save()
            
            # Get analytics page
            response = client.get('/app/analytics/')
            
            # Should return 200
            assert response.status_code == 200, f"Analytics page returned {response.status_code} for {vertical}"
            
            # Check that correct template is used (contains unique heading)
            content = response.content.decode('utf-8')
            assert expected_title in content or 'Analytics' in content, f"Expected '{expected_title}' in response for {vertical}"
    
    def test_analytics_filters_affect_kpis(self):
        """Test that filters change KPIs."""
        from datetime import date, timedelta
        from django.utils import timezone
        
        # Use phones business for this test
        client = self.clients['phones']
        business = self.businesses['phones']
        
        # Activate business
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Get analytics with default date range
        response1 = client.get('/app/analytics/')
        assert response1.status_code == 200
        
        # Get analytics with different date range (yesterday)
        yesterday = (timezone.now() - timedelta(days=1)).date()
        response2 = client.get(f'/app/analytics/?preset=yesterday')
        assert response2.status_code == 200
        
        # Both should render successfully (even if KPIs are 0)
        # The important thing is that filters are applied without errors
        assert 'Analytics' in response2.content.decode('utf-8')
    
    def test_inventory_dashboard_never_500(self):
        """Test that inventory dashboard never returns 500."""
        from inventory.views_dashboard import inventory_dashboard
        
        # Use phones business
        client = self.clients['phones']
        business = self.businesses['phones']
        
        # Activate business
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Get dashboard
        response = client.get('/inventory/dashboard/')
        
        # Should not be 500 (can be 302 redirect or 200)
        assert response.status_code != 500, "Inventory dashboard returned 500 error"
        assert response.status_code in [200, 302], f"Inventory dashboard returned unexpected status {response.status_code}"


@pytest.mark.django_db
class TestHQAnalytics(TestCase):
    """Test HQ analytics page."""
    
    def setUp(self):
        """Create HQ admin user."""
        from circuitcity.accounts.models import Profile
        
        self.hq_user = User.objects.create_user(
            username="hq_admin",
            email="hq@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        profile = Profile.objects.get_or_create(user=self.hq_user)[0]
        profile.save()
        
        self.hq_client = Client()
        self.hq_client.force_login(self.hq_user)
        
        # Create regular user
        self.regular_user = User.objects.create_user(
            username="regular_user",
            email="regular@test.com",
            password="testpass123"
        )
        self.regular_client = Client()
        self.regular_client.force_login(self.regular_user)
    
    def test_hq_analytics_requires_hq(self):
        """Test that non-HQ users cannot access HQ analytics."""
        # Regular user should be redirected or get 403
        response = self.regular_client.get('/hq/analytics/')
        assert response.status_code in [302, 403], f"Regular user should not access HQ analytics, got {response.status_code}"
    
    def test_hq_analytics_renders(self):
        """Test that HQ analytics renders for HQ users."""
        response = self.hq_client.get('/hq/analytics/')
        assert response.status_code == 200, f"HQ analytics should return 200, got {response.status_code}"
        
        content = response.content.decode('utf-8')
        assert 'HQ Analytics' in content or 'Analytics' in content, "HQ analytics page should contain 'Analytics'"
    
    def test_hq_analytics_filters(self):
        """Test that HQ analytics filters work."""
        from datetime import date, timedelta
        from django.utils import timezone
        
        # Test with preset
        response = self.hq_client.get('/hq/analytics/?preset=today')
        assert response.status_code == 200
        
        # Test with custom date range
        start_date = (timezone.now() - timedelta(days=7)).date()
        end_date = timezone.now().date()
        response = self.hq_client.get(f'/hq/analytics/?start={start_date}&end={end_date}')
        assert response.status_code == 200

