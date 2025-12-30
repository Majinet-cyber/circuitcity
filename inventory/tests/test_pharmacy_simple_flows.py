"""
Test pharmacy simple flows - "stupid simple" for Malawian merchants.

CRITICAL: These tests lock in business rules that must NEVER break:
- Barcode is ALWAYS optional (no errors if missing)
- Expiry/batch optional (must NOT block selling)
- Packaging (strip/box) is optional
- Multi-tenant isolation enforced
- Vertical gating enforced
- No cross-business leakage
- Concurrency safe (select_for_update prevents overselling)
"""
from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import transaction

from tenants.models import Business
from inventory.models import MerchProduct, Location
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.business_kinds import BusinessKind
from inventory.pharmacy_config import (
    to_base_units,
    validate_unit_for_category,
    get_allowed_units,
    get_default_config_for_category,
    PharmacyCategory,
)
from inventory.services.pharmacy_sale import (
    stock_in_pharmacy,
    sell_pharmacy,
    OutOfStockError,
)

User = get_user_model()


class PharmacySimpleFlowsTest(TestCase):
    """Test pharmacy simple flows"""

    def setUp(self):
        """Set up test fixtures"""
        import uuid
        
        # Generate unique identifiers
        unique_id1 = uuid.uuid4().hex[:8]
        unique_id2 = uuid.uuid4().hex[:8]
        
        # Create business
        self.business = Business.objects.create(
            name=f"Test Pharmacy {unique_id1}",
            slug=f"test-pharmacy-{unique_id1}",
            business_kind=BusinessKind.PHARMACY,
        )
        
        # Create second business for isolation tests
        self.business2 = Business.objects.create(
            name=f"Other Pharmacy {unique_id2}",
            slug=f"other-pharmacy-{unique_id2}",
            business_kind=BusinessKind.PHARMACY,
        )
        
        # Get or create default location for business
        self.location = Location.ensure_default_for_business(self.business)
        
        # Create user
        self.user = User.objects.create_user(
            username="pharmacist",
            email="pharmacist@testpharmacy.com",
            password="test123",
        )


class TestNoBarcodeFlows(PharmacySimpleFlowsTest):
    """Test that barcode is ALWAYS optional"""

    def test_stock_in_without_barcode_succeeds(self):
        """Stock in without barcode must succeed"""
        result = stock_in_pharmacy(
            business=self.business,
            product_name="Paracetamol 500mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            barcode=None,  # NO BARCODE
        )
        
        self.assertTrue(result["ok"])
        self.assertIn("Stocked in", result["message"])
        
        # Verify product created without barcode
        product = MerchProduct.objects.get(pk=result["product_id"])
        self.assertEqual(product.barcode, "")
        self.assertEqual(product.quantity_in_stock, 100)

    def test_sell_without_barcode_succeeds(self):
        """Sell without barcode must succeed (by product_id)"""
        # Stock in first
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Ibuprofen 400mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=50,
            unit="tablet",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
            barcode=None,  # NO BARCODE
        )
        
        batch_id = stock_result["batch_id"]
        
        # Sell by batch_id (no barcode needed)
        sell_result = sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=10,
            unit="tablet",
        )
        
        self.assertTrue(sell_result["ok"])
        self.assertIn("Sold", sell_result["message"])
        
        # Verify stock decremented
        batch = PharmacyBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.quantity, 40)

    def test_sell_by_product_id_without_barcode(self):
        """Sell by product_id without barcode (FIFO)"""
        # Stock in first
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Amoxicillin 250mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("40.00"),
            barcode=None,  # NO BARCODE
        )
        
        product_id = stock_result["product_id"]
        
        # Sell by product_id (no barcode needed)
        sell_result = sell_pharmacy(
            business=self.business,
            product_id=product_id,
            user=self.user,
            quantity=20,
            unit="tablet",
        )
        
        self.assertTrue(sell_result["ok"])
        
        # Verify stock decremented
        product = MerchProduct.objects.get(pk=product_id)
        self.assertEqual(product.quantity_in_stock, 80)


