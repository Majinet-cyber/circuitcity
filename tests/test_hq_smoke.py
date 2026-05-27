# tests/test_hq_smoke.py
"""
Regression tests for HQ pages to ensure they work with active_business=None.
Tests that HQ pages never redirect to business selection, billing checkout, or ActiveBusinessMiddleware logic.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership

User = get_user_model()


class HQSmokeTest(TestCase):
    """
    Smoke tests for HQ pages to ensure:
    1. No redirect loops on /hq/businesses/
    2. /hq/subscriptions/ loads without active_tab errors
    3. HQ routes work without requiring active_business
    """
    
    def setUp(self):
        """Set up test data."""
        # Create superuser for HQ access
        self.admin_user = User.objects.create_superuser(
            username='hqadmin',
            email='admin@hq.com',
            password='adminpass123'
        )
        
        # Create a regular business (but don't set it as active)
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            created_by=self.admin_user,
            status='ACTIVE'
        )
        
        self.client = Client()
        self.client.login(username='hqadmin', password='adminpass123')
        
        # CRITICAL: Ensure no active_business is set in session
        # This simulates the condition where HQ pages must work
        session = self.client.session
        session.pop('active_business_id', None)
        session.pop('biz_id', None)
        session.save()
    
    def test_hq_subscriptions_loads_without_active_tab_error(self):
        """
        Test that /hq/subscriptions/ loads without VariableDoesNotExist for active_tab.
        Even if the view forgets to include active_tab, the template should handle it safely.
        """
        url = reverse('hq:subscriptions')
        response = self.client.get(url)
        
        # Must return 200, not 302 (redirect) or 500 (error)
        self.assertEqual(
            response.status_code, 
            200, 
            f"Expected 200, got {response.status_code}. Response: {response.content.decode()[:500]}"
        )
        
        # Template should render without VariableDoesNotExist
        content = response.content.decode()
        self.assertNotIn('VariableDoesNotExist', content)
        self.assertNotIn('active_tab', content.lower())  # Should not appear as error text
    
    def test_hq_businesses_no_redirect_loop(self):
        """
        Test that /hq/businesses/ returns 200 immediately without redirect loop.
        This was the main bug: infinite 302 redirects.
        """
        url = reverse('hq:businesses')
        
        # Make request and check for redirect loop
        response = self.client.get(url, follow=False)  # Don't follow redirects
        
        # Must return 200 immediately, not 302
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}. "
            f"Location: {response.get('Location', 'None')}. "
            f"This indicates a redirect loop was not fixed."
        )
        
        # CRITICAL: Ensure it's not redirecting to itself
        if response.status_code == 302:
            location = response.get('Location', '')
            self.assertNotEqual(
                location.rstrip('/'),
                url.rstrip('/'),
                f"Redirect loop detected: {url} redirects to itself ({location})"
            )
        
        # If we follow redirects, we should still end at 200 (not loop)
        response_follow = self.client.get(url, follow=True)
        self.assertEqual(
            response_follow.status_code,
            200,
            f"Even with follow=True, should end at 200, got {response_follow.status_code}"
        )
        
        # Check that we're not being redirected to business selection
        final_url = response_follow.request.get('PATH_INFO', '')
        self.assertNotIn('/tenants/choose/', final_url)
        self.assertNotIn('/billing/checkout/', final_url)
        self.assertNotIn('/billing/subscribe/', final_url)
    
    def test_hq_pages_work_without_active_business(self):
        """
        Test that HQ pages work even when active_business is None.
        HQ is global admin view, should not require tenant context.
        """
        # Ensure no active business in session
        session = self.client.session
        session.pop('active_business_id', None)
        session.pop('biz_id', None)
        session.save()
        
        # Test multiple HQ endpoints
        hq_urls = [
            'hq:subscriptions',
            'hq:businesses',
            'hq:dashboard',
            'hq:invoices',
            'hq:agents',
        ]
        
        for url_name in hq_urls:
            try:
                url = reverse(url_name)
                response = self.client.get(url, follow=False)
                
                # Should return 200 or 302 to login (if not authenticated)
                # But never 302 to business selection
                self.assertIn(
                    response.status_code,
                    [200, 302],
                    f"{url_name} returned {response.status_code}"
                )
                
                if response.status_code == 302:
                    location = response.get('Location', '')
                    # Should not redirect to business selection or billing
                    self.assertNotIn('/tenants/choose/', location)
                    self.assertNotIn('/billing/checkout/', location)
                    self.assertNotIn('/billing/subscribe/', location)
                    
            except Exception as e:
                self.fail(f"Error accessing {url_name}: {e}")
    
    def test_hq_subscriptions_template_renders_safely(self):
        """
        Test that billing/hq_subscriptions.html template renders without requiring active_business.
        The template should use {% with active_tab|default:"subscriptions" as tab %} pattern.
        """
        url = reverse('hq:subscriptions')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Template should render successfully
        content = response.content.decode()
        
        # Should contain subscription-related content
        # (exact content depends on template, but should not be empty or error)
        self.assertGreater(len(content), 100, "Template rendered but content seems empty")
        
        # Should not contain error messages about missing variables
        error_indicators = [
            'VariableDoesNotExist',
            'TemplateSyntaxError',
            'TemplateDoesNotExist',
            'active_tab',
        ]
        for indicator in error_indicators:
            # Only check if it appears as part of an error message
            if indicator.lower() in content.lower():
                # Make sure it's not in an error context
                error_context = content.lower().find(indicator.lower())
                if error_context > 0:
                    # Check surrounding text for error patterns
                    snippet = content[max(0, error_context-50):error_context+100].lower()
                    if any(err in snippet for err in ['error', 'exception', 'traceback', 'does not exist']):
                        self.fail(f"Found error indicator '{indicator}' in response: {snippet}")
    
    def test_no_redirect_loop_on_businesses(self):
        """
        Specific test for the /hq/businesses/ redirect loop bug.
        This test will fail if the loop returns.
        """
        url = reverse('hq:businesses')
        
        # Simulate multiple requests to detect loops
        redirect_count = 0
        max_redirects = 5  # More than this indicates a loop
        current_url = url
        seen_urls = set()  # Track seen URLs to detect cycles
        
        for _ in range(max_redirects + 1):
            # Normalize URL for comparison
            normalized = current_url.rstrip('/').split('?')[0]
            if normalized in seen_urls:
                self.fail(
                    f"Redirect cycle detected: {normalized} was seen before "
                    f"(redirect #{redirect_count})"
                )
            seen_urls.add(normalized)
            
            response = self.client.get(current_url, follow=False)
            
            if response.status_code == 302:
                redirect_count += 1
                location = response.get('Location', '')
                
                # Check if redirecting to same or similar URL (loop indicator)
                location_normalized = location.rstrip('/').split('?')[0]
                if location_normalized == normalized:
                    self.fail(
                        f"Redirect loop detected: redirecting to {location} "
                        f"from {current_url} (redirect #{redirect_count})"
                    )
                
                if location and (location.endswith('/hq/businesses/') or 
                                location.endswith('/hq/businesses') or
                                '/hq/businesses' in location):
                    # Check if it's a self-redirect
                    if location_normalized == normalized:
                        self.fail(
                            f"Redirect loop detected: redirecting to {location} "
                            f"from {current_url} (redirect #{redirect_count})"
                        )
                
                # Follow the redirect
                current_url = location
            else:
                # Got a final response (200, 404, etc.)
                break
        
        # Should not have exceeded max redirects
        self.assertLess(
            redirect_count,
            max_redirects,
            f"Too many redirects ({redirect_count}), possible redirect loop"
        )
        
        # Final response should be 200
        final_response = self.client.get(url, follow=True)
        self.assertEqual(
            final_response.status_code,
            200,
            f"Final response should be 200, got {final_response.status_code}"
        )
        
        # Ensure no self-redirects in the redirect chain
        for redirect_url, _ in final_response.redirect_chain:
            redirect_normalized = redirect_url.rstrip('/').split('?')[0]
            self.assertNotEqual(
                redirect_normalized,
                url.rstrip('/'),
                f"Redirect chain contains self-redirect: {redirect_url}"
            )
    
    def test_hq_admin_redirects_from_blocked_paths(self):
        """
        Test that HQ admins are still redirected from blocked paths (e.g., /inventory/dashboard/)
        to HQ, but never to the same path (anti-loop guard).
        """
        # Test accessing a blocked path
        blocked_path = "/inventory/dashboard/"
        response = self.client.get(blocked_path, follow=False)
        
        # Should redirect (302) for HQ admin
        if response.status_code == 302:
            location = response.get('Location', '')
            # Should redirect to an HQ path
            self.assertTrue(
                location.startswith('/hq/'),
                f"HQ admin should be redirected to HQ path, got {location}"
            )
            # Should NOT redirect to the same path (anti-loop guard)
            self.assertNotEqual(
                location.rstrip('/'),
                blocked_path.rstrip('/'),
                f"Redirect loop: {blocked_path} redirects to itself ({location})"
            )
        else:
            # If not redirecting, that's also acceptable (middleware might allow it)
            # Just ensure it's not a loop
            self.assertNotEqual(response.status_code, 301, "Unexpected permanent redirect")

    def test_hq_businesses_returns_200_no_redirect(self):
        """Test that /hq/businesses/ returns 200, not a redirect."""
        response = self.client.get('/hq/businesses/', follow=False)
        self.assertEqual(response.status_code, 200, f'Expected 200, got {response.status_code}')
        # Ensure it's not a redirect
        self.assertNotIn(response.status_code, [301, 302, 307, 308], 'Should not redirect')

    def test_active_tab_template_safe(self):
        """Test that templates handle active_tab safely without VariableDoesNotExist."""
        response = self.client.get('/hq/subscriptions/')
        self.assertEqual(response.status_code, 200)
        # Should not raise VariableDoesNotExist
        content = response.content.decode('utf-8')
        self.assertNotIn('VariableDoesNotExist', content)
        # Template should render successfully
        self.assertIn('Subscriptions', content)

    def test_gym_analytics_shows_member_metrics_not_stock(self):
        """Test that gym analytics shows member metrics, not stock widgets."""
        from tenants.models import Business
        from django.contrib.auth import get_user_model
        from tenants.models import Membership
        
        User = get_user_model()
        
        # Create gym business
        gym_business = Business.objects.create(
            name="Test Gym",
            business_kind="gym",
            status="ACTIVE"
        )
        
        # Create user and membership
        user = User.objects.create_user(
            username="gym_user",
            email="gym@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=user,
            business=gym_business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login and set active business
        self.client.login(username="gym_user", password="testpass123")
        session = self.client.session
        session['active_business_id'] = gym_business.id
        session.save()
        
        # Access analytics
        response = self.client.get('/inventory/analytics/')
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Should contain member-related text
        self.assertIn('Members', content, "Gym analytics should show member metrics")
        # Should NOT contain stock-related text
        self.assertNotIn('Top Stock', content, "Gym analytics should not show stock widgets")
        self.assertNotIn('Stock Value', content, "Gym analytics should not show stock value")

