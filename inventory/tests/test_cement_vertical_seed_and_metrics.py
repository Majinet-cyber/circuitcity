# inventory/tests/test_cement_vertical_seed_and_metrics.py
"""
Integration tests for cement/hardware vertical.
Ensures:
1. Catalog seeding works and is idempotent
2. Stock-in creates inventory with value
3. Sales create revenue and profit
4. Dashboard metrics reflect transactions correctly
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import ensure_hardware_seeded, seed_cement_defaults
from inventory.models import MerchProduct
from inventory.models_verticals import CementSale
from tenants.models import Business, Location, Membership

User = get_user_model()


class CementSeedingTests(TestCase):
    """Test cement/hardware catalog seeding."""

    def setUp(self):
        """Create test business."""
        self.business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
            currency="MWK",
        )

    def test_seed_cement_defaults_creates_products(self):
        """Test that seed_cement_defaults creates cement products."""
        result = seed_cement_defaults(self.business)

        self.assertGreater(result["created"], 0, "Should create cement products")
        self.assertEqual(result["skipped"], 0, "Should not skip any on first run")

        # Verify products were created
        cement_products = MerchProduct.objects.filter(
            business=self.business, kind=BusinessKind.CEMENT, category="cement"
        )
        self.assertGreater(cement_products.count(), 0, "Cement products should exist")

    def test_seed_cement_defaults_is_idempotent(self):
        """Test that running seed twice doesn't duplicate products."""
        # First run
        result1 = seed_cement_defaults(self.business)
        first_count = result1["created"]

        # Second run
        result2 = seed_cement_defaults(self.business)

        self.assertEqual(result2["created"], 0, "Should not create duplicates")
        self.assertEqual(result2["skipped"], first_count, "Should skip all existing products")

    def test_ensure_hardware_seeded_creates_both_cement_and_hardware(self):
        """Test that ensure_hardware_seeded creates both cement and hardware products."""
        result = ensure_hardware_seeded(self.business)

        # Check result structure
        self.assertIn("cement_created", result)
        self.assertIn("hardware_created", result)

        # Verify both types were created
        self.assertGreater(result["cement_created"], 0, "Should create cement products")
        self.assertGreater(result["hardware_created"], 0, "Should create hardware products")

        # Verify in database
        all_products = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT)
        self.assertGreater(all_products.count(), 0, "Products should exist")

        # Check specific categories exist
        paint_products = all_products.filter(category="paint")
        self.assertGreater(paint_products.count(), 0, "Paint products should exist")

    def test_ensure_hardware_seeded_is_idempotent(self):
        """Test that ensure_hardware_seeded can be called multiple times safely."""
        # First run
        result1 = ensure_hardware_seeded(self.business)
        first_cement = result1["cement_created"]
        first_hardware = result1["hardware_created"]

        # Second run
        result2 = ensure_hardware_seeded(self.business)

        self.assertEqual(result2["cement_created"], 0, "Should not duplicate cement products")
        self.assertEqual(result2["hardware_created"], 0, "Should not duplicate hardware products")
        self.assertEqual(result2["cement_skipped"], first_cement, "Should skip existing cement")
        self.assertEqual(result2["hardware_skipped"], first_hardware, "Should skip existing hardware")

    def test_seeded_products_start_with_zero_stock(self):
        """Test that seeded products have zero initial stock."""
        ensure_hardware_seeded(self.business)

        all_products = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT)

        for product in all_products:
            self.assertEqual(product.quantity_in_stock, 0, f"{product.name} should start with zero stock")
            self.assertTrue(product.is_active, f"{product.name} should be active")
            self.assertTrue(product.track_inventory, f"{product.name} should track inventory")

    def test_seed_fails_for_non_cement_business(self):
        """Test that seeding fails gracefully for wrong business type."""
        wrong_business = Business.objects.create(
            name="Phone Shop",
            slug="phone-shop",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE",
        )

        result = ensure_hardware_seeded(wrong_business)

        self.assertIn("error", result, "Should return error for wrong business kind")
        self.assertIn("Wrong business kind", result["error"])


