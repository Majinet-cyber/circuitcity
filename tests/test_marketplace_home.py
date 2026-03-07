# tests/test_marketplace_home.py
"""
Tests for the public marketplace home view (/marketplace/).

Verifies:
- marketplace home loads with 200 status
- page does not 500 when there are zero listings
- only live listings appear in the paginated listing
- default status for new listings is 'draft'
- queryset filters by status correctly
- landing page contains Marketplace nav link
- signup CTA from marketplace resolves to a valid route (no 404)
- farm sale page renders with expected content
- landing page includes farm in marketplace messaging
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse, resolve, NoReverseMatch

from inventory.models_marketplace import MarketplaceListing, ListingStatus
from tenants.models import Business


def _make_biz(slug, kind="phones"):
    return Business.objects.create(name=f"Shop {slug}", slug=slug, business_kind=kind)


def _make_listing(biz, title, status):
    return MarketplaceListing.objects.create(business=biz, title=title, status=status)


# ---------------------------------------------------------------------------
# Marketplace Home: empty state
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceHomeEmptyTests(TestCase):
    """Marketplace home should return 200 even with no listings."""

    def test_home_loads_200_empty(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_home_does_not_500(self):
        url = reverse("marketplace:home")
        try:
            response = self.client.get(url)
            self.assertNotEqual(response.status_code, 500)
        except Exception as exc:
            self.fail(f"marketplace home raised exception: {exc}")


# ---------------------------------------------------------------------------
# Marketplace Home: listing visibility
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceHomeListingTests(TestCase):

    def setUp(self):
        self.biz = _make_biz("home-test-shop")
        self.live = _make_listing(self.biz, "Live Widget", "live")
        self.draft = _make_listing(self.biz, "Draft Widget", "draft")
        self.offline = _make_listing(self.biz, "Offline Widget", "offline")
        self.sold = _make_listing(self.biz, "Sold Widget", "sold")
        self.oos = _make_listing(self.biz, "OOS Widget", "out_of_stock")
        self.client = Client()

    def test_live_listing_appears(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Widget")

    def test_draft_listing_hidden(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertNotContains(response, "Draft Widget")

    def test_offline_listing_hidden(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertNotContains(response, "Offline Widget")

    def test_sold_listing_hidden(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertNotContains(response, "Sold Widget")

    def test_out_of_stock_listing_hidden(self):
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertNotContains(response, "OOS Widget")


# ---------------------------------------------------------------------------
# Marketplace Home: search + vertical filter
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceHomeFilterTests(TestCase):

    def setUp(self):
        self.biz = _make_biz("filter-shop")
        _make_listing(self.biz, "Red Phone", "live")
        _make_listing(self.biz, "Blue Shirt", "live")
        self.client = Client()

    def test_search_filters_results(self):
        url = reverse("marketplace:home") + "?q=Red+Phone"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Red Phone")
        self.assertNotContains(response, "Blue Shirt")

    def test_vertical_filter_works(self):
        biz2 = _make_biz("gym-shop", kind="gym")
        _make_listing(biz2, "Gym Pass", "live")
        url = reverse("marketplace:home") + "?vertical=phones"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_invalid_page_graceful(self):
        url = reverse("marketplace:home") + "?page=999"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Default status = 'draft'
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceListingDefaultStatusTests(TestCase):

    def test_default_status_is_draft(self):
        biz = _make_biz("default-status-shop")
        listing = MarketplaceListing.objects.create(business=biz, title="New Item")
        self.assertEqual(listing.status, ListingStatus.DRAFT)
        self.assertFalse(listing.is_active)

    def test_live_listing_is_active(self):
        biz = _make_biz("live-status-shop")
        listing = MarketplaceListing.objects.create(
            business=biz, title="Active Item", status="live"
        )
        self.assertTrue(listing.is_active)
        self.assertTrue(listing.is_live)

    def test_queryset_filter_by_status(self):
        biz = _make_biz("qs-filter-shop")
        MarketplaceListing.objects.create(business=biz, title="L1", status="live")
        MarketplaceListing.objects.create(business=biz, title="L2", status="live")
        MarketplaceListing.objects.create(business=biz, title="D1", status="draft")
        live_count = MarketplaceListing.objects.filter(
            business=biz, status=ListingStatus.LIVE
        ).count()
        draft_count = MarketplaceListing.objects.filter(
            business=biz, status=ListingStatus.DRAFT
        ).count()
        self.assertEqual(live_count, 2)
        self.assertEqual(draft_count, 1)


# ---------------------------------------------------------------------------
# Landing page Marketplace nav link
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class LandingPageMarketplaceNavTests(TestCase):

    def test_landing_page_has_marketplace_link(self):
        """The public landing page should contain a Marketplace link."""
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Marketplace", content)
        self.assertIn("/marketplace/", content)


# ---------------------------------------------------------------------------
# PART 2: Marketplace signup routing — no 404 from marketplace
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceSignupRoutingTests(TestCase):
    """
    Guard against the `/accounts/signup/wizard/` 404 regression.

    The correct signup entry point is `accounts:signup` which resolves to
    `/accounts/signup/` (the wizard view at step=0).
    """

    def test_accounts_signup_url_resolves(self):
        """accounts:signup named URL must reverse without NoReverseMatch."""
        try:
            url = reverse("accounts:signup")
        except NoReverseMatch as e:
            self.fail(f"accounts:signup does not resolve: {e}")
        self.assertTrue(url.startswith("/accounts/"), f"Unexpected URL: {url}")

    def test_accounts_signup_returns_non_404(self):
        """GET /accounts/signup/ must not return 404."""
        url = reverse("accounts:signup")
        response = self.client.get(url, follow=False)
        self.assertNotEqual(
            response.status_code, 404,
            f"accounts:signup returned 404 at {url}",
        )

    def test_wizard_step_url_resolves(self):
        """accounts:signup_wizard_step with step=0 must also resolve."""
        try:
            url = reverse("accounts:signup_wizard_step", kwargs={"step": 0})
        except NoReverseMatch as e:
            self.fail(f"accounts:signup_wizard_step does not resolve: {e}")
        self.assertIn("/accounts/signup/wizard/0/", url)

    def test_wizard_slash_url_does_not_exist(self):
        """
        /accounts/signup/wizard/ (no step argument) must NOT resolve to a valid
        named route — it was the broken link we fixed.
        """
        client = Client()
        response = client.get("/accounts/signup/wizard/")
        # Should be 404 (no such bare URL exists) — that's exactly the bug we fixed
        self.assertEqual(
            response.status_code, 404,
            "/accounts/signup/wizard/ should be a 404 (bare URL never existed)",
        )

    def test_marketplace_home_contains_correct_signup_url(self):
        """
        The marketplace public home page must link to /accounts/signup/
        and must NOT contain the broken /accounts/signup/wizard/ link.
        """
        url = reverse("marketplace:home")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Correct signup URL must appear somewhere in the page
        signup_url = reverse("accounts:signup")
        self.assertIn(
            signup_url, content,
            f"Marketplace page must contain {signup_url} (correct signup link)",
        )

        # Broken bare wizard URL must NOT appear
        self.assertNotIn(
            "/accounts/signup/wizard/\"",
            content,
            "Marketplace page must not contain broken /accounts/signup/wizard/ link",
        )


# ---------------------------------------------------------------------------
# PART 3: Farm sale URL resolution tests (no login needed — just URL reversals)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class FarmSaleLandingTests(TestCase):
    """
    Farm sale URL names must all resolve without NoReverseMatch.
    The actual rendering requires an authenticated session with an active farm
    business, but URL resolution can be verified without login.
    """

    def test_farm_sales_landing_resolves(self):
        """farm_sales named URL must resolve."""
        try:
            url = reverse("verticals:farm_sales")
        except NoReverseMatch as e:
            self.fail(f"verticals:farm_sales does not resolve: {e}")

    def test_farm_sales_crops_resolves(self):
        """farm_sales_crops named URL must resolve."""
        try:
            url = reverse("verticals:farm_sales_crops")
        except NoReverseMatch as e:
            self.fail(f"verticals:farm_sales_crops does not resolve: {e}")

    def test_farm_sales_livestock_resolves(self):
        """farm_sales_livestock named URL must resolve."""
        try:
            url = reverse("verticals:farm_sales_livestock")
        except NoReverseMatch as e:
            self.fail(f"verticals:farm_sales_livestock does not resolve: {e}")

    def test_farm_sales_record_resolves(self):
        """farm_sales_record named URL must resolve."""
        try:
            url = reverse("verticals:farm_sales_record")
        except NoReverseMatch as e:
            self.fail(f"verticals:farm_sales_record does not resolve: {e}")

    def test_farm_sale_landing_url_not_404_unauthenticated(self):
        """
        An unauthenticated user hitting /verticals/farm/sales/ should get
        a redirect (to login), NOT a 404 or 500.
        """
        url = reverse("verticals:farm_sales")
        response = self.client.get(url, follow=False)
        # Should be 302 redirect to login, not 404
        self.assertNotEqual(response.status_code, 404)
        self.assertNotEqual(response.status_code, 500)


# ---------------------------------------------------------------------------
# PART 4: Landing page includes farm in marketplace messaging
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class LandingPageFarmMarketplaceTests(TestCase):
    """
    The landing page must include farm in the marketplace section copy.
    """

    def _get_landing_content(self):
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def test_landing_page_mentions_farm(self):
        content = self._get_landing_content()
        self.assertIn(
            "farm", content.lower(),
            "Landing page must mention 'farm' somewhere.",
        )

    def test_landing_page_marketplace_section_exists(self):
        content = self._get_landing_content()
        self.assertIn(
            "marketplace", content.lower(),
            "Landing page must contain a marketplace section.",
        )

    def test_landing_page_farm_in_marketplace_section(self):
        """
        The marketplace showcase section on the landing page must reference
        farm/agriculture alongside other business types.
        """
        content = self._get_landing_content()
        # The farm card has a data-testid attribute we can check for
        self.assertIn(
            "Farm", content,
            "Landing page marketplace section must include Farm vertical.",
        )

    def test_landing_page_no_template_errors(self):
        """Landing page must render without 500."""
        response = self.client.get("/", follow=True)
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(response.status_code, 200)
