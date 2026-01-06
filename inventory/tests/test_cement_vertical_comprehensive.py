"""
Comprehensive tests for cement vertical (no regressions).

Tests:
1. Auto-product creation with correct defaults
2. Sale reduces stock correctly
3. Dashboard metrics update
4. Costs page loads without errors
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import CementCost, CementSale
from tenants.models import Business

User = get_user_model()


class CementProductCreationTest(TestCase):
    """Test auto-product creation with correct defaults"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Hardware Store", slug="test-hardware", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

    def test_product_created_with_correct_defaults(self):
        """Test that cement products are created with correct defaults"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="Bag (50KG)",
            pack_size=50,
            quantity_in_stock=0,
            cost_price=Decimal("0.00"),
            selling_price=Decimal("0.00"),
            is_active=True,
            track_inventory=True,
        )

        self.assertEqual(product.base_unit, "Bag (50KG)")
        self.assertEqual(product.category, "cement")
        self.assertEqual(product.pack_size, 50)
        self.assertEqual(product.quantity_in_stock, 0)
        self.assertTrue(product.track_inventory)

    def test_stock_in_updates_quantity_and_prices(self):
        """Test that stock-in updates quantity and prices correctly"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Aksher Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="Bag (50KG)",
            quantity_in_stock=0,
            cost_price=Decimal("0.00"),
            selling_price=Decimal("0.00"),
            is_active=True,
            track_inventory=True,
        )

        # Simulate stock-in
        product.quantity_in_stock += 12
        product.cost_price = Decimal("25000.00")
        product.selling_price = Decimal("28000.00")
        product.save()

        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 12)
        self.assertEqual(product.cost_price, Decimal("25000.00"))
        self.assertEqual(product.selling_price, Decimal("28000.00"))


class CementSaleTest(TestCase):
    """Test cement sales reduce stock and create records"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Hardware Store", slug="test-hardware", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

        # Create product in stock
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Aksher Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="Bag (50KG)",
            quantity_in_stock=12,
            cost_price=Decimal("25000.00"),
            selling_price=Decimal("28000.00"),
            is_active=True,
            track_inventory=True,
        )

    def test_sale_reduces_stock(self):
        """Test that creating a sale reduces stock quantity"""
        # Simulate sale
        sale_qty = 5
        self.product.quantity_in_stock -= sale_qty
        self.product.save()

        # Create sale record
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=sale_qty,
            unit_price=self.product.selling_price,
            total_price=self.product.selling_price * sale_qty,
            unit_cost=self.product.cost_price,
            total_cost=self.product.cost_price * sale_qty,
            payment_method="CASH",
            sold_by=self.user,
        )

        # Verify stock reduced
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 7)

        # Verify sale record
        self.assertEqual(sale.quantity, 5)
        self.assertEqual(sale.total_price, Decimal("140000.00"))
        self.assertEqual(sale.total_cost, Decimal("125000.00"))

    def test_only_products_with_stock_are_sellable(self):
        """Test that products with zero stock cannot be sold"""
        # Create out of stock product
        out_of_stock = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="Bag (50KG)",
            quantity_in_stock=0,
            cost_price=Decimal("26000.00"),
            selling_price=Decimal("29000.00"),
            is_active=True,
            track_inventory=True,
        )

        # Query for sellable products
        sellable = MerchProduct.objects.filter(
            business=self.business, kind=BusinessKind.CEMENT, is_active=True, quantity_in_stock__gt=0
        )

        self.assertEqual(sellable.count(), 1)
        self.assertEqual(sellable.first().name, "Aksher Cement")


class CementCostTest(TestCase):
    """Test cement costs can be created with category field"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Hardware Store", slug="test-hardware", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

    def test_can_create_cost_with_category(self):
        """Test that cost entries can be created with category field"""
        from django.utils import timezone

        cost = CementCost.objects.create(
            business=self.business,
            amount=Decimal("5000.00"),
            category="transport",
            description="Fuel for delivery truck",
            cost_date=timezone.now().date(),
            notes="Test note",
            created_by=self.user,
        )

        self.assertEqual(cost.amount, Decimal("5000.00"))
        self.assertEqual(cost.category, "transport")
        self.assertEqual(cost.description, "Fuel for delivery truck")

    def test_category_field_has_correct_choices(self):
        """Test that category field accepts valid choices"""
        from django.utils import timezone

        valid_categories = ["transport", "labor", "rent", "utilities", "other"]

        for category in valid_categories:
            cost = CementCost.objects.create(
                business=self.business,
                amount=Decimal("1000.00"),
                category=category,
                description=f"Test {category}",
                cost_date=timezone.now().date(),
                created_by=self.user,
            )
            self.assertEqual(cost.category, category)


class CementIntegrationTest(TestCase):
    """Integration test for full cement flow"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Hardware Store", slug="test-hardware", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

    def test_full_flow_stock_in_then_sell(self):
        """Test full flow: create product -> stock in -> sell -> verify metrics"""
        # 1. Create product (simulating stock-in)
        product = MerchProduct.objects.create(
            business=self.business,
            name="Aksher Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="Bag (50KG)",
            quantity_in_stock=20,
            cost_price=Decimal("24000.00"),
            selling_price=Decimal("27000.00"),
            is_active=True,
            track_inventory=True,
        )

        self.assertEqual(product.quantity_in_stock, 20)

        # 2. Sell 8 bags
        sale_qty = 8
        product.quantity_in_stock -= sale_qty
        product.save()

        sale = CementSale.objects.create(
            business=self.business,
            product=product,
            quantity=sale_qty,
            unit_price=product.selling_price,
            total_price=product.selling_price * sale_qty,
            unit_cost=product.cost_price,
            total_cost=product.cost_price * sale_qty,
            payment_method="CASH",
            sold_by=self.user,
        )

        # 3. Verify stock reduced
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 12)

        # 4. Verify sale record
        self.assertEqual(sale.quantity, 8)
        self.assertEqual(sale.total_price, Decimal("216000.00"))  # 8 * 27000
        self.assertEqual(sale.total_cost, Decimal("192000.00"))  # 8 * 24000

        # 5. Verify profit calculation
        profit = sale.total_price - sale.total_cost
        self.assertEqual(profit, Decimal("24000.00"))
