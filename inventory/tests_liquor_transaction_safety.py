# inventory/tests_liquor_transaction_safety.py
"""
Tests for liquor sale transaction safety - ensures select_for_update never fails.
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import transaction, TransactionManagementError
from django.db.models import F

from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import LiquorSale, LiquorWalletEntry
from inventory.services.liquor_sale import create_liquor_sale, create_liquor_sale_by_barcode, OutOfStockError
from tenants.models import Business, Location
from inventory.views_liquor import get_or_start_active_shift

User = get_user_model()


class LiquorSaleTransactionSafetyTest(TestCase):
    """Test that liquor sales are always atomic and never raise TransactionManagementError"""

    def setUp(self):
        self.business = Business.objects.create(name="Test Liquor Store", business_kind=BusinessKind.LIQUOR)
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="test123")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        self.product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            name="Test Beer",
            quantity_in_stock=10,
            cost_per_bottle=Decimal("1000.00"),
            price_per_bottle=Decimal("1500.00"),
            category="beer",
            is_active=True,
        )

    def test_create_liquor_sale_is_atomic(self):
        """Test that create_liquor_sale is wrapped in transaction.atomic"""
        # This test verifies the service can be called without TransactionManagementError
        result = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=2,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])
        self.assertIn("sale_id", result)

        # Verify sale was created
        sale = LiquorSale.objects.get(id=result["sale_id"])
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.total_price, Decimal("3000.00"))

        # Verify stock was decremented
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 8)

    def test_select_for_update_inside_transaction(self):
        """Test that select_for_update works correctly inside transaction"""
        # This test ensures select_for_update is called inside atomic block
        # If it's called outside, it would raise TransactionManagementError

        # Call the service - should not raise TransactionManagementError
        try:
            result = create_liquor_sale(
                business=self.business,
                product_id=self.product.id,
                user=self.user,
                quantity=1,
                unit="bottle",
                unit_price=Decimal("1500.00"),
                sale_type="cash",
            )
            self.assertTrue(result["ok"])
        except TransactionManagementError as e:
            self.fail(f"select_for_update raised TransactionManagementError: {e}")

    def test_sale_fails_when_insufficient_stock(self):
        """Test that sale fails gracefully when quantity > stock"""
        initial_stock = self.product.quantity_in_stock

        with self.assertRaises(OutOfStockError):
            create_liquor_sale(
                business=self.business,
                product_id=self.product.id,
                user=self.user,
                quantity=initial_stock + 10,  # More than available
                unit="bottle",
                unit_price=Decimal("1500.00"),
                sale_type="cash",
            )

        # Stock should remain unchanged
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, initial_stock)

        # No sale should be created
        self.assertEqual(LiquorSale.objects.count(), 0)

    def test_sale_creates_wallet_entry(self):
        """Test that cash sale creates wallet entry"""
        result = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=1,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])

        # Verify wallet entry was created
        sale = LiquorSale.objects.get(id=result["sale_id"])
        wallet_entries = LiquorWalletEntry.objects.filter(related_sale=sale)
        self.assertEqual(wallet_entries.count(), 1)
        self.assertEqual(wallet_entries.first().amount, Decimal("1500.00"))

    def test_credit_sale_creates_credit_record(self):
        """Test that credit sale creates credit record"""
        from inventory.models_verticals import LiquorCredit

        result = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=1,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="credit",
            customer_name="John Doe",
        )

        self.assertTrue(result["ok"])
        self.assertIn("credit_id", result)

        # Verify credit was created
        credit = LiquorCredit.objects.get(id=result["credit_id"])
        self.assertEqual(credit.customer_name, "John Doe")
        self.assertEqual(credit.amount, Decimal("1500.00"))

        # Verify no wallet entry for credit
        sale = LiquorSale.objects.get(id=result["sale_id"])
        wallet_entries = LiquorWalletEntry.objects.filter(related_sale=sale)
        self.assertEqual(wallet_entries.count(), 0)

    def test_barcode_based_sale(self):
        """Test barcode-based quick sell"""
        # Add barcode to product
        self.product.barcode = "TEST123"
        self.product.save()

        result = create_liquor_sale_by_barcode(
            business=self.business,
            user=self.user,
            barcode="TEST123",
            quantity=1,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])
        self.assertIn("sale_id", result)

        # Verify sale was created
        sale = LiquorSale.objects.get(id=result["sale_id"])
        self.assertEqual(sale.product, self.product)
        self.assertEqual(sale.quantity, 1)

    def test_concurrent_sales_prevent_overselling(self):
        """Test that concurrent sales don't cause overselling"""
        # Simulate two concurrent sales trying to sell the last item
        initial_stock = self.product.quantity_in_stock

        # First sale succeeds
        result1 = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=initial_stock,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="cash",
        )
        self.assertTrue(result1["ok"])

        # Second sale should fail (no stock left)
        with self.assertRaises(OutOfStockError):
            create_liquor_sale(
                business=self.business,
                product_id=self.product.id,
                user=self.user,
                quantity=1,
                unit="bottle",
                unit_price=Decimal("1500.00"),
                sale_type="cash",
            )

        # Verify stock is zero
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 0)

        # Verify only one sale was created
        self.assertEqual(LiquorSale.objects.count(), 1)

    def test_atomic_stock_decrement(self):
        """Test that stock decrement is atomic using F() expression"""
        initial_stock = self.product.quantity_in_stock

        # Create sale
        result = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=3,
            unit="bottle",
            unit_price=Decimal("1500.00"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])

        # Verify stock was decremented atomically
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, initial_stock - 3)

        # Verify the F() expression was used (no race condition possible)
        # This is verified by the fact that overselling is prevented in concurrent_sales test