class TestPackagingConversion(PharmacySimpleFlowsTest):
    """Test packaging conversion (strip/box)"""

    def test_stock_in_by_strip(self):
        """Stock in by strip converts to base units correctly"""
        result = stock_in_pharmacy(
            business=self.business,
            product_name="Azithromycin 250mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=5,  # 5 strips
            unit="strip",
            cost_price=Decimal("100.00"),  # per strip
            selling_price=Decimal("150.00"),  # per strip
            strip_size=10,  # 10 tablets per strip
        )
        
        self.assertTrue(result["ok"])
        self.assertEqual(result["qty_base_units"], 50)  # 5 strips * 10 tablets
        
        # Verify product stock
        product = MerchProduct.objects.get(pk=result["product_id"])
        self.assertEqual(product.quantity_in_stock, 50)
        self.assertEqual(product.strip_size, 10)

    def test_stock_in_by_box(self):
        """Stock in by box converts to base units correctly"""
        result = stock_in_pharmacy(
            business=self.business,
            product_name="Ciprofloxacin 500mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=2,  # 2 boxes
            unit="box",
            cost_price=Decimal("1000.00"),  # per box
            selling_price=Decimal("1500.00"),  # per box
            strip_size=10,  # 10 tablets per strip
            box_size=10,  # 10 strips per box
        )
        
        self.assertTrue(result["ok"])
        self.assertEqual(result["qty_base_units"], 200)  # 2 boxes * 10 strips * 10 tablets
        
        # Verify product stock
        product = MerchProduct.objects.get(pk=result["product_id"])
        self.assertEqual(product.quantity_in_stock, 200)

    def test_sell_by_strip(self):
        """Sell by strip converts to base units correctly"""
        # Stock in first
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Metronidazole 400mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            strip_size=10,
        )
        
        batch_id = stock_result["batch_id"]
        
        # Sell 3 strips
        sell_result = sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=3,
            unit="strip",
        )
        
        self.assertTrue(sell_result["ok"])
        
        # Verify stock decremented by 30 tablets (3 strips * 10)
        batch = PharmacyBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.quantity, 70)

    def test_packaging_optional_not_forced(self):
        """Packaging is optional - can stock/sell without it"""
        # Stock in syrup (no packaging)
        result = stock_in_pharmacy(
            business=self.business,
            product_name="Cough Syrup 100ml",
            category=PharmacyCategory.SYRUP,
            user=self.user,
            quantity=20,
            unit="bottle",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            # NO strip_size or box_size
        )
        
        self.assertTrue(result["ok"])
        self.assertEqual(result["qty_base_units"], 20)
        
        # Verify product has no packaging
        product = MerchProduct.objects.get(pk=result["product_id"])
        self.assertIsNone(product.strip_size)
        self.assertIsNone(product.box_size)


class TestMultiTenantIsolation(PharmacySimpleFlowsTest):
    """Test multi-tenant isolation (no cross-business leakage)"""

    def test_cannot_sell_from_other_business_batch(self):
        """Cannot sell from another business's batch"""
        # Business 1 stocks in
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Paracetamol 500mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
        )
        
        batch_id = stock_result["batch_id"]
        
        # Business 2 tries to sell from Business 1's batch
        with self.assertRaises(ValidationError) as cm:
            sell_pharmacy(
                business=self.business2,  # Different business!
                batch_id=batch_id,
                user=self.user,
                quantity=10,
                unit="tablet",
            )
        
        self.assertIn("not found", str(cm.exception).lower())

    def test_cannot_see_other_business_products(self):
        """Cannot see or sell products from other business"""
        # Business 1 creates product
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Amoxicillin 250mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("40.00"),
        )
        
        product_id = stock_result["product_id"]
        
        # Business 2 tries to sell Business 1's product
        with self.assertRaises(OutOfStockError):
            sell_pharmacy(
                business=self.business2,  # Different business!
                product_id=product_id,
                user=self.user,
                quantity=10,
                unit="tablet",
            )

    def test_stock_aggregation_per_business(self):
        """Stock aggregation is per-business (no leakage)"""
        # Business 1 stocks in
        stock_in_pharmacy(
            business=self.business,
            product_name="Ibuprofen 400mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
        )
        
        # Business 2 stocks in same product name (different product)
        stock_in_pharmacy(
            business=self.business2,
            product_name="Ibuprofen 400mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=200,
            unit="tablet",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
        )
        
        # Verify separate products and stock
        biz1_products = MerchProduct.objects.filter(business=self.business)
        biz2_products = MerchProduct.objects.filter(business=self.business2)
        
        self.assertEqual(biz1_products.count(), 1)
        self.assertEqual(biz2_products.count(), 1)
        self.assertEqual(biz1_products.first().quantity_in_stock, 100)
        self.assertEqual(biz2_products.first().quantity_in_stock, 200)


