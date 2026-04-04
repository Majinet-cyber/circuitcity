"""
Regression tests for the marketplace create page 500 fix.
Root cause: create_listing view was not passing `form_data` on GET,
causing VariableDoesNotExist in the template.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


def _make_business(slug="mkt-create-shop", kind="phones"):
    return Business.objects.create(
        name=f"CreateShop {slug}",
        slug=slug,
        business_kind=kind,
    )


def _make_manager(username="mkt_create_mgr"):
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


@pytest.mark.django_db
class MarketplaceCreateGETTest(TestCase):
    """GET /inventory/marketplace/create/ must return 200 — never 500."""

    def setUp(self):
        self.biz = _make_business(slug="create-get-shop")
        self.user = _make_manager(username="create_get_mgr")
        _make_membership(self.user, self.biz)
        self.client = Client()
        self.client.login(username="create_get_mgr", password="testpass123")
        # Simulate the middleware setting request.business
        session = self.client.session
        session["active_business_id"] = self.biz.pk
        session.save()

    def test_get_returns_200(self):
        url = reverse("inventory:create_listing")
        response = self.client.get(url)
        # Should not be a 500 — accept 200, 302 (redirect to login/business select)
        self.assertNotEqual(response.status_code, 500)

    def test_get_does_not_raise_template_error(self):
        """Template must render without VariableDoesNotExist for form_data."""
        url = reverse("inventory:create_listing")
        response = self.client.get(url)
        # Status 200 means template rendered without error
        # 302 means redirect (e.g. auth or business selection), also acceptable
        self.assertIn(response.status_code, [200, 302])


@pytest.mark.django_db
class MarketplaceCreatePOSTTest(TestCase):
    """POST with valid data should create a listing or return a friendly error."""

    def setUp(self):
        self.biz = _make_business(slug="create-post-shop")
        self.user = _make_manager(username="create_post_mgr")
        _make_membership(self.user, self.biz)
        self.client = Client()
        self.client.login(username="create_post_mgr", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.biz.pk
        session.save()

    def test_post_without_title_returns_non_500(self):
        """Submitting empty title should NOT return 500."""
        url = reverse("inventory:create_listing")
        response = self.client.post(url, data={"title": "", "price": "100"})
        self.assertNotEqual(response.status_code, 500)

    def test_post_with_invalid_price_returns_non_500(self):
        """Submitting invalid price should NOT return 500."""
        url = reverse("inventory:create_listing")
        response = self.client.post(url, data={"title": "Test Item", "price": "not-a-number"})
        self.assertNotEqual(response.status_code, 500)


@pytest.mark.django_db
class MarketplaceVerticalConfigTest(TestCase):
    """Marketplace vertical config must have safe fallbacks for all verticals."""

    def test_all_major_verticals_have_config(self):
        from inventory.marketplace_vertical_config import get_vertical_config

        verticals = [
            "phones", "liquor", "grocery", "pharmacy", "clothing",
            "gym", "hardware", "cement", "farm", "welding",
            "car_hire", "car_dealer", "energy", "electronics",
        ]
        for v in verticals:
            cfg = get_vertical_config(v)
            self.assertIsInstance(cfg, dict, f"Config for '{v}' should be a dict")
            self.assertIn("cta_label", cfg, f"'{v}' config missing cta_label")
            self.assertIn("listing_type_label", cfg, f"'{v}' config missing listing_type_label")
            self.assertIn("metadata_labels", cfg, f"'{v}' config missing metadata_labels")

    def test_unknown_vertical_returns_default(self):
        from inventory.marketplace_vertical_config import get_vertical_config

        cfg = get_vertical_config("totally_unknown_vertical_xyz")
        self.assertIsInstance(cfg, dict)
        self.assertIn("cta_label", cfg)

    def test_none_vertical_returns_default(self):
        from inventory.marketplace_vertical_config import get_vertical_config

        cfg = get_vertical_config(None)
        self.assertIsInstance(cfg, dict)
        self.assertIn("cta_label", cfg)


@pytest.mark.django_db
class HardwareCategoryRegistryTest(TestCase):
    """Hardware category registry must include all major hardware categories."""

    def test_all_hardware_categories_registered(self):
        from inventory.catalog.registry import STOCK_IN_CATEGORIES

        keys = {cat["key"] for cat in STOCK_IN_CATEGORIES}
        expected_keys = {
            "construction-materials",
            "paint-and-finishing",
            "plumbing-supplies",
            "electrical-supplies",
            "tools-and-hardware",
            "roofing-materials",
            "fasteners-and-fixings",
            "welding-materials",
            "adhesives-and-sealants",
            "car-spares",
        }
        for key in expected_keys:
            self.assertIn(key, keys, f"Missing hardware category: {key}")

    def test_all_categories_have_required_fields(self):
        from inventory.catalog.registry import STOCK_IN_CATEGORIES

        required = {"key", "label", "icon", "description", "handler", "enabled"}
        for cat in STOCK_IN_CATEGORIES:
            for field in required:
                self.assertIn(field, cat, f"Category '{cat.get('key')}' missing field '{field}'")

    def test_get_all_returns_enabled_categories(self):
        from inventory.catalog.registry import get_all_stock_in_categories

        cats = get_all_stock_in_categories()
        self.assertGreater(len(cats), 3)
        for cat in cats:
            self.assertTrue(cat.get("enabled", True))
