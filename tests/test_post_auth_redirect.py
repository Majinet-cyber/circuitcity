"""
Unit tests for post_auth_redirect service.

Tests the centralized redirect logic after login/signup.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from circuitcity.accounts.services.post_auth_redirect import (
    get_post_login_redirect,
    get_post_signup_redirect,
    get_vertical_home_url,
    get_vertical_urls_for_nav,
)

User = get_user_model()


class PostAuthRedirectTestCase(TestCase):
    """Test post-authentication redirect logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_get_post_login_redirect_no_business(self):
        """Test redirect when user has no business."""
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        
        url = get_post_login_redirect(self.user, request)
        
        # Should redirect to default dashboard
        assert url in ['/dashboard/', reverse('dashboard:home'), reverse('inventory:inventory_dashboard')]

    def test_get_post_signup_redirect_no_business(self):
        """Test redirect when new user has no business."""
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        
        url = get_post_signup_redirect(self.user, request)
        
        # Should redirect to default dashboard
        assert url in ['/dashboard/', reverse('dashboard:home'), reverse('inventory:inventory_dashboard')]

    def test_get_vertical_home_url_phones(self):
        """Test getting phones dashboard URL."""
        url = get_vertical_home_url('phones')
        
        # Should return phones dashboard URL
        assert '/inventory' in url or 'phone' in url

    def test_get_vertical_home_url_clothing(self):
        """Test getting clothing dashboard URL."""
        url = get_vertical_home_url('clothing')
        
        # Should return clothing dashboard URL
        assert 'clothing' in url

    def test_get_vertical_home_url_gym(self):
        """Test getting gym dashboard URL."""
        url = get_vertical_home_url('gym')
        
        # Should return gym dashboard URL
        assert 'gym' in url

    def test_get_vertical_home_url_cement(self):
        """Test getting cement/hardware dashboard URL."""
        url = get_vertical_home_url('cement')
        
        # Should return cement dashboard URL
        assert 'cement' in url or 'dashboard' in url

    def test_get_vertical_urls_for_nav_phones(self):
        """Test getting all nav URLs for phones."""
        urls = get_vertical_urls_for_nav('phones')
        
        assert 'home' in urls
        assert 'scan' in urls
        assert 'sell' in urls
        assert 'stock' in urls
        
        # All URLs should be valid (not #)
        assert urls['home'] != '#'

    def test_get_vertical_urls_for_nav_clothing(self):
        """Test getting all nav URLs for clothing."""
        urls = get_vertical_urls_for_nav('clothing')
        
        assert 'home' in urls
        assert 'scan' in urls
        assert 'sell' in urls
        
        # All URLs should be valid (not #)
        assert urls['home'] != '#'

    def test_get_vertical_urls_for_nav_gym(self):
        """Test getting all nav URLs for gym."""
        urls = get_vertical_urls_for_nav('gym')
        
        assert 'home' in urls
        assert 'members' in urls
        assert 'payment' in urls
        
        # All URLs should be valid (not #)
        assert urls['home'] != '#'

    def test_get_vertical_urls_for_nav_cement(self):
        """Test getting all nav URLs for cement/hardware."""
        urls = get_vertical_urls_for_nav('cement')
        
        assert 'home' in urls
        assert 'sell' in urls
        assert 'products' in urls
        
        # All URLs should be valid (not #)
        assert urls['home'] != '#'

    def test_redirect_never_goes_to_analytics(self):
        """CRITICAL: Ensure redirects NEVER go to analytics."""
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        
        login_url = get_post_login_redirect(self.user, request)
        signup_url = get_post_signup_redirect(self.user, request)
        
        # Neither should contain 'analytics' or 'insights'
        assert 'analytics' not in login_url.lower()
        assert 'insights' not in login_url.lower()
        assert 'analytics' not in signup_url.lower()
        assert 'insights' not in signup_url.lower()

    def test_redirect_always_goes_to_dashboard(self):
        """CRITICAL: Ensure redirects always go to dashboard."""
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        
        login_url = get_post_login_redirect(self.user, request)
        signup_url = get_post_signup_redirect(self.user, request)
        
        # Both should contain 'dashboard' or be a known dashboard route
        valid_dashboard_keywords = ['dashboard', 'inventory', 'gym', 'clothing', 'cement']
        
        assert any(keyword in login_url.lower() for keyword in valid_dashboard_keywords)
        assert any(keyword in signup_url.lower() for keyword in valid_dashboard_keywords)

    def test_get_vertical_home_url_unknown_vertical(self):
        """Test handling of unknown/invalid vertical."""
        url = get_vertical_home_url('unknown_vertical_xyz')
        
        # Should return a safe fallback
        assert url.startswith('/')
        assert url != '#'

    def test_get_vertical_urls_for_nav_unknown_vertical(self):
        """Test handling of unknown/invalid vertical for nav."""
        urls = get_vertical_urls_for_nav('unknown_vertical_xyz')
        
        # Should return a dict with at least 'home'
        assert isinstance(urls, dict)
        assert 'home' in urls


@pytest.mark.django_db
class PostAuthRedirectIntegrationTestCase:
    """Integration tests with actual database."""

    def test_post_login_redirect_with_phones_business(self, django_user_model):
        """Test redirect for user with phones business."""
        from tenants.models import Business, Membership
        
        user = django_user_model.objects.create_user(
            username='phoneuser',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name='Test Phones Shop',
            business_kind='phones'
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            status='ACTIVE'
        )
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        request.session = {'active_business_id': business.id}
        request.business = business
        
        url = get_post_login_redirect(user, request)
        
        # Should redirect to phones dashboard
        assert 'phone' in url.lower() or 'inventory' in url.lower()
        assert 'analytics' not in url.lower()

    def test_post_signup_redirect_with_clothing_business(self, django_user_model):
        """Test redirect for new user with clothing business."""
        from tenants.models import Business, Membership
        
        user = django_user_model.objects.create_user(
            username='clothinguser',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name='Test Clothing Store',
            business_kind='clothing'
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            status='ACTIVE'
        )
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        request.session = {'active_business_id': business.id}
        request.business = business
        
        url = get_post_signup_redirect(user, request, business)
        
        # Should redirect to clothing dashboard
        assert 'clothing' in url.lower()
        assert 'analytics' not in url.lower()

    def test_post_login_redirect_with_gym_business(self, django_user_model):
        """Test redirect for user with gym business."""
        from tenants.models import Business, Membership
        
        user = django_user_model.objects.create_user(
            username='gymuser',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name='Test Gym',
            business_kind='gym'
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            status='ACTIVE'
        )
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        request.session = {'active_business_id': business.id}
        request.business = business
        
        url = get_post_login_redirect(user, request)
        
        # Should redirect to gym dashboard
        assert 'gym' in url.lower()
        assert 'analytics' not in url.lower()

    def test_post_signup_redirect_with_cement_business(self, django_user_model):
        """Test redirect for new user with cement/hardware business."""
        from tenants.models import Business, Membership
        
        user = django_user_model.objects.create_user(
            username='cementuser',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name='Test Hardware Store',
            business_kind='cement'
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            status='ACTIVE'
        )
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        request.session = {'active_business_id': business.id}
        request.business = business
        
        url = get_post_signup_redirect(user, request, business)
        
        # Should redirect to cement dashboard
        assert 'cement' in url.lower() or 'dashboard' in url.lower()
        assert 'analytics' not in url.lower()

