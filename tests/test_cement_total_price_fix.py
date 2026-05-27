# tests/test_cement_total_price_fix.py
"""
Tests for CementSale total_price and total_cost calculation fix.
Ensures the migration backfill works and save() method computes totals correctly.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import seed_cement_defaults
from inventory.models import MerchProduct
from inventory.models_verticals import CementSale
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementSaleTotalPriceCalculation(TestCase):
    """Test CementSale total_price and total_cost auto-calculation"""

    def setUp(self):
        """Create cement business and product"""
        self.user = User.objects.create_user(username="cement_test", email="test@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Cement Test Store", slug="cement-test-totals", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        # Create a test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cement",
            kind=BusinessKind.CEMENT,
            base_unit="bag",
            quantity_in_stock=100,
            cost_price=Decimal("50000"),
            selling_price=Decimal("60000"),
            is_active=True,
        )

    def test_cementsale_auto_calculates_total_price_on_save(self):
        """Test that CementSale.save() auto-calculates total_price"""
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
        )

        # total_price should be auto-calculated: 5 × 60000 = 300000
        assert sale.total_price == Decimal("300000")
        # total_cost should be auto-calculated: 5 × 50000 = 250000
        assert sale.total_cost == Decimal("250000")
        # profit should be: 300000 - 250000 = 50000
        assert sale.profit == Decimal("50000")

    def test_cementsale_recalculates_total_price_on_update(self):
        """Test that updating quantity recalculates total_price"""
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=3,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
        )

        # Initial totals
        assert sale.total_price == Decimal("180000")  # 3 × 60000
        assert sale.total_cost == Decimal("150000")  # 3 × 50000

        # Update quantity
        sale.quantity = 10
        sale.save()

        # Totals should be recalculated
        assert sale.total_price == Decimal("600000")  # 10 × 60000
        assert sale.total_cost == Decimal("500000")  # 10 × 50000
        assert sale.profit == Decimal("100000")  # 600000 - 500000

    def test_cementsale_handles_decimal_unit_prices(self):
        """Test that decimal unit prices are calculated correctly"""
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=7,
            unit_price=Decimal("55500.50"),
            unit_cost=Decimal("45000.25"),
            sold_by=self.user,
        )

        # 7 × 55500.50 = 388503.50
        assert sale.total_price == Decimal("388503.50")
        # 7 × 45000.25 = 315001.75
        assert sale.total_cost == Decimal("315001.75")
        # 388503.50 - 315001.75 = 73501.75
        assert sale.profit == Decimal("73501.75")

    def test_cementsale_with_zero_quantity(self):
        """Test that zero quantity results in zero totals"""
        # This shouldn't happen in practice, but test defensive behavior
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=0,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
        )

        assert sale.total_price == Decimal("0")
        assert sale.total_cost == Decimal("0")
        assert sale.profit == Decimal("0")

    def test_cementsale_with_large_quantity(self):
        """Test calculation with large quantities"""
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=1000,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
        )

        # 1000 × 60000 = 60,000,000
        assert sale.total_price == Decimal("60000000")
        # 1000 × 50000 = 50,000,000
        assert sale.total_cost == Decimal("50000000")
        # 60,000,000 - 50,000,000 = 10,000,000
        assert sale.profit == Decimal("10000000")


@pytest.mark.django_db
class TestCementDashboardAggregation(TestCase):
    """Test cement dashboard uses aggregate queries correctly"""

    def setUp(self):
        """Create cement business with products and sales"""
        self.user = User.objects.create_user(
            username="cement_dashboard", email="dashboard@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Dashboard Aggregation Test",
            slug="dashboard-agg-test",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        # Create test products
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name="Cement A",
            kind=BusinessKind.CEMENT,
            base_unit="bag",
            quantity_in_stock=100,
            cost_price=Decimal("50000"),
            selling_price=Decimal("60000"),
            is_active=True,
        )
        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name="Cement B",
            kind=BusinessKind.CEMENT,
            base_unit="bag",
            quantity_in_stock=50,
            cost_price=Decimal("48000"),
            selling_price=Decimal("58000"),
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="cement_dashboard", password="test1234")

    def test_dashboard_calculates_total_revenue_correctly(self):
        """Test that dashboard aggregates total_revenue from multiple sales"""
        today = timezone.now()

        # Create multiple sales today
        CementSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=5,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
            sold_at=today,
        )
        CementSale.objects.create(
            business=self.business,
            product=self.product2,
            quantity=3,
            unit_price=Decimal("58000"),
            unit_cost=Decimal("48000"),
            sold_by=self.user,
            sold_at=today,
        )

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check context values
        context = response.context
        # Total revenue = (5 × 60000) + (3 × 58000) = 300000 + 174000 = 474000
        assert context["total_revenue"] == Decimal("474000")
        # Total profit = (5 × 10000) + (3 × 10000) = 50000 + 30000 = 80000
        assert context["total_profit"] == Decimal("80000")
        assert context["sold_today"] == 2

    def test_dashboard_with_no_sales_today(self):
        """Test that dashboard shows zero revenue when no sales today"""
        # Create a sale from yesterday
        yesterday = timezone.now() - timezone.timedelta(days=1)
        CementSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=10,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
            sold_at=yesterday,
        )

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        context = response.context
        # Should show zero for today
        assert context["total_revenue"] == Decimal("0")
        assert context["total_profit"] == Decimal("0")
        assert context["sold_today"] == 0

    def test_dashboard_with_many_sales(self):
        """Test dashboard performance with many sales (aggregate query)"""
        today = timezone.now()

        # Create 50 sales
        for i in range(50):
            CementSale.objects.create(
                business=self.business,
                product=self.product1,
                quantity=2,
                unit_price=Decimal("60000"),
                unit_cost=Decimal("50000"),
                sold_by=self.user,
                sold_at=today,
            )

        # Visit dashboard (should use aggregate, not iterate)
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        context = response.context
        # Total revenue = 50 × (2 × 60000) = 50 × 120000 = 6,000,000
        assert context["total_revenue"] == Decimal("6000000")
        # Total profit = 50 × (2 × 10000) = 50 × 20000 = 1,000,000
        assert context["total_profit"] == Decimal("1000000")
        assert context["sold_today"] == 50

    def test_dashboard_doesnt_crash_with_total_price_column(self):
        """Test that dashboard doesn't crash when accessing total_price"""
        today = timezone.now()

        # Create a sale
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=5,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
            sold_at=today,
        )

        # Verify the sale has total_price
        assert hasattr(sale, "total_price")
        assert sale.total_price == Decimal("300000")

        # Visit dashboard - should not crash
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Verify we can access total_revenue in template
        assert b"Total Revenue" in response.content


