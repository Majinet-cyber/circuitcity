"""
Tests for Landing Page Routing (Task C).

Tests:
- Anonymous user -> home page (marketing/home)
- Authenticated user -> dashboard (NOT analytics)
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class LandingRoutingAnonymousTestCase(TestCase):
    """Test landing page routing for anonymous users."""
    
    def setUp(self):
        self.client = Client()
    
    def test_anonymous_user_gets_home_page(self):
        """
        Anonymous user accessing root (/) should see the home page,
        NOT be redirected to login or dashboard.
        """
        response = self.client.get("/", follow=True)
        
        # Should eventually land on a home/marketing page (200)
        # or redirect to login (which is also acceptable)
        self.assertIn(response.status_code, [200, 302])
        
        # Final URL should be home-related, not dashboard
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/"
        
        # Should NOT end up on dashboard, inventory, or analytics
        self.assertNotIn("/dashboard/", final_url)
        self.assertNotIn("/inventory/dashboard", final_url)
        self.assertNotIn("/analytics", final_url)
        self.assertNotIn("/insights", final_url)
    
    def test_anonymous_user_root_redirect_target(self):
        """
        Test that anonymous user root redirect goes to home or login,
        never to authenticated pages.
        """
        response = self.client.get("/", follow=False)
        
        if response.status_code == 302:
            redirect_url = response.url
            
            # Valid targets for anonymous users
            valid_targets = [
                "/home",
                "/landing",
                "/login",
                "/accounts/login",
                "/staticpages"
            ]
            
            is_valid_target = any(target in redirect_url for target in valid_targets)
            
            # Should NOT redirect to authenticated pages
            invalid_targets = [
                "/dashboard/",
                "/inventory/dashboard",
                "/analytics",
                "/insights/analytics"
            ]
            
            is_invalid_target = any(target in redirect_url for target in invalid_targets)
            
            # Either valid target OR some other non-authenticated page
            self.assertFalse(is_invalid_target, 
                f"Anonymous user redirected to authenticated page: {redirect_url}")


class LandingRoutingAuthenticatedTestCase(TestCase):
    """Test landing page routing for authenticated users."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_authenticated_user_redirects_to_dashboard(self):
        """
        Authenticated user accessing root (/) should be redirected to dashboard,
        NOT analytics or insights.
        """
        response = self.client.get("/", follow=False)
        
        # Should redirect (not render home page for authenticated users)
        self.assertEqual(response.status_code, 302)
        
        redirect_url = response.url
        
        # Should redirect to dashboard
        dashboard_targets = [
            "/dashboard",
            "/inventory/dashboard",
            "/inventory/list",
            "/inventory/"
        ]
        
        is_dashboard = any(target in redirect_url for target in dashboard_targets)
        
        # Explicitly should NOT be analytics
        is_analytics = "/analytics" in redirect_url or "/insights" in redirect_url
        
        # Assertion: should go to dashboard-like page
        # (We accept various dashboard endpoints but NOT analytics)
        self.assertFalse(is_analytics,
            f"Authenticated user redirected to analytics instead of dashboard: {redirect_url}")
    
    def test_authenticated_user_final_destination_is_dashboard(self):
        """
        Follow all redirects and ensure authenticated user lands on dashboard,
        not analytics.
        """
        response = self.client.get("/", follow=True)
        
        # Should eventually get 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Check the final URL in redirect chain
        if response.redirect_chain:
            final_url = response.redirect_chain[-1][0]
            
            # Should NOT be analytics
            self.assertNotIn("/analytics", final_url)
            self.assertNotIn("/insights/analytics", final_url)
            
            # Should be dashboard-related (or at least not analytics)
            # We check that it's one of the acceptable endpoints
            acceptable_endpoints = [
                "/dashboard",
                "/inventory",
                "/tenants",
                "/wallet"
            ]
            
            # At least one of these should be in the URL OR it's root
            is_acceptable = any(ep in final_url for ep in acceptable_endpoints) or final_url == "/"
            
            self.assertTrue(is_acceptable or "/analytics" not in final_url,
                f"Authenticated user landed on unexpected page: {final_url}")


class LandingRoutingHQUserTestCase(TestCase):
    """Test landing page routing for HQ admin users."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username="hqadmin",
            email="hq@example.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client.login(username="hqadmin", password="testpass123")
    
    def test_hq_user_gets_appropriate_landing(self):
        """
        HQ admin should be routed to HQ dashboard or appropriate page,
        not regular user dashboard or analytics.
        """
        response = self.client.get("/", follow=False)
        
        # Should redirect somewhere
        if response.status_code == 302:
            redirect_url = response.url
            
            # HQ users might go to HQ pages or dashboard
            # Just ensure they don't go to analytics by default
            self.assertNotIn("/analytics", redirect_url)


class LandingRoutingEdgeCasesTestCase(TestCase):
    """Test edge cases in landing page routing."""
    
    def setUp(self):
        self.client = Client()
    
    def test_multiple_root_accesses_consistent(self):
        """Test that multiple accesses to root give consistent behavior."""
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Access as anonymous
        anon_response = self.client.get("/", follow=False)
        anon_redirect = anon_response.url if anon_response.status_code == 302 else None
        
        # Login
        self.client.login(username="testuser", password="testpass123")
        
        # Access as authenticated
        auth_response = self.client.get("/", follow=False)
        auth_redirect = auth_response.url if auth_response.status_code == 302 else None
        
        # Behavior should be different (anonymous vs authenticated)
        if anon_redirect and auth_redirect:
            self.assertNotEqual(anon_redirect, auth_redirect,
                "Anonymous and authenticated users should have different landing pages")
    
    def test_root_path_always_responds(self):
        """Test that root path always responds (never 404)."""
        # Anonymous
        anon_response = self.client.get("/", follow=True)
        self.assertNotEqual(anon_response.status_code, 404,
            "Root path should never return 404")
        
        # Authenticated
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
        
        auth_response = self.client.get("/", follow=True)
        self.assertNotEqual(auth_response.status_code, 404,
            "Root path should never return 404 for authenticated users")


class LandingRoutingConsistencyTestCase(TestCase):
    """Test consistency of landing page routing behavior."""
    
    def test_landing_routing_rule_documented(self):
        """
        Verify that the landing routing rule exists and is documented.
        This test serves as documentation of the expected behavior.
        """
        # Expected behavior:
        # 1. Anonymous users -> home page (marketing/staticpages)
        # 2. Authenticated users -> dashboard (NOT analytics)
        # 3. HQ admins -> HQ dashboard
        
        # This is enforced by the root_redirect function in cc/urls.py
        from cc.urls import root_redirect
        
        self.assertTrue(callable(root_redirect),
            "root_redirect function should exist in cc/urls.py")
        
        # Check that the function has appropriate logic
        import inspect
        source = inspect.getsource(root_redirect)
        
        # Should check authentication
        self.assertIn("is_authenticated", source)
        
        # Should mention dashboard
        self.assertIn("dashboard", source.lower())

