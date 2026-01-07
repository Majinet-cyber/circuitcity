# inventory/tests/test_utils_metrics.py
"""
Tests for inventory metrics utilities, specifically margin estimation and potential profit.
"""
from decimal import Decimal
from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Product, InventoryItem, Location
from sales.models import Sale
from inventory.utils_metrics import (
    estimate_margin_for_business_and_sku,
    compute_potential_profit_from_stock,
    DEFAULT_MARGIN,
)

User = get_user_model()


class MarginEstimationTestCase(TestCase):
    """Test margin estimation from sales history."""

    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Electronics",
            slug="test-electronics",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )

        # Create product
        self.product = Product.objects.create(
            code="TEST001",
            brand="TestBrand",
            model="TestModel",
            variant="4+64",
            cost_price=Decimal("100000.00"),
            sale_price=Decimal("120000.00"),
        )

        # Create user for sales
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

    def test_default_margin_when_no_sales(self):
        """When there's no sales history, should return default 12% margin."""
        margin = estimate_margin_for_business_and_sku(self.business)
        self.assertEqual(margin, DEFAULT_MARGIN)
        self.assertEqual(margin, Decimal("0.12"))

    def test_margin_from_sales_history(self):
        """When there's sales history, should calculate average margin."""
        # Create 5 sold items with 20% margin
        # Cost: 100,000, Selling: 120,000 => margin = 20%
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("100000.00"),
                selling_price=Decimal("120000.00"),
                status="SOLD",
                sold_at=timezone.now() - timedelta(days=i),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal("120000.00"),
            )

        margin = estimate_margin_for_business_and_sku(self.business)

        # Should be approximately 0.20 (20%)
        # margin = (120000 - 100000) / 100000 = 0.20
        self.assertGreater(margin, Decimal("0.15"))
        self.assertLess(margin, Decimal("0.25"))

    def test_margin_never_negative(self):
        """Even with bad data, margin should never be negative."""
        # Create items sold at a loss
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("120000.00"),  # Higher cost
                selling_price=Decimal("100000.00"),  # Lower selling
                status="SOLD",
                sold_at=timezone.now() - timedelta(days=i),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal("100000.00"),
            )

        margin = estimate_margin_for_business_and_sku(self.business)

        # Should return default margin instead of negative
        self.assertEqual(margin, DEFAULT_MARGIN)
        self.assertGreaterEqual(margin, Decimal("0"))

    def test_potential_profit_calculation(self):
        """Test potential profit calculation based on margin."""
        # Create stock items with total cost of 500,000
        for i in range(5):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("100000.00"),
                status="IN_STOCK",
            )

        # Create sales history with 20% margin
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("100000.00"),
                selling_price=Decimal("120000.00"),
                status="SOLD",
                sold_at=timezone.now() - timedelta(days=i),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal("120000.00"),
            )

        stock_qs = InventoryItem.objects.filter(
            business=self.business,
            status="IN_STOCK",
        )

        potential_profit = compute_potential_profit_from_stock(stock_qs, self.business, product=self.product)

        # Stock cost: 5 * 100,000 = 500,000
        # Margin: ~20%
        # Potential profit: 500,000 * 0.20 = 100,000
        self.assertGreater(potential_profit, Decimal("80000"))  # ~16% min
        self.assertLess(potential_profit, Decimal("120000"))  # ~24% max

    def test_potential_profit_never_negative(self):
        """Potential profit should never be negative."""
        # Create stock with zero sales history
        for i in range(3):
            InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("100000.00"),
                status="IN_STOCK",
            )

        stock_qs = InventoryItem.objects.filter(
            business=self.business,
            status="IN_STOCK",
        )

        potential_profit = compute_potential_profit_from_stock(stock_qs, self.business)

        # Should use default 12% margin
        # Stock cost: 3 * 100,000 = 300,000
        # Potential profit: 300,000 * 0.12 = 36,000
        self.assertGreaterEqual(potential_profit, Decimal("0"))
        self.assertGreater(potential_profit, Decimal("30000"))
        self.assertLess(potential_profit, Decimal("50000"))

    def test_product_specific_margin(self):
        """Test that product-specific margin is used when available."""
        # Create another product
        product2 = Product.objects.create(
            code="TEST002",
            brand="TestBrand",
            model="TestModel2",
            variant="8+128",
            cost_price=Decimal("150000.00"),
            sale_price=Decimal("195000.00"),
        )

        # Create sales for product1 with 20% margin
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                order_price=Decimal("100000.00"),
                selling_price=Decimal("120000.00"),
                status="SOLD",
                sold_at=timezone.now() - timedelta(days=i),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal("120000.00"),
            )

        # Create sales for product2 with 30% margin
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=product2,
                current_location=self.location,
                order_price=Decimal("150000.00"),
                selling_price=Decimal("195000.00"),
                status="SOLD",
                sold_at=timezone.now() - timedelta(days=i),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal("195000.00"),
            )

        # Get margin for product1
        margin1 = estimate_margin_for_business_and_sku(self.business, product=self.product)

        # Get margin for product2
        margin2 = estimate_margin_for_business_and_sku(self.business, product=product2)

        # Product1 should have ~20% margin
        self.assertGreater(margin1, Decimal("0.15"))
        self.assertLess(margin1, Decimal("0.25"))

        # Product2 should have ~30% margin
        self.assertGreater(margin2, Decimal("0.25"))
        self.assertLess(margin2, Decimal("0.35"))
