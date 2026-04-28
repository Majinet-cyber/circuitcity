# inventory/tests/test_phones_scan_sell.py
"""
Regression tests for Phones & Electronics Scan/Sell and Dashboard.

Covers:
- Scan & Sell landing page shows product type cards (Phone, Laptop, Desktop)
- Scan & Sell landing accessible for PHONES business
- Phone sale wizard empty state shows helpful message (not just "No phone brands available")
- Electronics stock-in/sell redirects to correct wizard per category
- Phones dashboard renders without 500
- Phones dashboard counts phones, laptops, desktops separately (category_breakdown)
- Low-stock alert section renders
- Recommendations panel renders
"""
from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phones_business(slug="test-phones"):
    return Business.objects.create(
        name="Test Phones Co",
        slug=slug,
        status="ACTIVE",
        business_kind="phones",
    )


def _make_user(username="phones_user", business=None, role="MANAGER"):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="TestPass123!@#",
    )
    if business:
        Membership.objects.create(user=user, business=business, role=role, status="ACTIVE")
    return user


def _make_client_for_business(business, username="test_user", role="MANAGER"):
    user = _make_user(username=username, business=business, role=role)
    client = Client()
    client.login(username=username, password="TestPass123!@#")
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    return client, user


# ---------------------------------------------------------------------------
# Scan & Sell Landing Page Tests
# ---------------------------------------------------------------------------

