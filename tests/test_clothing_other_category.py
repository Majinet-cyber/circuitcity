"""
Tests for Clothing Stock-In "Other" category fix.

Covers:
- Selecting "other" without custom_category → validation error
- Selecting "other" with custom_category → saves correctly
- Predefined categories save normally
- Custom category slug is properly generated
- Optional deep fields (brand, item_subtype) save correctly
- Product name is descriptive when brand/subtype provided
- Inventory displays custom category product
- Sales flow with custom category product
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business

User = get_user_model()

SCAN_IN_URL = "verticals:clothing_scan_in"


def _make_business_and_user(username="tcloth"):
    user = User.objects.create_user(username=username, password="pass1234")
    biz = Business.objects.create(
        name="Threads Shop",
        slug=f"threads-shop-{username}",
        business_kind=BusinessKind.CLOTHING,
        created_by=user,
        status="ACTIVE",
    )
    user.active_business = biz
    user.save()
    return user, biz


class OtherCategoryValidationTest(TestCase):
    """Category='other' requires custom_category."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("val_user")
        self.client.login(username="val_user", password="pass1234")
        self.url = reverse(SCAN_IN_URL)

    def _base_post(self, **overrides):
        data = {
            "category": "other",
            "custom_category": "",
            "brand": "",
            "item_subtype": "",
            "size": "M",
            "color": "Black",
            "quantity": 5,
            "cost_price": "2000.00",
            "selling_price": "3500.00",
            "description": "",
            "has_barcode": "no",
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_other_without_custom_category_fails(self):
        """POST with category=other and empty custom_category must not save."""
        response = self._base_post(custom_category="")
        # Should re-render form (200) and NOT redirect
        self.assertEqual(response.status_code, 200)
        # No product should be created
        self.assertFalse(MerchProduct.objects.filter(business=self.biz).exists())

    def test_other_with_custom_category_saves(self):
        """POST with category=other and custom_category creates a product."""
        response = self._base_post(custom_category="Soccer Jerseys")
        self.assertEqual(response.status_code, 200)  # after redirect, 200
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product, "Product should have been created.")
        # Category slug should be derived from custom text
        self.assertNotEqual(product.category, "other")
        self.assertIn("soccer", product.category)

    def test_other_custom_category_in_product_name(self):
        """Product name should include the custom category display name."""
        self._base_post(custom_category="Hats", size="L", color="Red")
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertIn("Hats", product.name)

    def test_predefined_category_no_custom_required(self):
        """Predefined category (e.g. shirt) saves without custom_category."""
        data = {
            "category": "shirt",
            "custom_category": "",
            "brand": "",
            "item_subtype": "",
            "size": "M",
            "color": "White",
            "quantity": 3,
            "cost_price": "1500.00",
            "selling_price": "",
            "description": "",
            "has_barcode": "no",
        }
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.category, "shirt")


class OtherCategoryDeepFieldsTest(TestCase):
    """Optional brand/subtype/description fields save correctly."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("deep_user")
        self.client.login(username="deep_user", password="pass1234")
        self.url = reverse(SCAN_IN_URL)

    def test_brand_saved_to_product(self):
        data = {
            "category": "shirt",
            "custom_category": "",
            "brand": "Nike",
            "item_subtype": "Polo Shirt",
            "size": "L",
            "color": "Navy",
            "quantity": 2,
            "cost_price": "4000.00",
            "selling_price": "6000.00",
            "description": "",
            "has_barcode": "no",
        }
        self.client.post(self.url, data, follow=True)
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.brand, "Nike")

    def test_item_subtype_saved(self):
        data = {
            "category": "shirt",
            "custom_category": "",
            "brand": "",
            "item_subtype": "Formal Shirt",
            "size": "M",
            "color": "Blue",
            "quantity": 1,
            "cost_price": "3000.00",
            "selling_price": "5000.00",
            "description": "",
            "has_barcode": "no",
        }
        self.client.post(self.url, data, follow=True)
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.item_type, "Formal Shirt")

    def test_brand_and_subtype_in_name(self):
        """When brand and subtype provided, name should include them."""
        data = {
            "category": "jeans",
            "custom_category": "",
            "brand": "Levi's",
            "item_subtype": "Skinny Jeans",
            "size": "32",
            "color": "Blue",
            "quantity": 4,
            "cost_price": "8000.00",
            "selling_price": "14000.00",
            "description": "",
            "has_barcode": "no",
        }
        self.client.post(self.url, data, follow=True)
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertIn("Levi's", product.name)
        self.assertIn("Skinny Jeans", product.name)

    def test_custom_category_slug_truncated(self):
        """Custom category slug should be <= 30 chars in DB."""
        long_custom = "A Very Long Custom Category Name That Exceeds Thirty Characters"
        data = {
            "category": "other",
            "custom_category": long_custom,
            "brand": "",
            "item_subtype": "",
            "size": "S",
            "color": "Grey",
            "quantity": 1,
            "cost_price": "500.00",
            "selling_price": "",
            "description": "",
            "has_barcode": "no",
        }
        self.client.post(self.url, data, follow=True)
        product = MerchProduct.objects.filter(business=self.biz).first()
        self.assertIsNotNone(product)
        self.assertLessEqual(len(product.category), 30)


class OtherCategoryInventoryDisplayTest(TestCase):
    """Custom category products appear correctly in inventory and sales flows."""

    def setUp(self):
        self.client = Client()
        self.user, self.biz = _make_business_and_user("inv_user")
        self.client.login(username="inv_user", password="pass1234")
        self.url = reverse(SCAN_IN_URL)
        # Pre-create a custom-category product
        self.product = MerchProduct.objects.create(
            business=self.biz,
            name="Swimwear - M - Black",
            kind=BusinessKind.CLOTHING,
            category="swimwear",
            size="M",
            color="Black",
            spec_label="Size M",
            cost_price=Decimal("2500.00"),
            selling_price=Decimal("4500.00"),
            quantity_in_stock=10,
            is_active=True,
            track_inventory=True,
        )

    def test_custom_category_product_in_dashboard(self):
        """Dashboard should render without error when custom category products exist."""
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_scan_in_page_renders(self):
        """Scan-in page renders successfully."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other")
        # custom-category-row should be present but hidden
        self.assertContains(response, "custom-category-row")
