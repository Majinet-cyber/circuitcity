# hq/tests/test_hq_views.py
"""Tests for HQ views - dashboard, business directory, subscriptions."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import BusinessSubscription as Subscription
from billing.models import Invoice
from tenants.models import Business, Membership

User = get_user_model()


class HQViewsTest(TestCase):
    """Test HQ views return 200 and handle edge cases."""

    def setUp(self):
        """Set up test data."""
        # Create superuser for HQ access
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )

        # Create a regular business
        self.business = Business.objects.create(
            name="Test Business", slug="test-business", created_by=self.admin_user, status="ACTIVE"
        )

        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

    def test_hq_dashboard_returns_200(self):
        """HQ dashboard should return 200 without errors."""
        url = reverse("hq:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_hq_business_directory_returns_200(self):
        """Business directory should return 200 with no template errors."""
        url = reverse("hq:business_directory")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Directory")
        # Should not have template errors for days_remaining
        self.assertNotContains(response, "Failed lookup for key")

    def test_business_directory_non_namespaced_url_resolves(self):
        """Non-namespaced 'business_directory' URL should resolve without NoReverseMatch."""
        # Test that {% url 'business_directory' %} works in templates
        try:
            url = reverse("business_directory")
            # Assert it resolves to /hq/businesses/
            self.assertEqual(url, "/hq/businesses/")

            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Business Directory")
        except Exception as e:
            self.fail(f"Non-namespaced 'business_directory' URL should resolve. Got: {e}")

    def test_business_detail_namespaced_url_resolves(self):
        """Namespaced 'hq:business_detail' URL should resolve correctly."""
        try:
            url = reverse("hq:business_detail", kwargs={"pk": self.business.id})
            # Should resolve to /hq/businesses/<pk>/
            self.assertIn(f"/hq/businesses/{self.business.id}/", url)

            response = self.client.get(url)
            # Should redirect to command center or return 200
            self.assertIn(response.status_code, [200, 302])
        except Exception as e:
            self.fail(f"Namespaced 'hq:business_detail' URL should resolve. Got: {e}")

    def test_business_detail_non_namespaced_url_resolves(self):
        """Non-namespaced 'business_detail' URL should resolve without NoReverseMatch."""
        # Test that {% url 'business_detail' pk=... %} works in templates
        try:
            url = reverse("business_detail", kwargs={"pk": self.business.id})
            # Should resolve to /hq/businesses/<pk>/
            self.assertIn(f"/hq/businesses/{self.business.id}/", url)

            response = self.client.get(url)
            # Should redirect to command center or return 200
            self.assertIn(response.status_code, [200, 302])
        except Exception as e:
            self.fail(f"Non-namespaced 'business_detail' URL should resolve. Got: {e}")

    def test_business_detail_with_current_app_matches_template_behavior(self):
        """Test reverse with current_app matches how Django resolves URLs in templates."""
        from django.urls import resolve, reverse

        # Resolve the business directory URL to get the namespace
        match = resolve("/hq/businesses/")
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.app_name, "hq")
        self.assertEqual(match.url_name, "business_directory")

        # When template uses {% url 'business_detail' pk=business.id %} in /hq/businesses/ context,
        # Django will use current_app (which is match.namespace) to resolve the URL.
        # We need to explicitly prepend the namespace when calling reverse() with current_app
        if match.namespace:
            url_with_current_app = reverse(f"{match.namespace}:business_detail", kwargs={"pk": self.business.id})
        else:
            url_with_current_app = reverse("business_detail", kwargs={"pk": self.business.id})
        self.assertIn(f"/hq/businesses/{self.business.id}/", url_with_current_app)

        # Test namespaced reverse (how templates resolve namespaced URLs)
        # When template uses {% url 'hq:business_detail' pk=business.id %}
        url_namespaced = reverse("hq:business_detail", kwargs={"pk": self.business.id})
        self.assertIn(f"/hq/businesses/{self.business.id}/", url_namespaced)

        # Both should resolve to the same URL
        self.assertEqual(url_with_current_app, url_namespaced)

        # Both should work when accessing the URL
        response1 = self.client.get(url_with_current_app)
        response2 = self.client.get(url_namespaced)
        self.assertIn(response1.status_code, [200, 302])
        self.assertIn(response2.status_code, [200, 302])

    def test_business_directory_returns_200_for_authenticated_hq_user(self):
        """GET /hq/businesses/ should return 200 for an authenticated HQ user."""
        url = reverse("hq:business_directory")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Directory")

    def test_hq_subscriptions_returns_200_without_contracts(self):
        """Subscriptions page should not 500 even if contracts module is missing."""
        url = reverse("hq:subscriptions")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    def test_contracts_stub_works_when_module_missing(self):
        """Contracts stub should return 200 when module is not available."""
        # This will hit the stub if contracts module is not available
        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        # Should return 200 (either real view or stub)
        self.assertEqual(response.status_code, 200)

    def test_business_detail_with_no_subscription(self):
        """Business detail should handle missing subscription gracefully."""
        # Business has no subscription yet
        url = reverse("hq:business_detail", args=[self.business.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should not crash with RelatedObjectDoesNotExist
        self.assertContains(response, self.business.name)

    def test_business_detail_with_subscription(self):
        """Business detail should show subscription when it exists."""
        # Create plan first (if Plan model exists)
        try:
            from billing.models import Plan

            plan = Plan.objects.create(name="Test Plan", code="test", amount=Decimal("50000.00"), interval="month")
            # Create subscription with plan
            subscription = Subscription.objects.create(
                business=self.business,
                plan=plan,
                status="active",
                current_period_end=timezone.now() + timedelta(days=30),
            )
        except (ImportError, AttributeError):
            # Plan model doesn't exist, create subscription without it
            subscription = Subscription.objects.create(
                business=self.business, status="active", current_period_end=timezone.now() + timedelta(days=30)
            )

        url = reverse("hq:business_detail", args=[self.business.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.business.name)

    def test_business_directory_normalizes_subscription_state(self):
        """Business directory should normalize subscription state to prevent template errors."""
        # Create business with no subscription
        biz2 = Business.objects.create(
            name="Business No Sub", slug="biz-no-sub", created_by=self.admin_user, status="ACTIVE"
        )

        url = reverse("hq:business_directory")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should handle missing days_remaining gracefully
        self.assertIn(biz2.name, response.content.decode())

    def test_hq_dashboard_sqlite_compatible(self):
        """HQ dashboard should work with SQLite (no custom functions)."""
        # Create some test sales data
        from inventory.models import InventoryItem
        from sales.models import Sale

        # This test ensures the dashboard doesn't crash on SQLite
        url = reverse("hq:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should not have OperationalError from user-defined functions

    def test_hq_dashboard_works_without_location_is_active(self):
        """HQ dashboard should return 200 even if Location model lacks is_active field."""
        from inventory.models import Location

        # Create a location to ensure the query runs
        location = Location.objects.create(name="Test Location", business=self.business)

        # The dashboard should work regardless of whether Location has is_active
        url = reverse("hq:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should not raise FieldError about is_active
        # The view should handle this gracefully by catching FieldError


class TestHQURLRouting(TestCase):
    """Test that HQ URLs are properly namespaced and resolve correctly."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="hqadmin2", email="admin2@hq.com", password="adminpass123"
        )
        self.business = Business.objects.create(
            name="Test Business Routing", slug="test-business-routing", created_by=self.admin_user, status="ACTIVE"
        )

    def test_hq_businesses_route_is_namespaced(self):
        """Ensure /hq/businesses/ resolves through hq.urls with namespace 'hq'."""
        from django.urls import resolve

        match = resolve("/hq/businesses/")
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.app_name, "hq")
        self.assertEqual(match.url_name, "business_directory")

    def test_business_detail_reverse_works_in_hq_namespace(self):
        """Test that business_detail can be reversed in hq namespace."""
        url = reverse("hq:business_detail", kwargs={"pk": self.business.id})
        self.assertTrue(url.endswith(f"/hq/businesses/{self.business.id}/"))

    def test_business_detail_resolve_has_correct_namespace(self):
        """Test that /hq/businesses/<pk>/ resolves with correct namespace."""
        from django.urls import resolve

        url = f"/hq/businesses/{self.business.id}/"
        match = resolve(url)
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.app_name, "hq")
        self.assertEqual(match.url_name, "business_detail")
        self.assertEqual(match.kwargs["pk"], self.business.id)

    def test_template_reversal_with_current_app(self):
        """Test that unnamespaced URL reversal works with current_app (simulates template context)."""
        from django.urls import resolve

        # Simulate template context: when rendering /hq/businesses/, current_app should be 'hq'
        match = resolve("/hq/businesses/")
        current_app = match.namespace

        # Template using {% url 'business_detail' pk=business.id %} should work
        url = reverse("business_detail", kwargs={"pk": self.business.id}, current_app=current_app)
        self.assertTrue(url.endswith(f"/hq/businesses/{self.business.id}/"))

    def test_namespaced_reversal_always_works(self):
        """Test that namespaced reversal always works regardless of current_app."""
        # Using {% url 'hq:business_detail' pk=business.id %} should always work
        url = reverse("hq:business_detail", kwargs={"pk": self.business.id})
        self.assertTrue(url.endswith(f"/hq/businesses/{self.business.id}/"))

        # Should work even without current_app
        url2 = reverse("hq:business_detail", kwargs={"pk": self.business.id}, current_app=None)
        self.assertEqual(url, url2)

    def test_hq_businesses_does_not_hit_cc_shim(self):
        """Regression test: Ensure /hq/businesses/ never resolves to _hq_businesses_shim."""
        from django.urls import resolve

        match = resolve("/hq/businesses/")
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.url_name, "business_directory")
        # Critical: The resolved function should NOT be _hq_businesses_shim
        self.assertNotEqual(match.func.__name__, "_hq_businesses_shim")
        # Verify it's the actual view from hq.views_business_directory
        self.assertEqual(match.func.__module__, "hq.views_business_directory")
        self.assertEqual(match.func.__name__, "business_directory")

    def test_business_detail_namespace_reverse(self):
        """Regression test: Ensure business_detail reverse works with hq namespace."""
        url = reverse("hq:business_detail", kwargs={"pk": 1})
        self.assertTrue(url.endswith("/hq/businesses/1/"))

    def test_business_detail_does_not_hit_cc_shim(self):
        """Regression test: Ensure /hq/businesses/<pk>/ never resolves to _hq_business_detail_shim."""
        from django.urls import resolve

        url = f"/hq/businesses/{self.business.id}/"
        match = resolve(url)
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.url_name, "business_detail")
        # Critical: The resolved function should NOT be _hq_business_detail_shim
        self.assertNotEqual(match.func.__name__, "_hq_business_detail_shim")
        # Verify it's the actual view from hq.views_business_directory
        self.assertEqual(match.func.__module__, "hq.views_business_directory")
        self.assertEqual(match.func.__name__, "business_detail")


