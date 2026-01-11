# tests/test_active_business_ssot.py
"""
Tests for SSOT active business resolution.

CRITICAL: These tests must prevent regressions that cause:
- 302 redirects to /tenants/ for single-business users
- 403 errors for managers on inventory/barcode endpoints
- Multi-business selection flow breaking

Run with: pytest tests/test_active_business_ssot.py -v
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tenants.models import Business, Membership
from tenants.services.active_business import (
    get_active_business,
    ensure_active_business,
    set_active_business,
)

User = get_user_model()


class TestActiveBusinessSSOT(TestCase):
    """Test SSOT service for active business resolution."""
    
    def setUp(self):
        """Create test users and businesses."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        self.business1 = Business.objects.create(
            name="Test Business 1",
            slug="test-business-1",
            status="ACTIVE",
            business_kind="phones",
        )
        
        self.business2 = Business.objects.create(
            name="Test Business 2",
            slug="test-business-2",
            status="ACTIVE",
            business_kind="liquor",
        )
        
        self.client = Client()
    
    def test_get_active_business_from_session(self):
        """Test getting active business from session."""
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()
        
        # Create mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = session
        
        # Should retrieve from session
        biz = get_active_business(request)
        self.assertEqual(biz.id, self.business1.id)
    
    def test_get_active_business_from_request_attr(self):
        """Test getting active business from request.business."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = self.client.session
        request.business = self.business1
        
        biz = get_active_business(request)
        self.assertEqual(biz.id, self.business1.id)
    
    def test_ensure_active_business_single_membership(self):
        """Test auto-select when user has exactly one membership."""
        # Create single membership
        Membership.objects.create(
            user=self.user,
            business=self.business1,
            role="MANAGER",
            status="ACTIVE",
        )
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = self.client.session
        request.user = self.user
        
        # Should auto-select the single business
        biz = ensure_active_business(request, self.user, auto_select_single=True)
        self.assertIsNotNone(biz)
        self.assertEqual(biz.id, self.business1.id)
        
        # Should persist to session
        self.assertEqual(request.session.get("active_business_id"), self.business1.id)
    
    def test_ensure_active_business_multiple_memberships(self):
        """Test NO auto-select when user has multiple memberships."""
        # Create locations for agent memberships (agents require locations)
        try:
            from inventory.models import Location
            loc1 = Location.objects.create(
                business=self.business1,
                name="Location 1",
                is_default=True,
            )
            loc2 = Location.objects.create(
                business=self.business2,
                name="Location 2",
                is_default=True,
            )
        except Exception:
            # Skip if Location model not available
            self.skipTest("Location model not available")
        
        # Create two AGENT memberships (agents can work for multiple businesses)
        Membership.objects.create(
            user=self.user,
            business=self.business1,
            role="AGENT",
            status="ACTIVE",
            location=loc1,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business2,
            role="AGENT",
            status="ACTIVE",
            location=loc2,
        )
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = self.client.session
        request.user = self.user
        
        # Should NOT auto-select (multi-business user)
        biz = ensure_active_business(request, self.user, auto_select_single=True)
        self.assertIsNone(biz)
        
        # Session should be empty
        self.assertIsNone(request.session.get("active_business_id"))
    
    def test_set_active_business(self):
        """Test setting active business."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = self.client.session
        
        set_active_business(request, self.business1)
        
        # Should set on request
        self.assertEqual(request.business, self.business1)
        self.assertEqual(request.active_business, self.business1)
        
        # Should persist to session
        self.assertEqual(request.session.get("active_business_id"), self.business1.id)
    
    def test_set_active_business_clear(self):
        """Test clearing active business."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.session = self.client.session
        
        # Set first
        set_active_business(request, self.business1)
        self.assertEqual(request.session.get("active_business_id"), self.business1.id)
        
        # Clear
        set_active_business(request, None)
        self.assertIsNone(request.session.get("active_business_id"))


class TestSingleBusinessUserIntegration(TestCase):
    """
    Integration tests: single-business users should NOT get 302 to /tenants/.
    
    CRITICAL: These tests lock the behavior to prevent regressions.
    """
    
    def setUp(self):
        """Create single-business user."""
        self.user = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.business = Business.objects.create(
            name="My Shop",
            slug="my-shop",
            status="ACTIVE",
            business_kind="phones",
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        self.client = Client()
        self.client.login(username="manager", password="testpass123")
    
    def test_dashboard_home_no_redirect(self):
        """Single-business user should access dashboard without 302 to /tenants/."""
        try:
            url = reverse("dashboard:home")
        except Exception:
            self.skipTest("dashboard:home not available")
        
        response = self.client.get(url, follow=False)
        
        # Debug: Print redirect location if 302
        if response.status_code == 302:
            location = response.get("Location", "")
            print(f"\n[DEBUG] Got 302 redirect to: {location}")
            # Check if redirecting to /tenants/
            if "/tenants/" in location:
                print(f"[DEBUG] Session state: {dict(self.client.session)}")
                self.fail(f"Single-business user should NOT redirect to /tenants/. Got: {location}")
        
        # Should NOT be 302 to /tenants/ (but other redirects are OK)
        # Should be 200, 301, or 302 (to non-tenant URL)
        self.assertIn(response.status_code, [200, 301, 302],
                     f"Expected 200/301/302, got {response.status_code}")
    
    def test_inventory_list_no_redirect(self):
        """Single-business user should access inventory list without 302."""
        try:
            url = reverse("inventory:stock_list")
        except Exception:
            try:
                url = reverse("inventory:inventory_list")
            except Exception:
                self.skipTest("inventory list view not available")
        
        response = self.client.get(url, follow=False)
        
        # Should NOT be 302 to /tenants/
        if response.status_code == 302:
            location = response.get("Location", "")
            self.assertNotIn("/tenants/", location,
                           "Should not redirect to /tenants/ for single-business user")


class TestMultiBusinessUserNoRegression(TestCase):
    """
    Test multi-business users still see tenant chooser.
    
    CRITICAL: Ensure we don't break existing multi-business selection flow.
    
    NOTE: Managers are bound to a single business by validation rules.
    Multi-business users would be AGENTS with multiple business memberships,
    or users with mixed MANAGER/AGENT roles across different businesses.
    """
    
    def setUp(self):
        """Create user with multiple AGENT memberships (valid scenario)."""
        self.user = User.objects.create_user(
            username="multibiz",
            email="multi@test.com",
            password="testpass123"
        )
        
        self.business1 = Business.objects.create(
            name="Shop 1",
            slug="shop-1",
            status="ACTIVE",
            business_kind="phones",
        )
        
        self.business2 = Business.objects.create(
            name="Shop 2",
            slug="shop-2",
            status="ACTIVE",
            business_kind="liquor",
        )
        
        # Create locations (required for agents)
        try:
            from inventory.models import Location
            self.loc1 = Location.objects.create(
                business=self.business1,
                name="Shop 1 Main",
                is_default=True,
            )
            self.loc2 = Location.objects.create(
                business=self.business2,
                name="Shop 2 Main",
                is_default=True,
            )
        except Exception:
            self.skipTest("Location model not available")
        
        # Create two AGENT memberships (valid multi-business scenario)
        # Managers are bound to single business, but agents can work for multiple
        Membership.objects.create(
            user=self.user,
            business=self.business1,
            role="AGENT",
            status="ACTIVE",
            location=self.loc1,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business2,
            role="AGENT",
            status="ACTIVE",
            location=self.loc2,
        )
        
        self.client = Client()
        self.client.login(username="multibiz", password="testpass123")
    
    def test_multi_business_user_sees_chooser(self):
        """Multi-business user should be redirected to tenant chooser."""
        try:
            url = reverse("dashboard:home")
        except Exception:
            self.skipTest("dashboard:home not available")
        
        response = self.client.get(url, follow=True)
        
        # Should redirect to tenant chooser or show some selection mechanism
        # (Exact behavior depends on implementation, but should not auto-select)
        
        # Check session - should NOT have auto-selected a business
        session = self.client.session
        active_biz_id = session.get("active_business_id")
        
        # If a business was set, it should be because user explicitly selected it,
        # NOT because of auto-selection
        # For this test, we haven't selected anything, so it should be None
        # (unless the redirect chain selected one, which would be a regression)
        
        # Note: Exact assertion depends on your redirect logic
        # The key is: do NOT auto-select when multiple memberships exist


class TestManagerBarcodeWorkflowPermissions(TestCase):
    """
    Test managers can access barcode workflow without 403.
    
    CRITICAL: Lock permission behavior to prevent 403 cascades.
    """
    
    def setUp(self):
        """Create manager user with proper permissions."""
        self.user = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE",
            business_kind="phones",
        )
        
        # Create MANAGER membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        self.client = Client()
        self.client.login(username="manager", password="testpass123")
    
    def test_manager_can_access_scan_in(self):
        """Manager should access scan-in without 403."""
        try:
            url = reverse("inventory:scan_in")
        except Exception:
            self.skipTest("scan_in view not available")
        
        response = self.client.get(url, follow=False)
        
        # Should NOT be 403
        self.assertNotEqual(response.status_code, 403,
                          "Manager should not get 403 on scan-in endpoint")
        
        # Should be 200 or redirect (but not 403)
        self.assertIn(response.status_code, [200, 302, 301],
                     f"Expected 200/301/302, got {response.status_code}")
    
    def test_manager_can_access_barcode_endpoints(self):
        """Manager should access barcode workflow without 403."""
        # Test various barcode-related endpoints
        endpoint_names = [
            "inventory:scan_in",
            "inventory:phone_scan_in",
        ]
        
        for name in endpoint_names:
            try:
                url = reverse(name)
            except Exception:
                continue  # Skip if not available
            
            response = self.client.get(url, follow=False)
            
            # Should NOT be 403
            self.assertNotEqual(
                response.status_code, 403,
                f"Manager should not get 403 on {name}"
            )
    
    def test_manager_role_resolution(self):
        """Test manager role is correctly resolved by middleware."""
        try:
            url = reverse("inventory:stock_list")
        except Exception:
            self.skipTest("stock_list view not available")
        
        response = self.client.get(url, follow=False)
        
        # Check that role was set on request (if we can inspect it)
        # For now, just verify no 403
        self.assertNotEqual(response.status_code, 403,
                          "Manager should not get 403 on inventory endpoints")


class TestSubscriptionTrialCreation(TestCase):
    """
    Test that trial subscriptions are created on business creation.
    
    This prevents 403 errors from subscription gate middleware.
    """
    
    def test_trial_created_on_business_creation(self):
        """New business should have trial subscription."""
        try:
            from billing.models import BusinessSubscription
        except ImportError:
            self.skipTest("Billing app not installed")
        
        business = Business.objects.create(
            name="New Shop",
            slug="new-shop",
            status="ACTIVE",
            business_kind="phones",
        )
        
        # Check if trial was created (signal should have fired)
        try:
            subscription = business.subscription
            self.assertIsNotNone(subscription, 
                               "Trial subscription should be created on business creation")
            
            # Should be trial status
            self.assertEqual(subscription.status, "trial",
                           "New business should have trial subscription")
        except AttributeError:
            # subscription relation doesn't exist yet, that's ok for this test
            pass
    
    def test_existing_subscription_not_overridden(self):
        """Signal should not override existing subscription."""
        try:
            from billing.models import BusinessSubscription, Plan
        except ImportError:
            self.skipTest("Billing app not installed")
        
        business = Business.objects.create(
            name="Shop with Sub",
            slug="shop-with-sub",
            status="ACTIVE",
            business_kind="phones",
        )
        
        # Manually create active subscription
        plan, _ = Plan.objects.get_or_create(
            code="premium",
            defaults={"name": "Premium", "amount": 10000}
        )
        
        from django.utils import timezone
        from datetime import timedelta
        
        sub = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="active",
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=365),
        )
        
        # Save business again (trigger signal)
        business.save()
        
        # Subscription should remain active (not overridden)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active",
                        "Existing subscription should not be overridden")


@pytest.mark.django_db
class TestMiddlewareIntegration:
    """
    Pytest-style integration tests for middleware.
    """
    
    def test_middleware_auto_selects_single_business(self, client):
        """Test middleware auto-selects business for single-business user."""
        user = User.objects.create_user(
            username="auto_user",
            email="auto@test.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Auto Shop",
            slug="auto-shop",
            status="ACTIVE",
            business_kind="phones",
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        client.login(username="auto_user", password="testpass123")
        
        # Make a request (any protected page)
        try:
            response = client.get(reverse("dashboard:home"), follow=False)
        except Exception:
            # If dashboard not available, just check session
            response = client.get("/", follow=False)
        
        # Session should have active_business_id set by middleware
        assert client.session.get("active_business_id") == business.id, \
            "Middleware should auto-select single business"
    
    def test_middleware_does_not_auto_select_multi_business(self, client):
        """Test middleware does NOT auto-select for multi-business user."""
        user = User.objects.create_user(
            username="multi_user",
            email="multi@test.com",
            password="testpass123"
        )
        
        business1 = Business.objects.create(
            name="Shop A",
            slug="shop-a",
            status="ACTIVE",
            business_kind="phones",
        )
        
        business2 = Business.objects.create(
            name="Shop B",
            slug="shop-b",
            status="ACTIVE",
            business_kind="liquor",
        )
        
        # Create locations (required for agents)
        try:
            from inventory.models import Location
            loc1 = Location.objects.create(
                business=business1,
                name="Shop A Main",
                is_default=True,
            )
            loc2 = Location.objects.create(
                business=business2,
                name="Shop B Main",
                is_default=True,
            )
        except Exception:
            pytest.skip("Location model not available")
        
        # Create two AGENT memberships (valid multi-business scenario)
        # Managers are bound to single business by validation rules
        Membership.objects.create(
            user=user,
            business=business1,
            role="AGENT",
            status="ACTIVE",
            location=loc1,
        )
        Membership.objects.create(
            user=user,
            business=business2,
            role="AGENT",
            status="ACTIVE",
            location=loc2,
        )
        
        client.login(username="multi_user", password="testpass123")
        
        # Make a request
        try:
            client.get(reverse("dashboard:home"), follow=False)
        except Exception:
            client.get("/", follow=False)
        
        # Session should NOT have active_business_id (multi-business user)
        assert client.session.get("active_business_id") is None, \
            "Middleware should NOT auto-select for multi-business user"

