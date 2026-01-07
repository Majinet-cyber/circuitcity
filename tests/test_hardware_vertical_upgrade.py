# tests/test_hardware_vertical_upgrade.py
"""
Tests for Hardware & General Dealers Vertical Upgrade
======================================================

Tests cover:
1. Display name mapping (no "Cement Store" visible)
2. Sidebar visibility (Products tab only for hardware vertical)
3. Product catalog functionality
4. No vertical leakage
5. No regressions (existing cement data still works)
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.catalog.hardware import (
    get_catalog_products,
    get_popular_products,
    get_product_by_slug,
    get_products_by_category,
    search_products,
)
from inventory.utils_verticals import get_vertical_display_name, get_vertical_sidebar_items
from tenants.models import Business

User = get_user_model()


class HardwareDisplayNameTest(TestCase):
    """Test that display name is correctly mapped to 'Hardware & General Dealers'"""

    def test_vertical_display_name_mapping(self):
        """Cement vertical code should display as 'Hardware & General Dealers'"""
        display_name = get_vertical_display_name("cement")
        self.assertEqual(display_name, "Hardware & General Dealers")
        # Ensure no "Cement Store" is returned
        self.assertNotIn("Cement Store", display_name)

    def test_business_kind_choices_label(self):
        """BusinessKind.CEMENT should have correct label"""
        cement_label = None
        for value, label in BusinessKind.choices:
            if value == "cement":
                cement_label = label
                break

        self.assertIsNotNone(cement_label)
        self.assertEqual(cement_label, "Hardware & General Dealers")
        self.assertNotIn("Cement", cement_label)


class HardwareSidebarVisibilityTest(TestCase):
    """Test that Products tab appears only for hardware vertical"""

    def test_products_tab_visible_for_hardware(self):
        """Hardware businesses should see Products tab in sidebar"""
        sidebar_items = get_vertical_sidebar_items("cement")

        # Find Products tab
        products_tab = None
        for item in sidebar_items:
            if item.get("key") == "products":
                products_tab = item
                break

        self.assertIsNotNone(products_tab, "Products tab should exist for hardware vertical")
        self.assertEqual(products_tab["label"], "Products")
        self.assertEqual(products_tab["url"], "cement:products_catalog")
        self.assertIn("products", products_tab["active_prefix"])

    def test_products_tab_not_visible_for_other_verticals(self):
        """Other verticals should NOT see hardware Products tab"""
        other_verticals = ["phones", "clothing", "liquor", "pharmacy", "gym", "grocery"]

        for vertical in other_verticals:
            sidebar_items = get_vertical_sidebar_items(vertical)

            # Ensure no Products tab pointing to cement catalog
            for item in sidebar_items:
                if item.get("key") == "products":
                    # If there's a products key, ensure it doesn't point to cement catalog
                    self.assertNotEqual(
                        item.get("url"),
                        "cement:products_catalog",
                        f"{vertical} vertical should not have cement products catalog",
                    )


class HardwareCatalogFunctionalityTest(TestCase):
    """Test hardware product catalog functionality"""

    def test_catalog_has_products(self):
        """Catalog should contain hardware products"""
        products = get_catalog_products()
        self.assertGreater(len(products), 0, "Catalog should have products")

        # Verify product structure
        for product in products[:5]:  # Check first 5
            self.assertIn("slug", product)
            self.assertIn("category", product)
            self.assertIn("base_name", product)
            self.assertIn("keywords", product)
            self.assertIn("default_unit", product)
            self.assertIn("variation_schema", product)

    def test_catalog_categories(self):
        """Catalog should have all required categories"""
        required_categories = [
            "construction",
            "car-spares",
            "welding",
            "safety",
            "carpentry",
        ]

        products = get_catalog_products()
        found_categories = set(p["category"] for p in products)

        for cat in required_categories:
            self.assertIn(cat, found_categories, f"Category '{cat}' should exist in catalog")

    def test_get_products_by_category(self):
        """Should filter products by category"""
        construction_products = get_products_by_category("construction")
        self.assertGreater(len(construction_products), 0)

        # All returned products should be in construction category
        for product in construction_products:
            self.assertEqual(product["category"], "construction")

    def test_get_product_by_slug(self):
        """Should retrieve product by slug"""
        # Test with known products
        cement = get_product_by_slug("cement")
        self.assertIsNotNone(cement)
        self.assertEqual(cement["base_name"], "Cement")

        paint = get_product_by_slug("paint")
        self.assertIsNotNone(paint)
        self.assertEqual(paint["base_name"], "Paint")

        # Test with non-existent slug
        fake = get_product_by_slug("nonexistent-product-xyz")
        self.assertIsNone(fake)

    def test_search_products(self):
        """Should search products by name and keywords"""
        # Search by base name
        results = search_products("paint")
        self.assertGreater(len(results), 0)
        found_paint = any(p["base_name"].lower() == "paint" for p in results)
        self.assertTrue(found_paint)

        # Search by keyword
        results = search_products("rainbow")
        self.assertGreater(len(results), 0)
        # Rainbow is a paint brand keyword
        found_paint_with_rainbow = any("rainbow" in p["keywords"] for p in results)
        self.assertTrue(found_paint_with_rainbow)

    def test_get_popular_products(self):
        """Should return popular products"""
        popular = get_popular_products(limit=12)
        self.assertEqual(len(popular), 12)

        # Test custom limit
        popular_5 = get_popular_products(limit=5)
        self.assertEqual(len(popular_5), 5)

    def test_no_duplicate_base_names(self):
        """Catalog should not have duplicate base product names"""
        products = get_catalog_products()
        base_names = [p["base_name"] for p in products]

        # Check for duplicates
        seen = set()
        duplicates = []
        for name in base_names:
            if name in seen:
                duplicates.append(name)
            seen.add(name)

        self.assertEqual(
            len(duplicates), 0, f"Found duplicate base names: {duplicates}. Each product should appear once."
        )


class HardwareCatalogViewsTest(TestCase):
    """Test catalog views are accessible and gated correctly"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="hardware_user", email="hardware@test.com", password="testpass123"
        )
        self.hardware_business = Business.objects.create(
            name="Test Hardware Store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        self.hardware_business.members.add(self.user)

        # Create a non-hardware business for leakage tests
        self.phones_business = Business.objects.create(
            name="Test Phone Store",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE",
        )
        self.phones_business.members.add(self.user)

    def test_products_catalog_accessible_for_hardware(self):
        """Hardware businesses should access products catalog"""
        self.client.login(username="hardware_user", password="testpass123")

        # Set hardware business context
        session = self.client.session
        session["active_business_id"] = self.hardware_business.id
        session.save()

        response = self.client.get(reverse("cement:products_catalog"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hardware Products Catalog")

    def test_products_catalog_blocked_for_non_hardware(self):
        """Non-hardware businesses should NOT access hardware catalog"""
        self.client.login(username="hardware_user", password="testpass123")

        # Set phones business context
        session = self.client.session
        session["active_business_id"] = self.phones_business.id
        session.save()

        # Should be blocked by @require_business_kind decorator
        response = self.client.get(reverse("cement:products_catalog"))
        # Expect redirect or 403
        self.assertIn(response.status_code, [302, 403])

    def test_product_detail_accessible(self):
        """Product detail page should load for hardware businesses"""
        self.client.login(username="hardware_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.hardware_business.id
        session.save()

        response = self.client.get(reverse("cement:product_detail", kwargs={"slug": "paint"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paint")
        self.assertContains(response, "Select Brand")

    def test_product_detail_with_invalid_slug(self):
        """Invalid product slug should return 404"""
        self.client.login(username="hardware_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.hardware_business.id
        session.save()

        response = self.client.get(reverse("cement:product_detail", kwargs={"slug": "nonexistent-xyz"}))
        self.assertEqual(response.status_code, 404)


class HardwareNoRegressionsTest(TestCase):
    """Test that existing cement/hardware functionality still works"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="cement_user", email="cement@test.com", password="testpass123")
        self.business = Business.objects.create(
            name="Legacy Cement Store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        self.business.members.add(self.user)

    def test_cement_dashboard_still_works(self):
        """Existing cement dashboard should still be accessible"""
        self.client.login(username="cement_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("verticals:cement_dashboard"))
        self.assertEqual(response.status_code, 200)
        # Should show new display name
        self.assertContains(response, "Hardware & General Dealers")

    def test_cement_stock_in_still_works(self):
        """Existing stock-in flow should still work"""
        self.client.login(username="cement_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("cement:stock_in"))
        self.assertEqual(response.status_code, 200)

    def test_cement_sell_still_works(self):
        """Existing sell flow should still work"""
        self.client.login(username="cement_user", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("cement:sell"))
        self.assertEqual(response.status_code, 200)


class HardwareSignupTest(TestCase):
    """Test that Hardware & General Dealers appears in signup"""

    def test_signup_form_includes_hardware(self):
        """Signup form should include Hardware & General Dealers option"""
        response = self.client.get(reverse("accounts:signup_manager"))
        self.assertEqual(response.status_code, 200)

        # Check that the new label appears
        self.assertContains(response, "Hardware & General Dealers")

        # Check that old label doesn't appear
        self.assertNotContains(response, "Cement Store")


class HardwareVerticalLeakageTest(TestCase):
    """Test that hardware catalog doesn't leak to other verticals"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="test_user", email="test@test.com", password="testpass123")

    def test_phones_vertical_no_hardware_products(self):
        """Phones vertical should not see hardware products tab"""
        business = Business.objects.create(
            name="Test Phones",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE",
        )
        business.members.add(self.user)

        sidebar_items = get_vertical_sidebar_items("phones")

        # Check that cement catalog URL is not in sidebar
        for item in sidebar_items:
            self.assertNotEqual(item.get("url"), "cement:products_catalog")

    def test_clothing_vertical_no_hardware_products(self):
        """Clothing vertical should not see hardware products tab"""
        sidebar_items = get_vertical_sidebar_items("clothing")

        for item in sidebar_items:
            self.assertNotEqual(item.get("url"), "cement:products_catalog")

    def test_liquor_vertical_no_hardware_products(self):
        """Liquor vertical should not see hardware products tab"""
        sidebar_items = get_vertical_sidebar_items("liquor")

        for item in sidebar_items:
            self.assertNotEqual(item.get("url"), "cement:products_catalog")
