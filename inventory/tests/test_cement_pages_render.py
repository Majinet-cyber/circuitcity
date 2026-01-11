# inventory/tests/test_cement_pages_render.py
"""
Regression tests to prevent cement templates from returning 500 errors.

These tests ensure that:
1. /cement/products/ (products_catalog) returns 200 (no missing |get_item filter)
2. /cement/stock/ (stock_list) returns 200 (no missing |mul filter)
3. Required template filters are loaded and working correctly

This prevents regressions where missing {% load %} tags cause TemplateSyntaxError.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementPagesRender(TestCase):
    """Test that cement pages render without 500 errors (template filter regression tests)"""

    def setUp(self):
        """Create cement business, manager, and test fixtures"""
        self.user = User.objects.create_user(
            username="cement_manager",
            email="manager@cement.test",
            password="test1234",
        )
        self.business = Business.objects.create(
            name="Cement Hardware Store",
            slug="cement-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
        )

        # Create test products for stock list
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement 50kg",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            cost_price=Decimal("25000.00"),
            selling_price=Decimal("30000.00"),
            quantity_in_stock=100,
            base_unit="bag",
            is_active=True,
            track_inventory=True,
        )

        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name="Lafarge Cement 50kg",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            cost_price=Decimal("24000.00"),
            selling_price=Decimal("29000.00"),
            quantity_in_stock=50,
            base_unit="bag",
            is_active=True,
            track_inventory=True,
        )

        self.client = Client()

    def test_products_catalog_renders_successfully(self):
        """
        Test /cement/products/ returns 200.

        This endpoint uses |get_item filter in products_catalog.html.
        Regression: TemplateSyntaxError if {% load cc_extras %} is missing.
        """
        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET products catalog
        response = self.client.get(reverse("cement:products_catalog"))

        # Should return 200, not 500 (TemplateSyntaxError: Invalid filter: 'get_item')
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. "
            "Check that {% load cc_extras %} is present in products_catalog.html"
        )

        # Verify template rendered correctly
        assert b"Hardware Products Catalog" in response.content or b"Products Catalog" in response.content

    def test_stock_list_renders_successfully(self):
        """
        Test /cement/stock/ returns 200.

        This endpoint uses |mul filter in stock_list.html to calculate stock value.
        Regression: TemplateSyntaxError if {% load cc_extras %} is missing.
        """
        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET stock list
        response = self.client.get(reverse("cement:stock_list"))

        # Should return 200, not 500 (TemplateSyntaxError: Invalid filter: 'mul')
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. "
            "Check that {% load cc_extras %} is present in stock_list.html"
        )

        # Verify template rendered correctly with products
        assert b"Dangote Cement" in response.content
        assert b"Lafarge Cement" in response.content

        # Verify |mul filter calculated stock values correctly
        # Product 1: 100 bags * 25000 = 2,500,000
        # Product 2: 50 bags * 24000 = 1,200,000
        # Values should be formatted with commas by intcomma filter
        assert b"2,500,000" in response.content or b"2500000" in response.content
        assert b"1,200,000" in response.content or b"1200000" in response.content

    def test_products_catalog_with_search(self):
        """Test products catalog search functionality doesn't crash"""
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET with search query
        response = self.client.get(reverse("cement:products_catalog") + "?q=paint")

        assert response.status_code == 200
        # Search results should render (may be empty, but page should load)

    def test_products_catalog_with_category_filter(self):
        """Test products catalog category filtering doesn't crash"""
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET with category filter (uses |get_item in template)
        response = self.client.get(reverse("cement:products_catalog") + "?category=cement")

        assert response.status_code == 200

    def test_stock_list_with_zero_stock(self):
        """Test stock list renders correctly when product has zero stock (edge case for |mul)"""
        # Create product with zero stock
        MerchProduct.objects.create(
            business=self.business,
            name="Zero Stock Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            cost_price=Decimal("20000.00"),
            selling_price=Decimal("25000.00"),
            quantity_in_stock=0,  # Zero stock
            base_unit="bag",
            is_active=True,
            track_inventory=True,
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("cement:stock_list"))

        assert response.status_code == 200
        # |mul filter should handle 0 * price = 0 correctly
        assert b"Zero Stock Cement" in response.content

    def test_stock_list_with_no_products(self):
        """Test stock list renders empty state when no products exist"""
        # Delete all products
        MerchProduct.objects.filter(business=self.business).delete()

        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("cement:stock_list"))

        assert response.status_code == 200
        # Should show empty state
        assert b"No products yet" in response.content or b"no products" in response.content.lower()


@pytest.mark.django_db
class TestCementPagesAuthentication(TestCase):
    """Test that cement pages require authentication and proper business kind"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="user",
            email="user@test.com",
            password="test1234",
        )
        self.cement_business = Business.objects.create(
            name="Cement Store",
            slug="cement-store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        self.grocery_business = Business.objects.create(
            name="Grocery Store",
            slug="grocery-store",
            business_kind=BusinessKind.GROCERY,
            status="ACTIVE",
        )
        self.client = Client()

    def test_products_catalog_requires_login(self):
        """Test that products catalog redirects to login if not authenticated"""
        response = self.client.get(reverse("cement:products_catalog"))

        # Should redirect to login
        assert response.status_code == 302
        assert "login" in response.url

    def test_stock_list_requires_login(self):
        """Test that stock list redirects to login if not authenticated"""
        response = self.client.get(reverse("cement:stock_list"))

        # Should redirect to login
        assert response.status_code == 302
        assert "login" in response.url

    def test_cement_pages_require_cement_business(self):
        """Test that cement pages reject non-cement businesses (403 or redirect)"""
        # Create membership for grocery business (not cement)
        Membership.objects.create(
            user=self.user,
            business=self.grocery_business,
            role="MANAGER",
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.grocery_business.id
        session.save()

        # Try to access cement pages with grocery business
        response_products = self.client.get(reverse("cement:products_catalog"))
        response_stock = self.client.get(reverse("cement:stock_list"))

        # Should be rejected (403 or redirect)
        # The exact status depends on your @require_business_kind implementation
        assert response_products.status_code in (302, 403, 404)
        assert response_stock.status_code in (302, 403, 404)

