# tests/test_cement_vertical.py
"""
Tests for Cement vertical functionality.
Ensures seeding, sell guardrails, and business logic work correctly.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import CEMENT_BRANDS, seed_cement_defaults
from inventory.models import MerchProduct
from inventory.models_verticals import CementSale
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementSeeding(TestCase):
    """Test cement default product seeding"""

    def setUp(self):
        """Create a cement business and manager"""
        self.user = User.objects.create_user(
            username="cement_manager", email="manager@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Cement Test Store", slug="cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="Manager")

    def test_seed_cement_defaults_creates_all_brands(self):
        """Test that seeding creates all 9 cement brands"""
        result = seed_cement_defaults(self.business)

        assert result["created"] == 9
        assert result["skipped"] == 0

        # Verify all brands exist
        products = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT)
        assert products.count() == 9

        # Verify brand names match
        product_names = set(p.name for p in products)
        expected_names = {brand["name"] for brand in CEMENT_BRANDS}
        assert product_names == expected_names

    def test_seed_cement_defaults_is_idempotent(self):
        """Test that seeding multiple times doesn't create duplicates"""
        # First seeding
        result1 = seed_cement_defaults(self.business)
        assert result1["created"] == 9

        # Second seeding
        result2 = seed_cement_defaults(self.business)
        assert result2["created"] == 0
        assert result2["skipped"] == 9

        # Verify still only 9 products
        assert MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).count() == 9

    def test_seed_cement_defaults_sets_correct_defaults(self):
        """Test that seeded products have correct default values"""
        seed_cement_defaults(self.business)

        product = MerchProduct.objects.get(business=self.business, name="Dangote", kind=BusinessKind.CEMENT)

        assert product.base_unit == "bag"
        assert product.quantity_in_stock == 0
        assert product.cost_price == Decimal("0.00")
        assert product.selling_price == Decimal("0.00")
        assert product.is_active is True
        assert product.track_inventory is True
        assert product.low_stock_threshold == 50

    def test_seed_cement_defaults_wrong_vertical(self):
        """Test that seeding fails for non-cement businesses"""
        # Create a phones business
        phones_business = Business.objects.create(
            name="Phone Store", slug="phone-store", business_kind=BusinessKind.PHONES, status="ACTIVE"
        )

        result = seed_cement_defaults(phones_business)
        assert result["created"] == 0
        assert "error" in result