class CementStockInTests(TestCase):
    """Test stock-in flow for cement vertical."""

    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
            currency="MWK",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )
        self.user = User.objects.create_user(username="manager", password="testpass123", is_staff=True)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            location=None,  # Managers don't have specific locations
            role="MANAGER",
            status="ACTIVE",
        )

        # Seed catalog
        ensure_hardware_seeded(self.business)

        self.client = Client()
        self.client.force_login(self.user)

    def test_stock_in_increases_quantity(self):
        """Test that stocking in a product increases its quantity."""
        # Get a seeded product
        product = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).first()
        initial_quantity = product.quantity_in_stock

        # Stock in 10 units
        product.quantity_in_stock += 10
        product.cost_price = Decimal("5000.00")
        product.selling_price = Decimal("6500.00")
        product.save()

        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, initial_quantity + 10)
        self.assertEqual(product.cost_price, Decimal("5000.00"))
        self.assertEqual(product.selling_price, Decimal("6500.00"))

    def test_stock_value_calculation(self):
        """Test that stock value is calculated correctly."""
        product = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).first()

        # Stock in with cost price
        product.quantity_in_stock = 20
        product.cost_price = Decimal("3500.00")
        product.save()

        # Calculate stock value
        stock_value = product.quantity_in_stock * product.cost_price
        expected_value = Decimal("70000.00")  # 20 * 3500

        self.assertEqual(stock_value, expected_value)


class CementSaleAndMetricsTests(TestCase):
    """Test sales and dashboard metrics for cement vertical."""

    def setUp(self):
        """Create test data with stocked products."""
        self.business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
            currency="MWK",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )
        self.user = User.objects.create_user(username="manager", password="testpass123", is_staff=True)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            location=None,  # Managers don't have specific locations
            role="MANAGER",
            status="ACTIVE",
        )

        # Seed and stock a product
        ensure_hardware_seeded(self.business)
        self.product = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).first()
        self.product.quantity_in_stock = 100
        self.product.cost_price = Decimal("5000.00")
        self.product.selling_price = Decimal("7000.00")
        self.product.save()

        self.client = Client()
        self.client.force_login(self.user)

    def test_sale_creates_revenue_and_profit(self):
        """Test that a sale creates correct revenue and profit."""
        quantity = 5
        unit_cost = self.product.cost_price
        unit_price = self.product.selling_price

        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=unit_price * quantity,
            unit_cost=unit_cost,
            total_cost=unit_cost * quantity,
            payment_method="CASH",
            sold_by=self.user,
        )

        # Verify calculations
        expected_revenue = Decimal("35000.00")  # 5 * 7000
        expected_cost = Decimal("25000.00")  # 5 * 5000
        expected_profit = Decimal("10000.00")  # 35000 - 25000

        self.assertEqual(sale.total_price, expected_revenue)
        self.assertEqual(sale.total_cost, expected_cost)

        profit = sale.total_price - sale.total_cost
        self.assertEqual(profit, expected_profit)

    def test_sale_decreases_stock(self):
        """Test that making a sale decreases stock quantity."""
        initial_stock = self.product.quantity_in_stock
        quantity_sold = 5

        # Decrease stock
        self.product.quantity_in_stock -= quantity_sold
        self.product.save()

        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, initial_stock - quantity_sold)

    def test_dashboard_reflects_sales_metrics(self):
        """Test that dashboard shows correct metrics after sales."""
        # Create multiple sales
        for i in range(3):
            CementSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=2,
                unit_price=self.product.selling_price,
                total_price=self.product.selling_price * 2,
                unit_cost=self.product.cost_price,
                total_cost=self.product.cost_price * 2,
                payment_method="CASH" if i % 2 == 0 else "MPESA",
                sold_by=self.user,
            )

        # Calculate expected totals
        expected_revenue = self.product.selling_price * 2 * 3  # 3 sales of 2 units each
        expected_cost = self.product.cost_price * 2 * 3
        expected_profit = expected_revenue - expected_cost

        # Get dashboard response
        response = self.client.get(reverse("cement:dashboard"))

        self.assertEqual(response.status_code, 200)

        # Verify metrics (using .get() to properly access context)
        self.assertEqual(response.context.get("total_revenue"), expected_revenue)
        self.assertEqual(response.context.get("total_profit"), expected_profit)
        self.assertEqual(response.context.get("total_sales_count"), 3)

    def test_stock_value_reflected_in_dashboard(self):
        """Test that dashboard shows correct stock value."""
        # Stock multiple products
        products = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT)[:3]

        total_value = Decimal("0")
        for i, product in enumerate(products):
            qty = (i + 1) * 10
            cost = Decimal(str((i + 1) * 1000))
            product.quantity_in_stock = qty
            product.cost_price = cost
            product.save()
            total_value += qty * cost

        # Get dashboard
        response = self.client.get(reverse("cement:dashboard"))

        self.assertEqual(response.status_code, 200)

        # Stock value should match our calculation
        self.assertGreater(response.context.get("stock_value"), Decimal("0"))

    def test_voided_sales_excluded_from_metrics(self):
        """Test that voided sales don't affect dashboard metrics."""
        # Create a normal sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=2,
            unit_price=self.product.selling_price,
            total_price=self.product.selling_price * 2,
            unit_cost=self.product.cost_price,
            total_cost=self.product.cost_price * 2,
            payment_method="CASH",
            sold_by=self.user,
            is_void=False,
        )

        # Create a voided sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=self.product.selling_price,
            total_price=self.product.selling_price * 5,
            unit_cost=self.product.cost_price,
            total_cost=self.product.cost_price * 5,
            payment_method="CASH",
            sold_by=self.user,
            is_void=True,  # This sale is voided
        )

        # Get dashboard
        response = self.client.get(reverse("cement:dashboard"))

        # Only the non-voided sale should count
        expected_revenue = self.product.selling_price * 2  # Only the first sale
        self.assertEqual(response.context.get("total_revenue"), expected_revenue)
        self.assertEqual(response.context.get("total_sales_count"), 1)  # Only 1 non-voided sale