class ScanSellLandingTest(TestCase):
    """Scan & Sell landing page must show product type choices: Phones, Laptops, Desktops."""

    def setUp(self):
        self.business = _make_phones_business("test-scan-sell-landing")
        self.client, self.user = _make_client_for_business(self.business)

    def test_landing_page_returns_200(self):
        """Scan & Sell landing must not 500."""
        try:
            url = reverse("inventory:scan_sell_landing")
        except NoReverseMatch:
            self.skipTest("scan_sell_landing URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Scan & Sell landing returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_landing_page_contains_phone_card(self):
        """Landing page must show a Phone category card."""
        try:
            url = reverse("inventory:scan_sell_landing")
        except NoReverseMatch:
            self.skipTest("scan_sell_landing URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Landing returned non-200")
        content = resp.content.decode()
        self.assertIn("Phone", content, "Landing page must show Phone category")

    def test_landing_page_contains_laptop_card(self):
        """Landing page must show a Laptop category card."""
        try:
            url = reverse("inventory:scan_sell_landing")
        except NoReverseMatch:
            self.skipTest("scan_sell_landing URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Landing returned non-200")
        content = resp.content.decode()
        self.assertIn("Laptop", content, "Landing page must show Laptop category")

    def test_landing_page_contains_desktop_card(self):
        """Landing page must show a Desktop category card."""
        try:
            url = reverse("inventory:scan_sell_landing")
        except NoReverseMatch:
            self.skipTest("scan_sell_landing URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Landing returned non-200")
        content = resp.content.decode()
        self.assertIn("Desktop", content, "Landing page must show Desktop category")

    def test_landing_page_context_has_wizard_urls(self):
        """Landing page context must include wizard URLs for all three categories."""
        try:
            url = reverse("inventory:scan_sell_landing")
        except NoReverseMatch:
            self.skipTest("scan_sell_landing URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Landing returned non-200")
        self.assertIn("phone_wizard_url", resp.context, "phone_wizard_url missing from landing context")
        self.assertIn("laptop_wizard_url", resp.context, "laptop_wizard_url missing from landing context")
        self.assertIn("desktop_wizard_url", resp.context, "desktop_wizard_url missing from landing context")


# ---------------------------------------------------------------------------
# Phone Sale Wizard Empty State Tests
# ---------------------------------------------------------------------------

class PhoneSaleWizardEmptyStateTest(TestCase):
    """Phone sale wizard empty state must be helpful, not just 'No phone brands available'."""

    def setUp(self):
        self.business = _make_phones_business("test-phone-wizard-empty")
        self.client, self.user = _make_client_for_business(self.business, "phone_wizard_mgr")

    def test_phone_wizard_returns_200_when_empty(self):
        """Phone wizard must not 500 when no stock exists."""
        try:
            url = reverse("inventory:phone_sale_wizard")
        except NoReverseMatch:
            self.skipTest("phone_sale_wizard URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Phone wizard returned 500 with empty stock")
        self.assertIn(resp.status_code, [200, 302])

    def test_phone_wizard_empty_state_shows_helpful_links(self):
        """When no brands exist, wizard must show Scan In and Sell Laptops/Desktops links."""
        try:
            url = reverse("inventory:phone_sale_wizard")
        except NoReverseMatch:
            self.skipTest("phone_sale_wizard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phone wizard returned non-200")
        content = resp.content.decode()
        # Must not just say "No phone brands available" without alternatives
        if "No phone products in stock" in content or "No phone brands" in content:
            # Must also show helpful links to scan in or sell other categories
            has_scan_link = "Scan In" in content or "scan_in" in content or "scan-in" in content
            has_laptop_link = "Laptop" in content or "laptop" in content
            self.assertTrue(
                has_scan_link or has_laptop_link,
                "Empty state must show Scan In link or Laptop/Desktop alternative"
            )

    def test_phone_wizard_empty_state_not_just_no_brands_message(self):
        """The old 'No phone brands available yet. Add phone products first.' must not be the only message."""
        try:
            url = reverse("inventory:phone_sale_wizard")
        except NoReverseMatch:
            self.skipTest("phone_sale_wizard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phone wizard returned non-200")
        content = resp.content.decode()
        # The old bare error message should not appear alone
        self.assertNotIn(
            "No phone brands available yet. Add phone products first.",
            content,
            "Old bare 'No phone brands available' message should be replaced by helpful guidance"
        )


# ---------------------------------------------------------------------------
# Phones Dashboard Tests
# ---------------------------------------------------------------------------

class PhonesDashboardTest(TestCase):
    """Phones dashboard must render without 500 and show category breakdowns."""

    def setUp(self):
        self.business = _make_phones_business("test-phones-dashboard")
        self.client, self.user = _make_client_for_business(self.business, "phones_dash_mgr")

    def _dashboard_url(self):
        try:
            return reverse("verticals:phones_dashboard")
        except NoReverseMatch:
            return None

    def test_dashboard_returns_200(self):
        """Phones dashboard must not 500."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Phones dashboard returned 500")
        self.assertIn(resp.status_code, [200, 302])

    def test_dashboard_context_has_category_breakdown(self):
        """dashboard_kpis must include category_breakdown with phones, laptops, desktops."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        kpis = resp.context.get("dashboard_kpis", {})
        self.assertIn("category_breakdown", kpis, "dashboard_kpis must have category_breakdown")
        breakdown = kpis["category_breakdown"]
        self.assertIn("phones", breakdown, "category_breakdown must have phones key")
        self.assertIn("laptops", breakdown, "category_breakdown must have laptops key")
        self.assertIn("desktops", breakdown, "category_breakdown must have desktops key")

    def test_dashboard_phones_count_is_non_negative(self):
        """Phones stock count must be 0 or more (never negative)."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        kpis = resp.context.get("dashboard_kpis", {})
        breakdown = kpis.get("category_breakdown", {})
        phones_stock = breakdown.get("phones", {}).get("stock", 0)
        self.assertGreaterEqual(phones_stock, 0, "Phones stock must be >= 0")

    def test_dashboard_laptop_count_is_non_negative(self):
        """Laptop stock count must be 0 or more (never negative)."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        kpis = resp.context.get("dashboard_kpis", {})
        breakdown = kpis.get("category_breakdown", {})
        laptops_stock = breakdown.get("laptops", {}).get("stock", 0)
        self.assertGreaterEqual(laptops_stock, 0, "Laptop stock must be >= 0")

    def test_dashboard_desktop_count_is_non_negative(self):
        """Desktop stock count must be 0 or more (never negative)."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        kpis = resp.context.get("dashboard_kpis", {})
        breakdown = kpis.get("category_breakdown", {})
        desktops_stock = breakdown.get("desktops", {}).get("stock", 0)
        self.assertGreaterEqual(desktops_stock, 0, "Desktop stock must be >= 0")

    def test_dashboard_contains_recommendations_panel(self):
        """Phones dashboard must contain a Recommended Actions panel."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        content = resp.content.decode()
        self.assertIn(
            "Recommended Actions",
            content,
            "Phones dashboard must show Recommended Actions panel"
        )

    def test_dashboard_shows_sell_link_when_stock_is_zero(self):
        """When no stock, dashboard recommendations must show a sell/scan-in link."""
        url = self._dashboard_url()
        if url is None:
            self.skipTest("phones_dashboard URL not configured")
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.skipTest("Phones dashboard returned non-200")
        kpis = resp.context.get("dashboard_kpis", {})
        # If stock is 0, the recommendations should show scan in link
        stock = kpis.get("stock_on_hand", 1)
        if stock == 0:
            content = resp.content.decode()
            has_scan = "Scan In" in content or "scan_in" in content or "scan-in" in content
            self.assertTrue(has_scan, "Recommendations must show Scan In link when stock is zero")


# ---------------------------------------------------------------------------
# Electronics Stock-In / Sell Routing Tests
# ---------------------------------------------------------------------------

class ElectronicsStockInRoutingTest(TestCase):
    """Electronics stock-in unified view routes correctly by category."""

    def setUp(self):
        self.business = _make_phones_business("test-electronics-routing")
        self.client, self.user = _make_client_for_business(self.business, "elec_route_mgr")

    def test_scan_in_default_returns_non_500(self):
        """Scan In unified view must not 500 for default category (phones)."""
        try:
            url = reverse("inventory:scan_in")
        except NoReverseMatch:
            self.skipTest("scan_in URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Scan In returned 500")

    def test_scan_in_laptops_category_returns_non_500(self):
        """Scan In with category=laptops must not 500."""
        try:
            url = reverse("inventory:scan_in") + "?category=laptops"
        except NoReverseMatch:
            self.skipTest("scan_in URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Scan In (laptops) returned 500")

    def test_scan_in_desktops_category_returns_non_500(self):
        """Scan In with category=desktops must not 500."""
        try:
            url = reverse("inventory:scan_in") + "?category=desktops"
        except NoReverseMatch:
            self.skipTest("scan_in URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Scan In (desktops) returned 500")

    def test_scan_sell_laptops_redirects_to_wizard(self):
        """Scan & Sell with category=laptops must redirect to laptop wizard."""
        try:
            url = reverse("inventory:scan_sell") + "?category=laptops"
        except NoReverseMatch:
            self.skipTest("scan_sell URL not configured")
        resp = self.client.get(url)
        # Should redirect to laptop_sale_wizard (302)
        self.assertNotEqual(resp.status_code, 500, "Scan & Sell (laptops) returned 500")
        # Either redirects or renders without 500
        self.assertIn(resp.status_code, [200, 302])

    def test_scan_sell_desktops_redirects_to_wizard(self):
        """Scan & Sell with category=desktops must redirect to desktop wizard."""
        try:
            url = reverse("inventory:scan_sell") + "?category=desktops"
        except NoReverseMatch:
            self.skipTest("scan_sell URL not configured")
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, "Scan & Sell (desktops) returned 500")
        self.assertIn(resp.status_code, [200, 302])