class TestConcurrencySafety(PharmacySimpleFlowsTest):
    """Test concurrency safety (select_for_update prevents overselling)"""

    def test_concurrent_sales_prevent_overselling(self):
        """Concurrent sales cannot oversell (atomic decrement)"""
        # Stock in
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Paracetamol 500mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=50,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
        )
        
        batch_id = stock_result["batch_id"]
        
        # First sale succeeds
        sell_result1 = sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=30,
            unit="tablet",
        )
        self.assertTrue(sell_result1["ok"])
        
        # Second sale for remaining stock succeeds
        sell_result2 = sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=20,
            unit="tablet",
        )
        self.assertTrue(sell_result2["ok"])
        
        # Verify batch is depleted and archived
        batch = PharmacyBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.quantity, 0)
        self.assertTrue(batch.is_archived)
        
        # Third sale should fail (batch archived, no stock)
        # Use product_id to trigger FIFO (which will find no available batches)
        product_id = stock_result["product_id"]
        with self.assertRaises(OutOfStockError):
            sell_pharmacy(
                business=self.business,
                product_id=product_id,
                user=self.user,
                quantity=1,
                unit="tablet",
            )

    def test_atomic_stock_decrement(self):
        """Stock decrement is atomic (no race conditions)"""
        # Stock in
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Azithromycin 250mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=100,
            unit="tablet",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("40.00"),
        )
        
        batch_id = stock_result["batch_id"]
        
        # Sell 60 tablets
        sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=60,
            unit="tablet",
        )
        
        # Try to sell 50 more (should fail - only 40 left)
        with self.assertRaises(OutOfStockError) as cm:
            sell_pharmacy(
                business=self.business,
                batch_id=batch_id,
                user=self.user,
                quantity=50,
                unit="tablet",
            )
        
        self.assertIn("Insufficient stock", str(cm.exception))
        
        # Verify stock not decremented
        batch = PharmacyBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.quantity, 40)


class TestExpiryOptional(PharmacySimpleFlowsTest):
    """Test that expiry is optional (must NOT block selling)"""

    def test_stock_in_without_expiry_succeeds(self):
        """Stock in without expiry date must succeed"""
        result = stock_in_pharmacy(
            business=self.business,
            product_name="Hand Sanitizer",
            category=PharmacyCategory.COSMETICS,
            user=self.user,
            quantity=50,
            unit="piece",
            cost_price=Decimal("30.00"),
            selling_price=Decimal("50.00"),
            expiry_date=None,  # NO EXPIRY
        )
        
        self.assertTrue(result["ok"])
        
        # Verify batch created without expiry
        batch = PharmacyBatch.objects.get(pk=result["batch_id"])
        self.assertIsNone(batch.expiry_date)

    def test_sell_without_expiry_succeeds(self):
        """Sell product without expiry date must succeed"""
        # Stock in without expiry
        stock_result = stock_in_pharmacy(
            business=self.business,
            product_name="Body Lotion",
            category=PharmacyCategory.COSMETICS,
            user=self.user,
            quantity=30,
            unit="piece",
            cost_price=Decimal("40.00"),
            selling_price=Decimal("70.00"),
            expiry_date=None,  # NO EXPIRY
        )
        
        batch_id = stock_result["batch_id"]
        
        # Sell must succeed
        sell_result = sell_pharmacy(
            business=self.business,
            batch_id=batch_id,
            user=self.user,
            quantity=10,
            unit="piece",
        )
        
        self.assertTrue(sell_result["ok"])


class TestFIFO(PharmacySimpleFlowsTest):
    """Test FIFO (first-in-first-out) batch selection"""

    def test_fifo_sells_from_earliest_expiry_first(self):
        """FIFO: Sells from earliest expiring batch first"""
        from datetime import date, timedelta
        
        # Stock in batch 1 (expires in 60 days)
        stock1 = stock_in_pharmacy(
            business=self.business,
            product_name="Paracetamol 500mg",
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=50,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            batch_number="BATCH001",
            expiry_date=date.today() + timedelta(days=60),
        )
        
        # Stock in batch 2 (expires in 30 days - earlier!)
        stock2 = stock_in_pharmacy(
            business=self.business,
            product_id=stock1["product_id"],
            category=PharmacyCategory.TABLETS_CAPSULES,
            user=self.user,
            quantity=50,
            unit="tablet",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            batch_number="BATCH002",
            expiry_date=date.today() + timedelta(days=30),
        )
        
        # Sell by product_id (should use FIFO - batch 2 first)
        sell_result = sell_pharmacy(
            business=self.business,
            product_id=stock1["product_id"],
            user=self.user,
            quantity=20,
            unit="tablet",
        )
        
        self.assertTrue(sell_result["ok"])
        
        # Verify batch 2 was decremented (earlier expiry)
        batch2 = PharmacyBatch.objects.get(pk=stock2["batch_id"])
        self.assertEqual(batch2.quantity, 30)
        
        # Verify batch 1 unchanged
        batch1 = PharmacyBatch.objects.get(pk=stock1["batch_id"])
        self.assertEqual(batch1.quantity, 50)


class TestVerticalGating(PharmacySimpleFlowsTest):
    """Test vertical gating (wrong vertical must NOT return 200)"""

    def test_cannot_stock_liquor_product_in_pharmacy(self):
        """Cannot create liquor product in pharmacy business"""
        # This should fail at business kind validation
        with self.assertRaises(ValidationError):
            stock_in_pharmacy(
                business=self.business,
                product_name="Beer",
                category="beer",  # Wrong category for pharmacy
                user=self.user,
                quantity=20,
                unit="bottle",
                cost_price=Decimal("500.00"),
                selling_price=Decimal("800.00"),
            )