class HQDashboardChartsTest(TestCase):
    """Test HQ dashboard chart data and numeric summaries."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

    def test_dashboard_has_numeric_summaries(self):
        """Dashboard should show numeric summaries beside charts."""
        url = reverse("hq:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check for key summary elements
        self.assertContains(response, "YTD TOTAL")
        self.assertContains(response, "PEAK MONTH")


class HQPaginationTest(TestCase):
    """Test HQ pagination handles edge cases safely."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

        # Create multiple businesses for pagination testing
        for i in range(35):
            Business.objects.create(
                name=f"Test Business {i}",
                slug=f"test-business-{i}",
                created_by=self.admin_user,
                status="ACTIVE",
            )

        # Create multiple agents for pagination testing
        first_business = Business.objects.first()
        for i in range(35):
            user = User.objects.create_user(
                username=f"agent{i}",
                email=f"agent{i}@test.com",
                password="testpass123",
            )
            Membership.objects.create(
                user=user,
                business=first_business,
                role="AGENT",
            )

    def test_agents_list_no_page_param(self):
        """GET /hq/agents/ without page param should return 200."""
        url = reverse("hq:agents")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_page_1(self):
        """GET /hq/agents/?page=1 should return 200."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"page": 1})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_page_0(self):
        """GET /hq/agents/?page=0 should return 200 (no crash)."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"page": 0})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_page_negative(self):
        """GET /hq/agents/?page=-1 should return 200 (no crash)."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"page": -1})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_page_invalid_string(self):
        """GET /hq/agents/?page=abc should return 200 (no crash)."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"page": "abc"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_page_very_large(self):
        """GET /hq/agents/?page=999999 should return 200 (should return last page, not crash)."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"page": 999999})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agents")

    def test_agents_list_pagination_preserves_search(self):
        """Pagination should preserve search query params."""
        url = reverse("hq:agents")
        response = self.client.get(url, {"q": "agent1", "page": 2})

        self.assertEqual(response.status_code, 200)
        # Search query should be preserved in pagination links
        self.assertContains(response, "agent1")

    def test_businesses_list_no_page_param(self):
        """GET /hq/businesses/ without page param should return 200."""
        url = reverse("hq:business_directory")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business")

    def test_businesses_list_page_0(self):
        """GET /hq/businesses/?page=0 should return 200 (no crash)."""
        url = reverse("hq:business_directory")
        response = self.client.get(url, {"page": 0})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business")

    def test_businesses_list_page_invalid_string(self):
        """GET /hq/businesses/?page=abc should return 200 (no crash)."""
        url = reverse("hq:business_directory")
        response = self.client.get(url, {"page": "abc"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business")

    def test_businesses_list_page_very_large(self):
        """GET /hq/businesses/?page=999999 should return 200 (should return last page, not crash)."""
        url = reverse("hq:business_directory")
        response = self.client.get(url, {"page": 999999})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business")

    def test_businesses_list_pagination_preserves_filters(self):
        """Pagination should preserve filter query params."""
        url = reverse("hq:business_directory")
        response = self.client.get(url, {"q": "Test", "page": 2})

        self.assertEqual(response.status_code, 200)
        # Search query should be preserved in pagination links
        self.assertContains(response, "Test")

    def test_hq_notifications_api_returns_200(self):
        """HQ notifications API should return 200 JSON, never 404."""
        # Test both slash and no-slash
        for url in ["/hq/api/notifications", "/hq/api/notifications/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.json()
            self.assertIn("items", data)
            self.assertIn("unread_count", data)
            self.assertIsInstance(data["items"], list)
            self.assertIsInstance(data["unread_count"], int)
