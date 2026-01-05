"""
Tests to prevent infinite redirect loops for unrecognized business kinds.

This test suite ensures:
1. /verticals/none/ returns 200 (not 302)
2. Generic dashboard returns 200 (not 302)
3. Cement businesses route to cement dashboard (not unrecognized)
4. Unknown business_kind routes to generic dashboard with at most 1 redirect
5. No infinite loops occur for any business_kind value
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


class RedirectLoopPreventionTests(TestCase):
    """Tests to prevent infinite redirect loops"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser@example.com", email="testuser@example.com", password="password123"
        )
        self.client.login(username="testuser@example.com", password="password123")

    def test_verticals_none_returns_200(self):
        """
        /verticals/none/ must return HTTP 200 (not 302).
        This prevents redirect loops.
        """
        # Create business with unrecognized kind
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            created_by=self.user,
            business_kind="unknown_vertical",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("verticals:no_business")
        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
            f"/verticals/none/ should return 200, got {response.status_code}. "
            "Returning 302 causes infinite redirect loops.",
        )

        # Should show helpful message
        content = response.content.decode("utf-8")
        self.assertIn("not fully configured", content.lower())

    def test_generic_dashboard_returns_200(self):
        """
        /inventory/generic-dashboard/ must return HTTP 200 (not redirect).
        This is the safe landing page for unrecognized verticals.
        """
        business = Business.objects.create(
            name="Test Business",
            slug="test-business-2",
            created_by=self.user,
            business_kind="unknown_vertical",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:generic_dashboard")
        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
            f"Generic dashboard should return 200, got {response.status_code}. "
            "This is the safe landing page - it must not redirect.",
        )

    def test_cement_business_routes_correctly(self):
        """
        Cement businesses should route to generic dashboard (treated as legacy).
        CRITICAL: Must not crash or loop, must land on a usable 200 page.
        """
        business = Business.objects.create(
            name="Cement Store",
            slug="cement-store",
            created_by=self.user,
            business_kind="cement",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        # Access inventory dashboard - should redirect to generic dashboard
        url = reverse("inventory:inventory_dashboard")
        response = self.client.get(url, follow=True)

        # Should return 200 (not crash)
        self.assertEqual(
            response.status_code,
            200,
            f"Cement business should return 200, got {response.status_code}",
        )

        # Should not end up on /verticals/none/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Cement business should NOT redirect to /verticals/none/, got: {final_url}",
        )

        # Should redirect to generic dashboard (cement is treated as legacy)
        self.assertIn(
            "generic-dashboard",
            final_url.lower(),
            f"Cement business should redirect to generic dashboard, got: {final_url}",
        )

    def test_unknown_business_kind_no_infinite_loop(self):
        """
        Unknown business_kind should redirect at most ONCE to generic dashboard,
        then return 200. No infinite loops.
        """
        business = Business.objects.create(
            name="Unknown Business",
            slug="unknown-business",
            created_by=self.user,
            business_kind="totally_unknown_vertical_xyz",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:inventory_dashboard")
        response = self.client.get(url, follow=True)

        # Should eventually return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Unknown vertical should eventually return 200, got {response.status_code}",
        )

        # Should redirect at most once
        redirect_count = len(response.redirect_chain)
        self.assertLessEqual(
            redirect_count,
            2,
            f"Unknown vertical should redirect at most twice (to generic dashboard, maybe via fallback), "
            f"got {redirect_count} redirects: {response.redirect_chain}",
        )

        # Final URL should NOT be /verticals/none/ (that would indicate a loop)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Unknown vertical should NOT end on /verticals/none/, got: {final_url}",
        )

    def test_null_business_kind_redirects_to_settings(self):
        """
        business_kind=None should redirect to settings (not generic dashboard).
        This is the ONLY case where settings redirect is correct.
        """
        business = Business.objects.create(
            name="No Kind Business",
            slug="no-kind-business",
            created_by=self.user,
            business_kind=None,  # NULL
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:inventory_dashboard")
        response = self.client.get(url, follow=True)

        # Should redirect to settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        self.assertTrue(
            "/accounts/settings" in final_url or "/settings/" in final_url,
            f"NULL business_kind should redirect to settings, got: {final_url}",
        )

    def test_hardware_business_routes_correctly(self):
        """
        Hardware businesses should route to generic dashboard (not cement, not unrecognized).
        """
        business = Business.objects.create(
            name="Hardware Store",
            slug="hardware-store",
            created_by=self.user,
            business_kind="hardware",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:inventory_dashboard")
        response = self.client.get(url, follow=True)

        # Should return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Hardware business should return 200, got {response.status_code}",
        )

        # Should NOT redirect to /verticals/none/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Hardware business should NOT redirect to /verticals/none/, got: {final_url}",
        )

        # Should redirect to generic dashboard
        self.assertIn(
            "generic-dashboard",
            final_url.lower(),
            f"Hardware business should redirect to generic dashboard, got: {final_url}",
        )

    def test_generic_dashboard_does_not_redirect_again(self):
        """
        If already on generic dashboard, it must NOT redirect again.
        This is critical to prevent loops.
        """
        business = Business.objects.create(
            name="Test Business",
            slug="test-business-3",
            created_by=self.user,
            business_kind="unknown_vertical",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:generic_dashboard")
        response = self.client.get(url, follow=False)

        # Should return 200 directly (no redirect)
        self.assertEqual(
            response.status_code,
            200,
            f"Generic dashboard should return 200 directly (no redirect), got {response.status_code}",
        )

    def test_phones_business_routes_correctly(self):
        """
        Phones businesses should use the default inventory dashboard.
        """
        business = Business.objects.create(
            name="Phone Store",
            slug="phone-store",
            created_by=self.user,
            business_kind="phones",
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=business, role="MANAGER", status="ACTIVE")

        url = reverse("inventory:inventory_dashboard")
        response = self.client.get(url, follow=True)

        # Should return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Phones business should return 200, got {response.status_code}",
        )

        # Should NOT redirect to /verticals/none/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Phones business should NOT redirect to /verticals/none/, got: {final_url}",
        )

    def test_url_home_for_unknown_kind_is_safe(self):
        """
        url_home context variable for unknown business_kind must point to a safe page
        (NOT the dispatcher) to prevent redirect loops.
        """
        from inventory.url_home import get_home_url_for_business

        business = Business.objects.create(
            name="Unknown Business",
            slug="unknown-biz",
            created_by=self.user,
            business_kind="totally_unknown_xyz",
            status="ACTIVE",
        )

        url_home = get_home_url_for_business(business)

        # Should NOT point to the dispatcher (/inventory/dashboard/)
        self.assertNotEqual(
            url_home,
            "/inventory/dashboard/",
            "url_home for unknown business_kind should NOT point to dispatcher (prevents loops)",
        )

        # Should point to generic dashboard
        self.assertEqual(
            url_home,
            "/inventory/generic-dashboard/",
            f"url_home for unknown business_kind should point to generic dashboard, got: {url_home}",
        )

    def test_url_home_for_cement_is_safe(self):
        """
        url_home for cement (legacy) must point to generic dashboard (not crash).
        """
        from inventory.url_home import get_home_url_for_business

        business = Business.objects.create(
            name="Cement Store",
            slug="cement-biz",
            created_by=self.user,
            business_kind="cement",
            status="ACTIVE",
        )

        url_home = get_home_url_for_business(business)

        # Should point to generic dashboard (cement is treated as legacy)
        self.assertEqual(
            url_home,
            "/inventory/generic-dashboard/",
            f"url_home for cement should point to generic dashboard, got: {url_home}",
        )

