"""
Test that internal_sku is auto-generated for MerchProduct to prevent NOT NULL constraint failures.
"""
from django.test import TestCase
from tenants.models import Business
from inventory.models import MerchProduct, BusinessKind
from inventory.models import Location


class SKUAutoGenerationTestCase(TestCase):
    """Test SKU auto-generation at model level"""

    def setUp(self):
        """Create test business and location"""
        self.business = Business.objects.create(
            name="Test Pharmacy", business_kind=BusinessKind.PHARMACY, subdomain="test-pharm"
        )
        self.location = Location.objects.create(business=self.business, name="Main Store")

    def test_internal_sku_auto_generated_when_missing(self):
        """
        Test that internal_sku is automatically generated when creating a product
        without providing it (prevents NOT NULL constraint failure).
        """
        # Create product WITHOUT providing internal_sku
        product = MerchProduct.objects.create(
            business=self.business,
            name="Paracetamol Syrup",
            kind=BusinessKind.PHARMACY,
            selling_price=5000,
            cost_price=3000,
        )

        # Verify internal_sku was auto-generated
        self.assertIsNotNone(product.internal_sku)
        self.assertNotEqual(product.internal_sku, "")
        self.assertIn(f"BIZ{self.business.id}", product.internal_sku)
        self.assertIn("paracetamol-syrup", product.internal_sku.lower())

    def test_internal_sku_preserved_when_provided(self):
        """Test that existing SKU is preserved when provided"""
        custom_sku = "CUSTOM-SKU-123"

        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind=BusinessKind.PHARMACY,
            internal_sku=custom_sku,
            selling_price=1000,
            cost_price=500,
        )

        # Verify custom SKU was preserved
        self.assertEqual(product.internal_sku, custom_sku)

    def test_empty_sku_gets_regenerated(self):
        """Test that empty string SKU gets replaced with generated one"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Another Product",
            kind=BusinessKind.PHARMACY,
            internal_sku="",  # Empty string should trigger generation
            selling_price=2000,
            cost_price=1000,
        )

        # Verify SKU was generated (not empty)
        self.assertNotEqual(product.internal_sku, "")
        self.assertIn(f"BIZ{self.business.id}", product.internal_sku)

    def test_multiple_products_have_unique_skus(self):
        """Test that multiple products get unique SKUs"""
        product1 = MerchProduct.objects.create(
            business=self.business, name="Product One", kind=BusinessKind.PHARMACY, selling_price=1000, cost_price=500
        )

        product2 = MerchProduct.objects.create(
            business=self.business,
            name="Product Two",  # Different name
            kind=BusinessKind.PHARMACY,
            selling_price=1000,
            cost_price=500,
        )

        # Verify both have SKUs and they're different
        self.assertIsNotNone(product1.internal_sku)
        self.assertIsNotNone(product2.internal_sku)
        self.assertNotEqual(product1.internal_sku, product2.internal_sku)