@pytest.mark.django_db
class TestCementSaleMigrationBackfill(TestCase):
    """Test that migration backfill would work correctly"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(
            username="cement_backfill", email="backfill@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Backfill Test Store", slug="backfill-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cement",
            kind=BusinessKind.CEMENT,
            base_unit="bag",
            quantity_in_stock=100,
            cost_price=Decimal("50000"),
            selling_price=Decimal("60000"),
            is_active=True,
        )

    def test_backfill_computes_total_price_from_quantity_and_unit_price(self):
        """
        Test that backfill logic (quantity * unit_price) works correctly.
        This simulates what the migration backfill function does.
        """
        # Create a sale
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=8,
            unit_price=Decimal("60000"),
            unit_cost=Decimal("50000"),
            sold_by=self.user,
        )

        # Simulate backfill: manually compute and save
        sale.total_price = Decimal(sale.quantity) * sale.unit_price
        sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
        sale.save()

        # Verify backfill worked
        sale.refresh_from_db()
        assert sale.total_price == Decimal("480000")  # 8 × 60000
        assert sale.total_cost == Decimal("400000")  # 8 × 50000

    def test_multiple_sales_backfill(self):
        """Test backfill with multiple sales"""
        # Create multiple sales
        sales_data = [
            (10, Decimal("60000"), Decimal("50000")),
            (5, Decimal("58000"), Decimal("48000")),
            (20, Decimal("62000"), Decimal("52000")),
        ]

        for qty, unit_price, unit_cost in sales_data:
            CementSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=qty,
                unit_price=unit_price,
                unit_cost=unit_cost,
                sold_by=self.user,
            )

        # Verify all sales have correct totals (order by id for consistent ordering)
        sales = CementSale.objects.filter(business=self.business).order_by("id")
        assert sales.count() == 3

        expected_totals = [
            (Decimal("600000"), Decimal("500000")),  # 10 × 60000, 10 × 50000
            (Decimal("290000"), Decimal("240000")),  # 5 × 58000, 5 × 48000
            (Decimal("1240000"), Decimal("1040000")),  # 20 × 62000, 20 × 52000
        ]

        for sale, (expected_price, expected_cost) in zip(sales, expected_totals):
            assert sale.total_price == expected_price
            assert sale.total_cost == expected_cost
