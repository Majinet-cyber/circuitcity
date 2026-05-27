# Test for MerchProduct.size field (fix for OperationalError)
# This test verifies that migration 0045_clothing_cost_tracking was applied correctly

from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.verticals.base import merch_metrics

User = get_user_model()


class MerchProductSizeFieldTest(TestCase):
    """
    Test that MerchProduct.size field exists in DB and works correctly.

    This test was added to prevent regression of the error:
    django.db.utils.OperationalError: no such column: inventory_merchproduct.size

    If this test fails with OperationalError, run:
    python manage.py migrate inventory
    """

    def setUp(self):
        """Create test business and user"""
        self.user = User.objects.create_user(
            username="testclothinguser", email="test@clothing.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)

    def test_size_field_exists_in_database(self):
        """Verify size field can be set and queried without DB errors"""
        # Create a clothing product with size
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test T-Shirt",
            kind=BusinessKind.CLOTHING,
            size="L",
            color="Blue",
            quantity_in_stock=10,
            cost_price=5000.00,
            selling_price=8000.00,
        )

        # Verify the product was created with size
        self.assertEqual(product.size, "L")
        self.assertEqual(product.color, "Blue")
        self.assertEqual(product.quantity_in_stock, 10)

        # Verify we can query by size
        products = MerchProduct.objects.filter(size="L")
        self.assertEqual(products.count(), 1)
        self.assertEqual(products.first().name, "Test T-Shirt")

    def test_size_field_optional(self):
        """Verify size field is optional (for non-clothing products)"""
        # Create a product without size
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Item",
            kind=BusinessKind.CLOTHING,
        )

        # Verify size defaults to empty string
        self.assertEqual(product.size, "")
        self.assertEqual(product.color, "")
        self.assertEqual(product.quantity_in_stock, 0)

    def test_merch_metrics_works_with_clothing(self):
        """
        Verify merch_metrics() can query clothing products without errors.
        This is the exact call that was failing in clothing.py line 31.
        """
        # Create some clothing products
        MerchProduct.objects.create(
            business=self.business,
            name="T-Shirt S",
            kind=BusinessKind.CLOTHING,
            size="S",
        )
        MerchProduct.objects.create(
            business=self.business,
            name="T-Shirt M",
            kind=BusinessKind.CLOTHING,
            size="M",
        )
        MerchProduct.objects.create(
            business=self.business,
            name="Jeans",
            kind=BusinessKind.CLOTHING,
            size="32",
        )

        # Call merch_metrics - this was failing before
        metrics = merch_metrics(self.business, BusinessKind.CLOTHING)

        # Verify metrics were calculated correctly
        self.assertEqual(metrics["total"], 3)
        self.assertEqual(metrics["active"], 3)
        self.assertEqual(len(metrics["recent"]), 3)

    def test_size_field_ordering_in_queries(self):
        """
        Verify that ordering by -id works (the exact query from base.py line 96)
        This was the line that triggered: OperationalError: no such column
        """
        # Create products
        p1 = MerchProduct.objects.create(
            business=self.business,
            name="Product 1",
            kind=BusinessKind.CLOTHING,
            size="S",
        )
        p2 = MerchProduct.objects.create(
            business=self.business,
            name="Product 2",
            kind=BusinessKind.CLOTHING,
            size="M",
        )
        p3 = MerchProduct.objects.create(
            business=self.business,
            name="Product 3",
            kind=BusinessKind.CLOTHING,
            size="L",
        )

        # This is the exact query from base.py line 96 that was failing
        qs = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CLOTHING)
        recent = list(qs.order_by("-id")[:6])

        # Verify the query executed successfully
        self.assertEqual(len(recent), 3)
        # Verify ordering (newest first)
        self.assertEqual(recent[0].id, p3.id)
        self.assertEqual(recent[1].id, p2.id)
        self.assertEqual(recent[2].id, p1.id)

    def test_all_clothing_fields_present(self):
        """Verify all clothing-related fields from migration 0045 are accessible"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Complete Product",
            kind=BusinessKind.CLOTHING,
            size="XL",
            color="Red",
            quantity_in_stock=50,
            cost_price=10000.00,
            selling_price=15000.00,
        )

        # Refresh from DB to ensure fields are persisted
        product.refresh_from_db()

        # Verify all fields
        self.assertEqual(product.size, "XL")
        self.assertEqual(product.color, "Red")
        self.assertEqual(product.quantity_in_stock, 50)
        self.assertEqual(float(product.cost_price), 10000.00)
        self.assertEqual(float(product.selling_price), 15000.00)

    def test_size_field_max_length(self):
        """Verify size field accepts various size formats"""
        test_sizes = ["S", "M", "L", "XL", "XXL", "28", "30", "32", "One Size", "10-12"]

        for idx, size in enumerate(test_sizes):
            product = MerchProduct.objects.create(
                business=self.business,
                name=f"Product {idx}",
                kind=BusinessKind.CLOTHING,
                size=size,
            )
            self.assertEqual(product.size, size)

    # Note: Django's TestCase handles cleanup automatically via transaction rollback.
    # Manual tearDown deletion is not needed and can cause cascade errors.
