"""
Tests for Clothing Category System — Part 5 of the Farm/Emajinet upgrade.

Covers:
- get_category_display for predefined categories
- get_category_display fallback for custom/slugified categories (hyphen fix)
- get_category_icon
- generate_auto_description builder
- CLOTHING_SUBTYPES coverage
- Clothing scan-in form: Other requires custom_category
- Clothing scan-in form: predefined category saves normally
- Custom category slug stored correctly (≤ 30 chars)
- Custom category displayed correctly in inventory context
- Product name built from brand + subtype + category
- deep field (item_subtype) saved in product
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.clothing_config import (
    generate_auto_description,
    get_category_display,
    get_category_icon,
    get_subtypes_for_category,
    CLOTHING_CATEGORIES,
    CLOTHING_SUBTYPES,
)
from inventory.models import MerchProduct
from tenants.models import Business

User = get_user_model()

SCAN_IN_URL = "verticals:clothing_scan_in"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_business_and_user(username="cat_test"):
    user = User.objects.create_user(username=username, password="pass9999")
    biz = Business.objects.create(
        name=f"CatTestShop {username}",
        slug=f"cat-test-shop-{username}",
        business_kind=BusinessKind.CLOTHING,
        created_by=user,
        status="ACTIVE",
    )
    user.active_business = biz
    user.save()
    return user, biz


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests (no DB required)
# ─────────────────────────────────────────────────────────────────────────────


class GetCategoryDisplayTest(TestCase):
    """get_category_display returns correct human-readable names."""

    def test_predefined_shirt(self):
        self.assertEqual(get_category_display("shirt"), "Shirt")

    def test_predefined_dress(self):
        self.assertEqual(get_category_display("dress"), "Dress")

    def test_predefined_sneaker(self):
        self.assertEqual(get_category_display("sneaker"), "Sneakers")

    def test_predefined_perfume(self):
        self.assertEqual(get_category_display("perfume"), "Perfume")

    def test_predefined_other(self):
        self.assertEqual(get_category_display("other"), "Other")

    def test_custom_slug_single_word(self):
        """'hats' → 'Hats'"""
        self.assertEqual(get_category_display("hats"), "Hats")

    def test_custom_slug_hyphenated(self):
        """'soccer-jerseys' → 'Soccer Jerseys' (NOT 'Soccer-Jerseys')"""
        result = get_category_display("soccer-jerseys")
        self.assertEqual(result, "Soccer Jerseys")
        self.assertNotIn("-", result)

    def test_custom_slug_multi_word(self):
        """'swim-wear' → 'Swim Wear'"""
        result = get_category_display("swim-wear")
        self.assertEqual(result, "Swim Wear")

    def test_custom_slug_underscored(self):
        """'school_uniforms' → 'School Uniforms'"""
        result = get_category_display("school_uniforms")
        self.assertEqual(result, "School Uniforms")

    def test_empty_string(self):
        self.assertEqual(get_category_display(""), "")

    def test_all_predefined_categories_return_non_empty(self):
        for val, display, _, _ in CLOTHING_CATEGORIES:
            result = get_category_display(val)
            self.assertTrue(result, f"Empty display for category '{val}'")
            self.assertNotIn("-", result, f"Hyphen in display for predefined category '{val}'")


class GetCategoryIconTest(TestCase):
    """get_category_icon returns emoji for known categories."""

    def test_shirt_icon(self):
        self.assertEqual(get_category_icon("shirt"), "👔")

    def test_sneaker_icon(self):
        self.assertEqual(get_category_icon("sneaker"), "👟")

    def test_unknown_returns_default(self):
        self.assertEqual(get_category_icon("not-a-real-category"), "👕")


class GetSubtypesForCategoryTest(TestCase):
    """get_subtypes_for_category returns correct subtypes."""

    def test_shirt_has_subtypes(self):
        subtypes = get_subtypes_for_category("shirt")
        self.assertIsInstance(subtypes, list)
        self.assertGreater(len(subtypes), 0)

    def test_jeans_has_subtypes(self):
        subtypes = get_subtypes_for_category("jeans")
        self.assertIn("Skinny Jeans", subtypes)

    def test_unknown_category_returns_empty(self):
        subtypes = get_subtypes_for_category("not-a-category")
        self.assertEqual(subtypes, [])

    def test_other_returns_empty(self):
        subtypes = get_subtypes_for_category("other")
        self.assertEqual(subtypes, [])


class GenerateAutoDescriptionTest(TestCase):
    """generate_auto_description builds clean product descriptions."""

    def test_full_attributes(self):
        result = generate_auto_description(
            category="shirt",
            brand="Lacoste",
            item_subtype="Polo Shirt",
            size="M",
            color="Navy",
        )
        self.assertIn("Lacoste", result)
        self.assertIn("Polo Shirt", result)
        self.assertIn("Navy", result)
        self.assertIn("M", result)

    def test_custom_other_category(self):
        result = generate_auto_description(
            category="other",
            custom_category="Soccer Jerseys",
            brand="Adidas",
            size="L",
            color="Green",
        )
        self.assertIn("Adidas", result)
        self.assertIn("Green", result)

    def test_minimal_just_category(self):
        result = generate_auto_description(category="dress")
        self.assertEqual(result, "Dress")

    def test_color_other_excluded(self):
        result = generate_auto_description(category="shirt", color="Other")
        # "Other" color should not appear as a word in description
        self.assertNotIn("Other", result)

    def test_size_appended_with_label(self):
        result = generate_auto_description(category="sneaker", size="42")
        self.assertIn("42", result)

    def test_empty_returns_empty(self):
        result = generate_auto_description(category="")
        self.assertEqual(result, "")

    def test_no_empty_parts_in_result(self):
        result = generate_auto_description(
            category="jacket",
            brand="",
            item_subtype="",
            size="",
            color="",
        )
        # Should not have leading/trailing spaces or doubled spaces
        self.assertEqual(result, result.strip())
        self.assertNotIn("  ", result)


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (DB + HTTP)
# ─────────────────────────────────────────────────────────────────────────────


class ScanInOtherCategoryTest(TestCase):
    """Clothing scan-in flow: 'Other' category requires custom_category."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("scan_other1")
        self.client.login(username="scan_other1", password="pass9999")
        self.url = reverse(SCAN_IN_URL)

    def _post(self, **overrides):
        data = {
            "category": "other",
            "custom_category": "Soccer Jerseys",
            "brand": "",
            "item_subtype": "",
            "size": "M",
            "color": "Black",
            "quantity": 3,
            "cost_price": "2000.00",
            "selling_price": "",
            "description": "",
            "has_barcode": "no",
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_other_without_custom_fails_validation(self):
        resp = self._post(custom_category="")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MerchProduct.objects.filter(business=self.biz).exists())

    def test_other_with_custom_creates_product(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        # Category slug, not "other"
        self.assertNotEqual(p.category, "other")
        self.assertIn("soccer", p.category)

    def test_custom_category_slug_max_30_chars(self):
        resp = self._post(custom_category="A Very Long Category Name Beyond Thirty Chars")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertLessEqual(len(p.category), 30)

    def test_custom_category_display_name_in_product_name(self):
        self._post(custom_category="Swim Wear")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertIn("Swim Wear", p.name)

    def test_category_stored_as_slug_not_display(self):
        """Stored category should be a slug, not have spaces."""
        self._post(custom_category="School Uniforms")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        # Slug: 'school-uniforms'
        self.assertNotIn(" ", p.category)


class ScanInPredefinedCategoryTest(TestCase):
    """Predefined categories save without needing custom_category."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("scan_predef")
        self.client.login(username="scan_predef", password="pass9999")
        self.url = reverse(SCAN_IN_URL)

    def _post(self, **overrides):
        data = {
            "category": "shirt",
            "custom_category": "",
            "brand": "",
            "item_subtype": "",
            "size": "L",
            "color": "White",
            "quantity": 5,
            "cost_price": "1500.00",
            "selling_price": "2500.00",
            "description": "",
            "has_barcode": "no",
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_shirt_saves_category_correctly(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.category, "shirt")

    def test_brand_saved(self):
        self._post(brand="Nike")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.brand, "Nike")

    def test_item_subtype_saved(self):
        self._post(item_subtype="Formal Shirt")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.item_type, "Formal Shirt")

    def test_brand_and_subtype_in_name(self):
        self._post(category="jeans", brand="Levi's", item_subtype="Skinny Jeans", size="32", color="Blue")
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertIn("Levi's", p.name)
        self.assertIn("Skinny Jeans", p.name)

    def test_quantity_reflects_in_stock(self):
        self._post(quantity=10)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.quantity_in_stock, 10)

    def test_stock_in_again_adds_quantity(self):
        self._post(quantity=3)
        self._post(quantity=2)  # same product (same name)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.quantity_in_stock, 5)

    def test_dress_saves(self):
        resp = self._post(category="dress", size="S", color="Red")
        self.assertEqual(resp.status_code, 200)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.category, "dress")

    def test_sneaker_saves(self):
        resp = self._post(category="sneaker", size="42", color="White")
        self.assertEqual(resp.status_code, 200)
        p = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(p)
        self.assertEqual(p.category, "sneaker")


class ScanInPageRenderTest(TestCase):
    """Scan-in page renders with correct elements."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("scan_render")
        self.client.login(username="scan_render", password="pass9999")
        self.url = reverse(SCAN_IN_URL)

    def test_page_renders_200(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_other_category_card_present(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "other")
        self.assertContains(resp, "custom-category-row")

    def test_all_predefined_categories_rendered(self):
        resp = self.client.get(self.url)
        # A representative sample of predefined categories
        for slug in ("shirt", "sneaker", "dress", "perfume"):
            self.assertContains(resp, f'data-category="{slug}"')


class CategoryDisplayInDashboardTest(TestCase):
    """Custom category products display correctly in clothing dashboard."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("dash_disp")
        self.client.login(username="dash_disp", password="pass9999")
        # Create a product with a custom (hyphenated slug) category
        MerchProduct.objects.create(
            business=self.biz,
            name="Soccer Jerseys - M - Green",
            kind=BusinessKind.CLOTHING,
            category="soccer-jerseys",
            size="M",
            color="Green",
            cost_price=Decimal("2000"),
            selling_price=Decimal("3500"),
            quantity_in_stock=5,
            is_active=True,
            track_inventory=True,
        )

    def test_dashboard_loads_without_error(self):
        resp = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_get_category_display_converts_slug(self):
        """get_category_display should not return hyphenated text."""
        result = get_category_display("soccer-jerseys")
        self.assertNotIn("-", result)
        self.assertEqual(result, "Soccer Jerseys")
