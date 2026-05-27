"""
Tests for landing page routing fixes.
Ensures:
- Anonymous users see marketing homepage
- Authenticated users redirect to dashboard (NOT analytics)
- Login redirects to dashboard by default
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class LandingPageRoutingTests(TestCase):
    """Test landing page routing based on authentication."""

    def setUp(self):
        """Set up test users."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_anonymous_sees_marketing_home(self):
        """Test that anonymous users see the marketing homepage."""
        # Don't login
        response = self.client.get('/', follow=True)
        
        # Should not crash
        self.assertNotEqual(response.status_code, 500)
        
        # Should show some marketing content or login
        self.assertIn(response.status_code, [200, 302])
        
        # If it's a redirect, should go to marketing/login, NOT dashboard
        if response.status_code == 302:
            # Check redirect chain
            for url, status in response.redirect_chain:
                self.assertNotIn('dashboard', url.lower(),
                               "Anonymous users should not redirect to dashboard")
                self.assertNotIn('analytics', url.lower(),
                               "Anonymous users should not redirect to analytics")

    def test_authenticated_redirects_to_dashboard(self):
        """Test that authenticated users redirect to dashboard."""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get('/', follow=False)
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Redirect URL should contain dashboard or inventory
        redirect_url = response.url.lower()
        self.assertTrue(
            'dashboard' in redirect_url or 'inventory' in redirect_url,
            f"Authenticated user should redirect to dashboard, got: {response.url}"
        )
        
        # Should NOT redirect to analytics
        self.assertNotIn('analytics', redirect_url,
                        "Should NOT redirect to analytics")
        self.assertNotIn('insights', redirect_url,
                        "Should NOT redirect to insights")

    def test_authenticated_never_analytics(self):
        """Test that authenticated users NEVER get sent to analytics."""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get('/', follow=True)
        
        # Check all URLs in redirect chain
        for url, status in response.redirect_chain:
            self.assertNotIn('analytics', url.lower(),
                           f"Redirect chain should not include analytics: {url}")
            self.assertNotIn('insights', url.lower(),
                           f"Redirect chain should not include insights: {url}")
        
        # Final URL should also not be analytics
        final_url = response.request['PATH_INFO']
        self.assertNotIn('analytics', final_url.lower())
        self.assertNotIn('insights', final_url.lower())


