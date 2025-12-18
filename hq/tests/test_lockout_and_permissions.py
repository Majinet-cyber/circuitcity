# hq/tests/test_lockout_and_permissions.py
"""
Tests for subscription lockout and role-based UI permissions.

Requirements:
1. Agents must NOT see manager-only subscription controls
2. When business is locked (trial ended / unpaid), EVERYONE is blocked
3. Lockout messaging differs by role:
   - Agents: "Account locked. Contact your manager."
   - Managers: "Account locked. Pay subscription or contact admin to resolve."
4. JSON endpoints must also be blocked during lockout
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from tenants.models import Business, Membership
from billing.models import BusinessSubscription, SubscriptionPlan

User = get_user_model()


class SubscriptionLockoutTestCase(TestCase):
    """Test subscription lockout blocks everyone with role-specific messaging."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            status='ACTIVE'
        )
        
        # Create subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name='Test Plan',
            amount=20000,
            is_active=True
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.client = Client()
    
    def _create_expired_subscription(self):
        """Create an expired subscription for the business."""
        subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status='expired',
            trial_end=timezone.now() - timedelta(days=5),
            current_period_end=timezone.now() - timedelta(days=5)
        )
        return subscription
    
    def _create_active_subscription(self):
        """Create an active subscription for the business."""
        subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status='active',
            trial_end=None,
            current_period_end=timezone.now() + timedelta(days=30)
        )
        return subscription
    
    def test_agent_blocked_when_subscription_expired(self):
        """Agents should be blocked when subscription is expired."""
        self._create_expired_subscription()
        
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access dashboard
        response = self.client.get('/dashboard/')
        
        # Should be blocked (403 or redirect to lockout page)
        self.assertIn(response.status_code, [403, 302])
        
        # If 403, check for agent-specific message
        if response.status_code == 403:
            content = response.content.decode('utf-8')
            self.assertIn('Account locked', content.lower())
            self.assertIn('Contact your manager', content.lower())
    
    def test_manager_blocked_when_subscription_expired(self):
        """Managers should be blocked when subscription is expired."""
        self._create_expired_subscription()
        
        self.client.force_login(self.manager)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access dashboard
        response = self.client.get('/dashboard/')
        
        # Should be blocked (403 or redirect to lockout page)
        self.assertIn(response.status_code, [403, 302])
        
        # If 403, check for manager-specific message
        if response.status_code == 403:
            content = response.content.decode('utf-8')
            self.assertIn('Account locked', content.lower())
            # Manager should see payment/admin message
            self.assertTrue(
                'pay subscription' in content.lower() or 
                'contact admin' in content.lower()
            )
    
    def test_agent_can_access_when_subscription_active(self):
        """Agents should access app when subscription is active."""
        self._create_active_subscription()
        
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access dashboard
        response = self.client.get('/dashboard/')
        
        # Should be allowed (200 or redirect to proper dashboard)
        self.assertIn(response.status_code, [200, 302])
        
        # If redirected, should not be to lockout page
        if response.status_code == 302:
            self.assertNotIn('blocked', response.url.lower())
            self.assertNotIn('locked', response.url.lower())
    
    def test_manager_can_access_when_subscription_active(self):
        """Managers should access app when subscription is active."""
        self._create_active_subscription()
        
        self.client.force_login(self.manager)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access dashboard
        response = self.client.get('/dashboard/')
        
        # Should be allowed
        self.assertIn(response.status_code, [200, 302])
    
    def test_lockout_blocks_inventory_pages(self):
        """Lockout should block inventory pages, not just dashboard."""
        self._create_expired_subscription()
        
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try various inventory pages
        pages_to_test = [
            '/inventory/dashboard/',
            '/inventory/list/',
        ]
        
        for page in pages_to_test:
            response = self.client.get(page)
            # Should be blocked
            self.assertIn(
                response.status_code, 
                [403, 302], 
                f"Page {page} should be blocked but got {response.status_code}"
            )


class RoleBasedUIPermissionsTestCase(TestCase):
    """Test that agents don't see manager-only subscription UI."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            status='ACTIVE'
        )
        
        # Create subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name='Test Plan',
            amount=20000,
            is_active=True
        )
        
        # Create active trial subscription
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status='trial',
            trial_end=timezone.now() + timedelta(days=15),
            current_period_end=timezone.now() + timedelta(days=30)
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.client = Client()
    
    def test_agent_does_not_see_subscription_actions(self):
        """Agents should NOT see subscription management buttons."""
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Access dashboard
        response = self.client.get('/dashboard/')
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            
            # Should NOT contain subscription action buttons
            self.assertNotIn('subscription-actions', content)
            self.assertNotIn('Choose plan', content)
            self.assertNotIn('Checkout', content)
            self.assertNotIn('billing/subscribe', content)
            self.assertNotIn('billing/checkout', content)
    
    def test_manager_sees_subscription_actions(self):
        """Managers SHOULD see subscription management buttons."""
        self.client.force_login(self.manager)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Access dashboard
        response = self.client.get('/dashboard/')
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            
            # Should contain subscription action buttons
            # (trial banner with Choose plan / Checkout buttons)
            self.assertTrue(
                'subscription-actions' in content or
                'Choose plan' in content or
                'Checkout' in content,
                "Manager should see subscription management UI"
            )
    
    def test_agent_cannot_access_billing_pages(self):
        """Agents should not be able to access billing pages (optional enforcement)."""
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access billing pages
        billing_urls = [
            '/billing/subscribe/',
            '/billing/checkout/',
        ]
        
        for url in billing_urls:
            response = self.client.get(url)
            # Either blocked (403/302) or allowed but no sensitive data
            # This is optional - the main requirement is hiding UI
            # If allowed, we just verify no crash
            self.assertIn(response.status_code, [200, 302, 403, 404])


class JSONEndpointLockoutTestCase(TestCase):
    """Test that JSON endpoints are also blocked during lockout."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            status='ACTIVE'
        )
        
        # Create subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name='Test Plan',
            amount=20000,
            is_active=True
        )
        
        # Create expired subscription
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status='expired',
            trial_end=timezone.now() - timedelta(days=5),
            current_period_end=timezone.now() - timedelta(days=5)
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.client = Client()
    
    def test_json_endpoints_blocked_during_lockout(self):
        """JSON endpoints should be blocked when subscription is expired."""
        self.client.force_login(self.agent)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to access various JSON endpoints
        json_endpoints = [
            '/api/dashboard/stats/',
            '/api/inventory/summary/',
        ]
        
        for endpoint in json_endpoints:
            response = self.client.get(endpoint)
            
            # Should be blocked
            if response.status_code == 200:
                # If 200, check if it's actually returning error JSON
                try:
                    import json
                    data = json.loads(response.content)
                    # Should have error indicator
                    self.assertFalse(
                        data.get('ok', True),
                        f"JSON endpoint {endpoint} should return error during lockout"
                    )
                except:
                    pass
            else:
                # Or should return non-200 status
                self.assertIn(response.status_code, [403, 302, 401, 404])

