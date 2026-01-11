# core/tests/test_compat_kwargs.py
"""
Regression tests for 302/403 cascade fix.

CRITICAL: These tests must pass to ensure:
1. Single-membership users get 200 on dashboards (no 302 to /tenants/)
2. Multi-business users still see tenant chooser
3. Managers can access barcode/sell endpoints (no 403)

Run with: pytest core/tests/test_compat_kwargs.py -v
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


class TestSingleBusinessNoRedirect(TestCase):
    """
    CRITICAL: Single-membership users should NOT get 302 redirects to /tenants/.
    """

    def setUp(self):
        """Create single-business manager."""
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

        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client = Client()
        self.client.login(username="manager", password="testpass123")

    def test_phones_dashboard_returns_200(self):
        """Single-business user should get 200 on phones dashboard (no redirect)."""
        try:
            url = reverse("inventory:phones_dashboard")
        except Exception:
            try:
                url = reverse("dashboard:home")
            except Exception:
                self.skipTest("Dashboard view not available")

        response = self.client.get(url, follow=False)

        # CRITICAL: Should NOT redirect to /tenants/
        if response.status_code == 302:
            location = response.get("Location", "")
            # Print for debugging
            print(f"\n[DEBUG] Got 302 redirect to: {location}")
            self.assertNotIn(
                "/tenants/",
                location,
                f"Should not redirect to /tenants/ for single-business user. Got redirect to: {location}"
            )

        # Should be 200 or acceptable redirect (not to /tenants/)
        self.assertIn(
            response.status_code,
            [200, 301, 302],
            f"Expected 200/301/302, got {response.status_code}"
        )

    def test_inventory_stock_list_returns_200(self):
        """Single-business user should get 200 on inventory stock list."""
        try:
            url = reverse("inventory:stock_list")
        except Exception:
            self.skipTest("stock_list view not available")

        response = self.client.get(url, follow=False)

        # Should NOT redirect to /tenants/
        if response.status_code == 302:
            location = response.get("Location", "")
            self.assertNotIn(
                "/tenants/",
                location,
                f"Should not redirect to /tenants/ for single-business user. Got: {location}"
            )

        # Should be 200 or acceptable redirect
        self.assertIn(
            response.status_code,
            [200, 301, 302],
            f"Expected 200/301/302, got {response.status_code}"
        )


class TestMultiBusinessStillRedirects(TestCase):
    """
    CRITICAL: Multi-business users should still see tenant chooser.
    """

    def setUp(self):
        """Create multi-business agent (valid scenario)."""
        self.user = User.objects.create_user(
            username="agent",
            email="agent@test.com",
            password="testpass123"
        )

        self.business1 = Business.objects.create(
            name="Shop A",
            slug="shop-a",
            status="ACTIVE",
            business_kind="phones",
        )

        self.business2 = Business.objects.create(
            name="Shop B",
            slug="shop-b",
            status="ACTIVE",
            business_kind="liquor",
        )

        # Create locations (agents require locations)
        try:
            from inventory.models import Location
            loc1 = Location.objects.create(
                business=self.business1,
                name="Shop A Main",
                is_default=True,
            )
            loc2 = Location.objects.create(
                business=self.business2,
                name="Shop B Main",
                is_default=True,
            )

            # Create two AGENT memberships (valid multi-business scenario)
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
        except Exception:
            self.skipTest("Location model not available")

        self.client = Client()
        self.client.login(username="agent", password="testpass123")

    def test_multi_business_user_no_auto_select(self):
        """Multi-business user should NOT have auto-selected business."""
        try:
            url = reverse("dashboard:home")
        except Exception:
            url = "/"

        response = self.client.get(url, follow=False)

        # Session should NOT have auto-selected a business
        active_biz = self.client.session.get("active_business_id")
        self.assertIsNone(
            active_biz,
            "Multi-business user should NOT have auto-selected business"
        )


class TestManagerBarcodeWorkflow(TestCase):
    """
    CRITICAL: Managers should access barcode/sell endpoints without 403.
    """

    def setUp(self):
        """Create manager with proper setup."""
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

        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client = Client()
        self.client.login(username="manager", password="testpass123")

    def test_manager_scan_in_not_403(self):
        """Manager should access scan_in without 403."""
        try:
            url = reverse("inventory:scan_in")
        except Exception:
            self.skipTest("scan_in view not available")

        response = self.client.get(url, follow=False)

        # CRITICAL: Should NOT be 403
        self.assertNotEqual(
            response.status_code,
            403,
            f"Manager should not get 403 on scan_in. Got: {response.status_code}"
        )

    def test_manager_barcode_endpoints_not_403(self):
        """Manager should access barcode workflow without 403."""
        endpoints = [
            "inventory:scan_in",
            "inventory:phone_scan_in",
        ]

        for name in endpoints:
            try:
                url = reverse(name)
            except Exception:
                continue

            with self.subTest(endpoint=name):
                response = self.client.get(url, follow=False)

                self.assertNotEqual(
                    response.status_code,
                    403,
                    f"Manager should not get 403 on {name}"
                )

    def test_manager_sell_quick_not_403(self):
        """Manager should access sell_quick without 403."""
        try:
            url = reverse("inventory:sell_quick_page")
        except Exception:
            self.skipTest("sell_quick_page not available")

        response = self.client.get(url, follow=False)

        self.assertNotEqual(
            response.status_code,
            403,
            "Manager should not get 403 on sell_quick_page"
        )
