# hq/tests/test_pharmacy_fast_sell_no_recursion.py
"""
TEST: Pharmacy Fast Sell Must Not Cause RecursionError

This test specifically targets the production 500 error where:
- /verticals/pharmacy/dashboard/ returns 200
- Then /inventory/dashboard/ redirects (302)
- Then /dashboard/ redirects (302)
- Then /accounts/login/ redirects (302)
- Then RecursionError occurs

The recursion was in template render calls, likely from circular includes or
redirect loops in the require_business decorator.

This test ensures:
1. Pharmacy fast sell page renders successfully (200)
2. No RecursionError is raised
3. Template includes work correctly
4. Pharmacy dashboard works
5. All related pharmacy pages load without recursion
"""
import pytest
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import Location

try:
    from inventory.models_pharmacy import PharmacyBatch
    from inventory.models import MerchProduct

    PHARMACY_AVAILABLE = True
except ImportError:
    PHARMACY_AVAILABLE = False

User = get_user_model()


@pytest.mark.skipif(not PHARMACY_AVAILABLE, reason="Pharmacy models not available")
class TestPharmacyFastSellNoRecursion(TestCase):
    """
    Test that pharmacy fast sell does not cause recursion errors.
    """

    def setUp(self):
        """Set up pharmacy business and user."""
        # Create pharmacy business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            kind="pharmacy",
            status="ACTIVE",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
            is_default=True,
        )

        # Create manager user
        self.manager = User.objects.create_user(
            username="pharma_manager",
            email="pharma@test.com",
            password="testpass123",
        )

        # Create membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Create a sample product
        if PHARMACY_AVAILABLE:
            self.product = MerchProduct.objects.create(
                business=self.business,
                name="Test Medicine",
                kind="pharmacy",
                is_active=True,
            )

            # Create a batch
            self.batch = PharmacyBatch.objects.create(
                business=self.business,
                merch_product=self.product,
                batch_number="BATCH001",
                quantity=100,
                cost_price=50.00,
                selling_price=80.00,
            )

        self.client = Client()

    def test_pharmacy_fast_sell_page_loads(self):
        """Pharmacy fast sell page must load without recursion error."""
        # Login
        self.client.login(username="pharma_manager", password="testpass123")

        # Set active business
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET fast sell page
        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell"))

            # CRITICAL: Should return 200, not raise RecursionError
            self.assertEqual(response.status_code, 200, "Pharmacy fast sell should return 200")

            # Check that template rendered (not empty)
            self.assertTrue(len(response.content) > 0, "Fast sell page should have content")

            # Check for key elements (scanner, payment mix, etc.)
            content = response.content.decode("utf-8")
            self.assertIn("fast-sell", content.lower(), "Page should contain fast sell elements")

        except RecursionError as e:
            self.fail(f"RecursionError occurred in pharmacy fast sell: {e}")

    def test_pharmacy_dashboard_loads(self):
        """Pharmacy dashboard must load without recursion error."""
        self.client.login(username="pharma_manager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        try:
            response = self.client.get(reverse("verticals:pharmacy_dashboard"))

            # Should return 200
            self.assertEqual(response.status_code, 200, "Pharmacy dashboard should return 200")

        except RecursionError as e:
            self.fail(f"RecursionError occurred in pharmacy dashboard: {e}")

    def test_pharmacy_hub_loads(self):
        """Pharmacy hub page must load without recursion error."""
        self.client.login(username="pharma_manager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        try:
            response = self.client.get(reverse("verticals:pharmacy_hub"))

            # Should return 200
            self.assertEqual(response.status_code, 200, "Pharmacy hub should return 200")

        except RecursionError as e:
            self.fail(f"RecursionError occurred in pharmacy hub: {e}")

    def test_pharmacy_fast_sell_api_endpoints(self):
        """Pharmacy fast sell API endpoints must work without recursion."""
        self.client.login(username="pharma_manager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Test lookup API
        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell_lookup_api"), {"barcode": "test123"})

            # Should return 200 (even if not found)
            self.assertEqual(response.status_code, 200, "Fast sell lookup API should return 200")

        except RecursionError as e:
            self.fail(f"RecursionError in fast sell lookup API: {e}")

        # Test KPIs API
        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell_kpis_api"), {"range": "today"})

            # Should return 200
            self.assertEqual(response.status_code, 200, "Fast sell KPIs API should return 200")

        except RecursionError as e:
            self.fail(f"RecursionError in fast sell KPIs API: {e}")

    def test_redirect_chain_no_loop(self):
        """Test that dashboard redirect chain does not loop."""
        self.client.login(username="pharma_manager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Test the exact redirect chain from the logs:
        # /verticals/pharmacy/dashboard/ -> /inventory/dashboard/ -> /dashboard/

        # 1. Pharmacy dashboard
        try:
            response = self.client.get(reverse("verticals:pharmacy_dashboard"), follow=True)
            self.assertEqual(response.status_code, 200, "Pharmacy dashboard redirect chain should end in 200")

            # Check redirect chain length (should be short, not infinite)
            if hasattr(response, "redirect_chain"):
                self.assertLess(len(response.redirect_chain), 5, "Should not have long redirect chain")
        except RecursionError as e:
            self.fail(f"RecursionError in redirect chain: {e}")

        # 2. Inventory dashboard
        try:
            response = self.client.get("/inventory/dashboard/", follow=True)
            self.assertEqual(response.status_code, 200, "/inventory/dashboard/ should resolve")
        except RecursionError as e:
            self.fail(f"RecursionError at /inventory/dashboard/: {e}")

        # 3. Main dashboard
        try:
            response = self.client.get("/dashboard/", follow=True)
            self.assertEqual(response.status_code, 200, "/dashboard/ should resolve")
        except RecursionError as e:
            self.fail(f"RecursionError at /dashboard/: {e}")

    @override_settings(DEBUG=False)
    def test_pharmacy_fast_sell_production_mode(self):
        """Test pharmacy fast sell in production mode (DEBUG=False)."""
        # The recursion error was reported in production
        self.client.login(username="pharma_manager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell"))

            # Should not raise RecursionError even in production mode
            self.assertEqual(response.status_code, 200, "Fast sell should work in production mode")

        except RecursionError as e:
            self.fail(f"RecursionError in production mode: {e}")


@pytest.mark.skipif(not PHARMACY_AVAILABLE, reason="Pharmacy models not available")
class TestPharmacyTemplateIncludes(TestCase):
    """
    Test that pharmacy templates don't have circular includes.
    """

    def setUp(self):
        """Set up minimal test scenario."""
        self.business = Business.objects.create(
            name="Test Pharmacy 2",
            slug="test-pharmacy-2",
            kind="pharmacy",
            status="ACTIVE",
        )

        self.user = User.objects.create_user(
            username="pharma_user",
            email="user@test.com",
            password="testpass123",
        )

        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client = Client()

    def test_payment_mix_bar_include_works(self):
        """Test that payment_mix_bar.html include doesn't cause recursion."""
        # The fast_sell.html template includes "payments/_payment_mix_bar.html"
        # at line 414. This include must not cause recursion.

        self.client.login(username="pharma_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell"))

            # Should render without error
            self.assertEqual(response.status_code, 200)

            # Check that payment mix elements are present
            content = response.content.decode("utf-8")
            self.assertIn("payment", content.lower(), "Payment mix should be included")

        except RecursionError as e:
            self.fail(f"Template include caused RecursionError: {e}")

    def test_base_html_extends_works(self):
        """Test that base.html extends doesn't cause recursion."""
        # fast_sell.html extends base.html
        # base.html must not have circular extends

        self.client.login(username="pharma_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        try:
            response = self.client.get(reverse("verticals:pharmacy_fast_sell"))

            # Should render without error
            self.assertEqual(response.status_code, 200)

            # Check for base template elements
            content = response.content.decode("utf-8")
            self.assertIn("<!doctype html>", content.lower(), "Should have HTML doctype from base.html")

        except RecursionError as e:
            self.fail(f"Template extends caused RecursionError: {e}")
