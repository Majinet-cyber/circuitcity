# tests/test_marketplace_upgrade.py
"""
Tests for marketplace upgrade: status workflow, listing_slug, images, vertical_metadata.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models_marketplace import (
    MarketplaceListing,
    MarketplaceListingImage,
    MarketplaceEnquiry,
    ListingStatus,
)

User = get_user_model()


def _make_business(slug="mkt-shop"):
    return Business.objects.create(
        name=f"Market Shop {slug}",
        slug=slug,
        business_kind="phones",
    )


def _make_manager(username="mkt_mgr"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


def _make_membership(user, business):
    return Membership.objects.create(
        user=user,
        business=business,
        role="manager",
        status="ACTIVE",
    )


# ---------------------------------------------------------------------------
# ListingStatus Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class ListingStatusTests(TestCase):
    def test_status_choices_exist(self):
        expected = {"draft", "live", "offline", "sold", "out_of_stock"}
        actual = {choice[0] for choice in ListingStatus.choices}
        self.assertTrue(expected.issubset(actual))

    def test_default_status_is_draft(self):
        biz = _make_business()
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Test Item",
        )
        self.assertEqual(listing.status, "draft")

    def test_is_active_property_true_when_live(self):
        biz = _make_business(slug="biz-live")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Live Item",
            status="live",
        )
        self.assertTrue(listing.is_active)

    def test_is_active_property_false_when_offline(self):
        biz = _make_business(slug="biz-offline")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Offline Item",
            status="offline",
        )
        self.assertFalse(listing.is_active)

    def test_is_active_setter_true_sets_live(self):
        biz = _make_business(slug="biz-setter1")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Setter Test",
            status="draft",
        )
        listing.is_active = True
        listing.save()
        listing.refresh_from_db()
        self.assertEqual(listing.status, "live")

    def test_is_active_setter_false_sets_offline(self):
        biz = _make_business(slug="biz-setter2")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Setter Test 2",
            status="live",
        )
        listing.is_active = False
        listing.save()
        listing.refresh_from_db()
        self.assertEqual(listing.status, "offline")


# ---------------------------------------------------------------------------
# listing_slug Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class ListingSlugTests(TestCase):
    def test_slug_auto_generated_from_title(self):
        biz = _make_business(slug="slug-shop")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="iPhone 14 Pro Max",
        )
        self.assertIn("iphone", listing.listing_slug.lower())

    def test_slug_is_unique_per_business(self):
        biz = _make_business(slug="slug-shop2")
        l1 = MarketplaceListing.objects.create(business=biz, title="Same Title")
        l2 = MarketplaceListing.objects.create(business=biz, title="Same Title")
        self.assertNotEqual(l1.listing_slug, l2.listing_slug)


# ---------------------------------------------------------------------------
# vertical_metadata Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class VerticalMetadataTests(TestCase):
    def test_vertical_metadata_stores_dict(self):
        biz = _make_business(slug="meta-shop")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Toyota Corolla",
            vertical="car_dealer",
            vertical_metadata={
                "make": "Toyota",
                "model": "Corolla",
                "year": 2019,
                "mileage": 85000,
            },
        )
        listing.refresh_from_db()
        self.assertEqual(listing.vertical_metadata["make"], "Toyota")
        self.assertEqual(listing.vertical_metadata["year"], 2019)

    def test_vertical_metadata_defaults_to_empty_dict(self):
        biz = _make_business(slug="meta-shop2")
        listing = MarketplaceListing.objects.create(business=biz, title="Test")
        self.assertIsInstance(listing.vertical_metadata, dict)


# ---------------------------------------------------------------------------
# Contact fields Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class ListingContactFieldsTests(TestCase):
    def test_contact_fields_stored(self):
        biz = _make_business(slug="contact-shop")
        listing = MarketplaceListing.objects.create(
            business=biz,
            title="Test Item",
            contact_phone="+265991234567",
            contact_email="shop@example.com",
            address="Area 3, Lilongwe",
            location_text="Near Area 3 roundabout",
        )
        listing.refresh_from_db()
        self.assertEqual(listing.contact_phone, "+265991234567")
        self.assertEqual(listing.contact_email, "shop@example.com")
        self.assertIn("Lilongwe", listing.address)


# ---------------------------------------------------------------------------
# MarketplaceListingImage Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplaceListingImageTests(TestCase):
    def setUp(self):
        self.biz = _make_business(slug="img-shop")
        self.listing = MarketplaceListing.objects.create(
            business=self.biz,
            title="Test Listing",
            status="live",
        )

    def test_can_create_listing_image(self):
        img = MarketplaceListingImage.objects.create(
            listing=self.listing,
            sort_order=0,
        )
        self.assertEqual(img.listing, self.listing)

    def test_multiple_images_per_listing(self):
        for i in range(3):
            MarketplaceListingImage.objects.create(listing=self.listing, sort_order=i)
        self.assertEqual(
            MarketplaceListingImage.objects.filter(listing=self.listing).count(), 3
        )

    def test_images_deleted_with_listing(self):
        MarketplaceListingImage.objects.create(listing=self.listing, sort_order=0)
        listing_id = self.listing.pk
        self.listing.delete()
        self.assertEqual(
            MarketplaceListingImage.objects.filter(listing_id=listing_id).count(), 0
        )


# ---------------------------------------------------------------------------
# Public View Tests (with new status workflow)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class MarketplacePublicStatusTests(TestCase):
    def setUp(self):
        self.biz = _make_business(slug="pub-shop")
        self.live_listing = MarketplaceListing.objects.create(
            business=self.biz, title="Live Product", status="live",
        )
        self.draft_listing = MarketplaceListing.objects.create(
            business=self.biz, title="Draft Product", status="draft",
        )
        self.sold_listing = MarketplaceListing.objects.create(
            business=self.biz, title="Sold Product", status="sold",
        )
        self.client = Client()

    def test_public_page_shows_live_listings_only(self):
        url = reverse("inventory:marketplace_public")
        response = self.client.get(url)
        self.assertContains(response, "Live Product")
        self.assertNotContains(response, "Draft Product")
        self.assertNotContains(response, "Sold Product")

    def test_business_page_shows_live_listings_only(self):
        url = reverse("inventory:business_public_page", args=[self.biz.slug])
        response = self.client.get(url)
        self.assertContains(response, "Live Product")
        self.assertNotContains(response, "Draft Product")


# ---------------------------------------------------------------------------
# Toggle Status Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class ToggleListingStatusTests(TestCase):
    def setUp(self):
        self.user = _make_manager()
        self.biz = _make_business(slug="toggle-shop")
        _make_membership(self.user, self.biz)
        self.listing = MarketplaceListing.objects.create(
            business=self.biz,
            title="Toggle Test",
            status="draft",
        )
        self.client = Client()
        self.client.login(username="mkt_mgr", password="testpass123")

    def test_toggle_to_live(self):
        url = reverse("inventory:marketplace_toggle_status", args=[self.listing.id])
        self.client.post(url, {"status": "live"})
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "live")

    def test_toggle_to_offline(self):
        self.listing.status = "live"
        self.listing.save()
        url = reverse("inventory:marketplace_toggle_status", args=[self.listing.id])
        self.client.post(url, {"status": "offline"})
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "offline")

    def test_toggle_requires_auth(self):
        anon = Client()
        url = reverse("inventory:marketplace_toggle_status", args=[self.listing.id])
        response = anon.post(url, {"status": "live"})
        self.assertEqual(response.status_code, 302)