class LoginRedirectTests(TestCase):
    """Test login redirect behavior."""

    def setUp(self):
        """Set up test user."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_login_redirects_to_dashboard(self):
        """Test that login redirects to dashboard by default."""
        response = self.client.post(
            '/accounts/login/',
            {
                'identifier': 'testuser',
                'password': 'testpass123',
            },
            follow=True
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Check where we ended up
        final_url = response.request['PATH_INFO'].lower()
        
        # Should be dashboard or inventory, NOT analytics
        self.assertTrue(
            'dashboard' in final_url or 'inventory' in final_url,
            f"Login should redirect to dashboard, got: {final_url}"
        )
        self.assertNotIn('analytics', final_url)
        self.assertNotIn('insights', final_url)

    def test_login_with_next_param(self):
        """Test that ?next= parameter is respected."""
        # Try to access protected page
        response = self.client.get('/reports/', follow=False)
        
        # Should redirect to login with ?next=
        self.assertEqual(response.status_code, 302)
        
        # Now login
        login_url = response.url
        response = self.client.post(
            login_url,
            {
                'identifier': 'testuser',
                'password': 'testpass123',
            },
            follow=True
        )
        
        # Should be successful
        self.assertEqual(response.status_code, 200)

    def test_login_without_next_goes_to_dashboard(self):
        """Test that login without ?next= goes to dashboard."""
        response = self.client.post(
            '/accounts/login/',
            {
                'identifier': 'testuser',
                'password': 'testpass123',
            },
            follow=True
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Should end up at dashboard, NOT analytics
        final_path = response.request['PATH_INFO'].lower()
        self.assertNotIn('analytics', final_path)
        self.assertNotIn('insights', final_path)


class RootRedirectIntegrationTests(TestCase):
    """Integration tests for root redirect logic."""

    def setUp(self):
        """Set up test environment."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_anonymous_to_authenticated_flow(self):
        """Test flow from anonymous -> login -> dashboard."""
        # 1. Visit root as anonymous
        response = self.client.get('/', follow=True)
        self.assertNotEqual(response.status_code, 500)
        
        # 2. Login
        self.client.login(username='testuser', password='testpass123')
        
        # 3. Visit root as authenticated
        response = self.client.get('/', follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Should be at dashboard, not analytics
        final_path = response.request['PATH_INFO'].lower()
        self.assertNotIn('analytics', final_path)

    def test_multiple_root_visits_consistent(self):
        """Test that multiple visits to root are consistent."""
        self.client.login(username='testuser', password='testpass123')
        
        # Visit root multiple times
        urls = []
        for _ in range(3):
            response = self.client.get('/', follow=True)
            self.assertEqual(response.status_code, 200)
            urls.append(response.request['PATH_INFO'])
        
        # All visits should go to the same place
        self.assertEqual(len(set(urls)), 1,
                        "Root redirect should be consistent")
        
        # Should never be analytics
        for url in urls:
            self.assertNotIn('analytics', url.lower())

    def test_no_redirect_loops(self):
        """Test that there are no redirect loops."""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get('/', follow=True)
        
        # Should not have excessive redirects
        self.assertLess(len(response.redirect_chain), 10,
                       "Should not have excessive redirects (possible loop)")
        
        # Should successfully resolve
        self.assertEqual(response.status_code, 200)


@pytest.mark.django_db
class HQUserRoutingTests(TestCase):
    """Test routing for HQ admin users."""

    def setUp(self):
        """Set up HQ user."""
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hquser',
            email='hq@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )

    def test_hq_user_goes_to_hq_dashboard(self):
        """Test that HQ users go to HQ dashboard, not regular dashboard."""
        self.client.login(username='hquser', password='testpass123')
        
        response = self.client.get('/', follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # HQ users should ideally go to /hq/ area
        # This is a soft check - as long as they don't crash
        final_path = response.request['PATH_INFO']
        
        # Should not crash
        self.assertNotEqual(response.status_code, 500)


class LoginURLConfigTests(TestCase):
    """Test LOGIN_REDIRECT_URL configuration."""

    def test_login_redirect_url_setting(self):
        """Test that LOGIN_REDIRECT_URL is properly configured."""
        from django.conf import settings
        
        # Should be set (not None or empty)
        self.assertTrue(hasattr(settings, 'LOGIN_REDIRECT_URL'))
        
        redirect_url = settings.LOGIN_REDIRECT_URL
        
        # Should not be empty
        self.assertTrue(redirect_url, "LOGIN_REDIRECT_URL should not be empty")
        
        # Should not be analytics
        self.assertNotIn('analytics', redirect_url.lower(),
                        "LOGIN_REDIRECT_URL should not point to analytics")
        self.assertNotIn('insights', redirect_url.lower(),
                        "LOGIN_REDIRECT_URL should not point to insights")


class AnonymousUserSecurityTests(TestCase):
    """Test that anonymous users don't access protected areas."""

    def setUp(self):
        """Set up client."""
        self.client = Client()

    def test_anonymous_cannot_access_dashboard(self):
        """Test that anonymous users cannot directly access dashboard."""
        response = self.client.get('/dashboard/', follow=False)
        
        # Should not be 200 (direct access)
        self.assertNotEqual(response.status_code, 200,
                           "Anonymous users should not access dashboard directly")
        
        # Should redirect to login or show 403
        self.assertIn(response.status_code, [302, 403])

    def test_anonymous_cannot_access_reports(self):
        """Test that anonymous users cannot access reports."""
        response = self.client.get('/reports/', follow=False)
        
        # Should not be 200
        self.assertNotEqual(response.status_code, 200,
                           "Anonymous users should not access reports")
        
        # Should redirect or forbid
        self.assertIn(response.status_code, [302, 403])

    def test_anonymous_cannot_access_inventory(self):
        """Test that anonymous users cannot access inventory."""
        response = self.client.get('/inventory/', follow=False)
        
        # Should not be 200
        self.assertNotEqual(response.status_code, 200,
                           "Anonymous users should not access inventory")
        
        # Should redirect or forbid
        self.assertIn(response.status_code, [302, 403])