@pytest.mark.django_db
class TestCementSellGuardrails(TestCase):
    """Test cement sell flow guardrails"""

    def setUp(self):
        """Create cement business with seeded products"""
        self.user = User.objects.create_user(username="cement_agent", email="agent@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Cement Test Store", slug="cement-test-sell", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="Agent")

        # Seed and stock Dangote cement
        seed_cement_defaults(self.business)
        self.dangote = MerchProduct.objects.get(business=self.business, name="Dangote", kind=BusinessKind.CEMENT)
        self.dangote.quantity_in_stock = 10  # Stock 10 bags
        self.dangote.cost_price = Decimal("50000")
        self.dangote.selling_price = Decimal("60000")
        self.dangote.save()

        self.client = Client()
        self.client.login(username="cement_agent", password="test1234")

    def test_cannot_sell_more_than_available_stock(self):
        """Test that selling more than available stock is blocked"""
        # Try to sell 11 bags (have 10)
        response = self.client.post(
            reverse("verticals:cement_sell") + "?step=3",
            {
                "step": "3",
                "quantity": 11,
                "payment_method": "CASH",
            },
            follow=False,
        )

        # Should redirect with error
        assert response.status_code == 302

        # Verify stock unchanged
        self.dangote.refresh_from_db()
        assert self.dangote.quantity_in_stock == 10

        # Verify no sale created
        assert CementSale.objects.filter(business=self.business).count() == 0

    def test_successful_sell_decreases_stock(self):
        """Test that successful sale decreases stock correctly"""
        # Store product_id in session (simulating step 2)
        session = self.client.session
        session["cement_sell_product_id"] = self.dangote.id
        session.save()

        # Sell 3 bags
        response = self.client.post(
            reverse("verticals:cement_sell") + "?step=3",
            {
                "step": "3",
                "quantity": 3,
                "payment_method": "CASH",
            },
            follow=True,
        )

        # Should succeed
        assert response.status_code == 200

        # Verify stock decreased
        self.dangote.refresh_from_db()
        assert self.dangote.quantity_in_stock == 7

        # Verify sale created
        sales = CementSale.objects.filter(business=self.business)
        assert sales.count() == 1

        sale = sales.first()
        assert sale.quantity == 3
        assert sale.unit_price == Decimal("60000")
        assert sale.total_price == Decimal("180000")  # 3 × 60000
        assert sale.unit_cost == Decimal("50000")
        assert sale.total_cost == Decimal("150000")  # 3 × 50000
        assert sale.profit == Decimal("30000")  # 180000 - 150000

    def test_sell_all_remaining_stock(self):
        """Test that selling all remaining stock works"""
        session = self.client.session
        session["cement_sell_product_id"] = self.dangote.id
        session.save()

        # Sell all 10 bags
        response = self.client.post(
            reverse("verticals:cement_sell") + "?step=3",
            {
                "step": "3",
                "quantity": 10,
                "payment_method": "MOBILE_MONEY",
            },
            follow=True,
        )

        assert response.status_code == 200

        # Verify stock is now zero
        self.dangote.refresh_from_db()
        assert self.dangote.quantity_in_stock == 0

        # Verify sale created correctly
        sale = CementSale.objects.get(business=self.business)
        assert sale.quantity == 10
        assert sale.payment_method == "MOBILE_MONEY"

    def test_cannot_sell_with_zero_stock(self):
        """Test that products with zero stock cannot be sold"""
        # Set stock to zero
        self.dangote.quantity_in_stock = 0
        self.dangote.save()

        session = self.client.session
        session["cement_sell_product_id"] = self.dangote.id
        session.save()

        # Try to sell 1 bag
        response = self.client.post(
            reverse("verticals:cement_sell") + "?step=3",
            {
                "step": "3",
                "quantity": 1,
                "payment_method": "CASH",
            },
            follow=False,
        )

        # Should redirect with error
        assert response.status_code == 302

        # Verify no sale created
        assert CementSale.objects.filter(business=self.business).count() == 0


@pytest.mark.django_db
class TestCementStockIn(TestCase):
    """Test cement stock-in functionality"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(
            username="cement_manager", email="manager@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Cement Store", slug="cement-store", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="Manager")

        self.client = Client()
        self.client.login(username="cement_manager", password="test1234")

    def test_stock_in_increases_quantity(self):
        """Test that stocking in increases product quantity"""
        # Seed defaults
        seed_cement_defaults(self.business)

        akshar = MerchProduct.objects.get(business=self.business, name="Akshar", kind=BusinessKind.CEMENT)
        initial_stock = akshar.quantity_in_stock

        # Stock in via form (simulating step 3)
        session = self.client.session
        session["cement_stock_in_product_id"] = akshar.id
        session.save()

        response = self.client.post(
            reverse("verticals:cement_stock_in") + "?step=3",
            {
                "step": "3",
                "quantity": 50,
                "cost_price": "48000",
                "selling_price": "58000",
                "unit": "bag",
            },
            follow=True,
        )

        assert response.status_code == 200

        # Verify stock increased
        akshar.refresh_from_db()
        assert akshar.quantity_in_stock == initial_stock + 50
        assert akshar.cost_price == Decimal("48000")
        assert akshar.selling_price == Decimal("58000")


@pytest.mark.django_db
class TestCementDashboard(TestCase):
    """Test cement dashboard view"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(username="cement_user", email="user@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Dashboard Test Store", slug="dashboard-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="Manager")

        self.client = Client()
        self.client.login(username="cement_user", password="test1234")

    def test_dashboard_seeds_on_first_visit(self):
        """Test that dashboard seeds defaults on first visit"""
        # No products exist yet
        assert MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).count() == 0

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Verify products were seeded
        assert MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).count() == 9
