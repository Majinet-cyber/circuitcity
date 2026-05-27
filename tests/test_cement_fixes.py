"""
Tests for Cement vertical fixes:
1. NoReverseMatch redirect fix
2. Sidebar buttons wiring
3. Paint variation grouping
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import Business, MerchProduct
from inventory.utils_product_variations import (
    extract_variation_from_name,
    get_unique_variations,
    get_variation_display,
    group_products_by_base_name,
    normalize_product_base_name,
)

User = get_user_model()


class CementRedirectFixTest(TestCase):
    """Test that cement stock-in/sell redirects work correctly (no NoReverseMatch)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="cementuser", email="cement@test.com", password="testpass123")
        self.business = Business.objects.create(
            name="Test Cement Store",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_stock_in_step1_redirect_no_error(self):
        """POST to stock-in step 1 should redirect without NoReverseMatch"""
        response = self.client.post(reverse("cement:stock_in"), {"step": "1", "brand": "Dangote"}, follow=False)

        # Should redirect (302) not crash
        self.assertEqual(response.status_code, 302)

        # Location header should contain step=2 querystring
        self.assertIn("step=2", response.url)
        self.assertIn("/cement/stock-in", response.url)

    def test_stock_in_step2_redirect_no_error(self):
        """POST to stock-in step 2 should redirect without NoReverseMatch"""
        # Set up session for step 2
        session = self.client.session
        session["cement_stock_in_brand"] = "Dangote"
        session.save()

        response = self.client.post(
            reverse("cement:stock_in"), {"step": "2", "brand": "Dangote", "product_name": "Cement 50kg"}, follow=False
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=3", response.url)

    def test_sell_step1_redirect_no_error(self):
        """POST to sell step 1 should redirect without NoReverseMatch"""
        response = self.client.post(reverse("cement:sell"), {"step": "1", "brand": "Dangote"}, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)
        self.assertIn("/cement/sell", response.url)


class CementSidebarWiringTest(TestCase):
    """Test that cement sidebar buttons are present and working"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="cementuser", email="cement@test.com", password="testpass123")
        self.business = Business.objects.create(
            name="Test Cement Store",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_cement_dashboard_has_sidebar_items(self):
        """Cement dashboard should render with sidebar nav items"""
        response = self.client.get(reverse("verticals:cement_dashboard"))

        self.assertEqual(response.status_code, 200)

        # Check sidebar_items in context
        self.assertIn("sidebar_items", response.context)
        sidebar_items = response.context["sidebar_items"]
        self.assertGreater(len(sidebar_items), 0)

        # Check specific items are present
        item_keys = [item["key"] for item in sidebar_items]
        self.assertIn("stock_in", item_keys, "Stock In button missing from sidebar")
        self.assertIn("sell", item_keys, "Sell button missing from sidebar")
        self.assertIn("costs", item_keys, "Costs button missing from sidebar")
        self.assertIn("stock", item_keys, "Stock button missing from sidebar")

    def test_cement_sidebar_items_in_html(self):
        """Sidebar items should appear in rendered HTML"""
        response = self.client.get(reverse("verticals:cement_dashboard"))
        html = response.content.decode("utf-8")

        # Check that sidebar nav items are in HTML
        self.assertIn("Stock In", html, "Stock In link not in HTML")
        self.assertIn("Sell", html, "Sell link not in HTML")
        self.assertIn("Costs", html, "Costs link not in HTML")
        self.assertIn("Stock", html, "Stock link not in HTML")

    def test_cement_sidebar_urls_resolve(self):
        """All cement sidebar URLs should resolve and return 200"""
        urls_to_test = [
            ("cement:stock_in", "Stock In"),
            ("cement:sell", "Sell"),
            ("cement:costs", "Costs"),
            ("cement:stock_list", "Stock"),
            ("cement:analytics", "Analytics"),
        ]

        for url_name, label in urls_to_test:
            with self.subTest(url=url_name):
                url = reverse(url_name)
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code, 200, f"{label} ({url_name}) should return 200, got {response.status_code}"
                )


class PaintVariationGroupingTest(TestCase):
    """Test that Paint products are grouped by base name with unique variations"""

    def setUp(self):
        self.user = User.objects.create_user(username="cementuser", email="cement@test.com", password="testpass123")
        self.business = Business.objects.create(
            name="Test Cement Store",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )

    def test_normalize_product_base_name(self):
        """normalize_product_base_name should remove size suffixes"""
        test_cases = [
            ("Paint 1L", "Paint"),
            ("Paint - 4L", "Paint"),
            ("Paint 20L", "Paint"),
            ("Dangote Cement 50kg", "Dangote Cement"),
            ("Nails 2inch", "Nails"),
        ]

        for input_name, expected_base in test_cases:
            with self.subTest(input=input_name):
                result = normalize_product_base_name(input_name)
                self.assertEqual(result, expected_base)

    def test_extract_variation_from_name(self):
        """extract_variation_from_name should extract size labels"""
        test_cases = [
            ("Paint 1L", "1L"),
            ("Paint - 4L", "4L"),
            ("Paint 20L", "20L"),
            ("Dangote Cement 50kg", "50kg"),
        ]

        for input_name, expected_variation in test_cases:
            with self.subTest(input=input_name):
                result = extract_variation_from_name(input_name)
                self.assertEqual(result, expected_variation)

    def test_get_variation_display(self):
        """get_variation_display should prioritize spec_label over name extraction"""
        # Product with spec_label
        product1 = MerchProduct.objects.create(
            business=self.business,
            name="Paint",
            spec_label="1L",
            kind=BusinessKind.CEMENT,
        )
        self.assertEqual(get_variation_display(product1), "1L")

        # Product without spec_label but with size in name
        product2 = MerchProduct.objects.create(
            business=self.business,
            name="Paint 4L",
            spec_label="",
            kind=BusinessKind.CEMENT,
        )
        self.assertEqual(get_variation_display(product2), "4L")

    def test_group_products_by_base_name(self):
        """group_products_by_base_name should group Paint 1L, 4L, 20L under 'Paint'"""
        # Create paint products with different sizes
        paint_1l = MerchProduct.objects.create(
            business=self.business,
            name="Paint 1L",
            spec_label="1L",
            kind=BusinessKind.CEMENT,
        )
        paint_4l = MerchProduct.objects.create(
            business=self.business,
            name="Paint 4L",
            spec_label="4L",
            kind=BusinessKind.CEMENT,
        )
        paint_20l = MerchProduct.objects.create(
            business=self.business,
            name="Paint 20L",
            spec_label="20L",
            kind=BusinessKind.CEMENT,
        )
        cement = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement 50kg",
            spec_label="50kg",
            kind=BusinessKind.CEMENT,
        )

        products = [paint_1l, paint_4l, paint_20l, cement]
        grouped = group_products_by_base_name(products)

        # Should have 2 groups: Paint and Dangote Cement
        self.assertEqual(len(grouped), 2)
        self.assertIn("Paint", grouped)
        self.assertIn("Dangote Cement", grouped)

        # Paint group should have 3 products
        self.assertEqual(len(grouped["Paint"]), 3)

        # Cement group should have 1 product
        self.assertEqual(len(grouped["Dangote Cement"]), 1)

    def test_get_unique_variations_no_duplicates(self):
        """get_unique_variations should return unique variations only"""
        # Create duplicate variations (should be prevented in UI)
        paint_1l_a = MerchProduct.objects.create(
            business=self.business,
            name="Paint 1L",
            spec_label="1L",
            kind=BusinessKind.CEMENT,
        )
        paint_1l_b = MerchProduct.objects.create(
            business=self.business,
            name="Paint 1L",
            spec_label="1L",
            kind=BusinessKind.CEMENT,
        )
        paint_4l = MerchProduct.objects.create(
            business=self.business,
            name="Paint 4L",
            spec_label="4L",
            kind=BusinessKind.CEMENT,
        )

        products = [paint_1l_a, paint_1l_b, paint_4l]
        unique_variations = get_unique_variations(products)

        # Should only return 2 unique variations (1L, 4L), not 3
        self.assertEqual(len(unique_variations), 2)

        # Check variation labels
        variation_labels = [v["variation"] for v in unique_variations]
        self.assertIn("1L", variation_labels)
        self.assertIn("4L", variation_labels)

    def test_cement_stock_in_shows_grouped_products(self):
        """Cement stock-in step 2 should show grouped products in context"""
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["cement_stock_in_brand"] = "Paint"
        session.save()

        # Create paint products
        MerchProduct.objects.create(
            business=self.business,
            name="Paint 1L",
            spec_label="1L",
            kind=BusinessKind.CEMENT,
        )
        MerchProduct.objects.create(
            business=self.business,
            name="Paint 4L",
            spec_label="4L",
            kind=BusinessKind.CEMENT,
        )

        response = self.client.get(f"{reverse('cement:stock_in')}?step=2")

        self.assertEqual(response.status_code, 200)
        self.assertIn("grouped_products", response.context)

        grouped = response.context["grouped_products"]
        self.assertIn("Paint", grouped)
        self.assertEqual(len(grouped["Paint"]), 2)