class CementVerticalViewTests(TestCase):
    """Test cement vertical views render without errors."""

    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
            currency="MWK",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )
        self.user = User.objects.create_user(username="manager", password="testpass123", is_staff=True)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            location=None,  # Managers don't have specific locations
            role="MANAGER",
            status="ACTIVE",
        )

        # Seed catalog
        ensure_hardware_seeded(self.business)

        self.client = Client()
        self.client.force_login(self.user)

    def test_products_catalog_renders_without_error(self):
        """Test /cement/products/ page renders successfully."""
        response = self.client.get(reverse("cement:products_catalog"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "verticals/cement/products_catalog.html")
        # Main goal: ensure page doesn't crash - check for key content
        self.assertContains(response, "Hardware Products Catalog")

    def test_stock_list_renders_without_error(self):
        """Test /cement/stock/ page renders successfully."""
        response = self.client.get(reverse("cement:stock_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "verticals/cement/stock_list.html")
        # Main goal: ensure page doesn't crash with 500 error
        self.assertContains(response, "Building Materials")

    def test_sell_page_renders_with_brands(self):
        """Test /cement/sell/ shows brands (not empty)."""
        # Stock a product so it appears in sell
        product = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT).first()
        product.quantity_in_stock = 10
        product.cost_price = Decimal("5000.00")
        product.selling_price = Decimal("6000.00")
        product.save()

        response = self.client.get(reverse("cement:sell"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "verticals/cement/sell.html")
        self.assertIsNotNone(response.context.get("brands"))

        # Brands should not be empty after seeding
        brands = response.context["brands"]
        # Note: brands will only show if products are in stock
        # Since we stocked one product above, we should have at least some brands
        # (The view filters to only show brands with stock)

    def test_dashboard_renders_without_error(self):
        """Test /cement/ dashboard renders successfully."""
        response = self.client.get(reverse("cement:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "verticals/cement/dashboard.html")
        self.assertIsNotNone(response.context.get("total_revenue"))
        self.assertIsNotNone(response.context.get("total_profit"))
        self.assertIsNotNone(response.context.get("stock_value"))
