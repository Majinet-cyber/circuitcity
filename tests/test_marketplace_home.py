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
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse

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
        # Root URL redirects to staticpages:home — follow the redirect
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Marketplace", content)
        # The link should point to /marketplace/
        self.assertIn("/marketplace/", content)
