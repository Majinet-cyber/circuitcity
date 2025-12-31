# inventory/tests/test_groceries_v2.py
"""
GROCERIES V2 TESTS - Comprehensive Firewall
============================================

Tests cover:
- Product creation without barcode (barcode always optional)
- Stock-in without barcode
- Sell without barcode
- Pack conversion (carton/bale/bundle → base units)
- Wholesale vs Retail pricing
- Multi-tenant security (no cross-business leakage)
- Vertical gating (GROCERIES only)
- Concurrency safety (overselling prevention)
"""
import threading
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction

from tenants.models import Business, Location
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import GrocerySale
from inventory.services.groceries_service import (
    stock_in_groceries,
    sell_groceries,
    adjust_groceries_stock,
    lookup_product_by_barcode,
    get_groceries_product,
)
from inventory.groceries_config import (
    to_base_units,
    get_unit_price,
    SALE_MODE_RETAIL,
    SALE_MODE_WHOLESALE,
)

User = get_user_model()


class GroceriesV2BasicFlowTest(TestCase):
    """Test basic groceries flows without barcodes"""
    
    def setUp(self):
        # Create business and user
        self.business = Business.objects.create(
            name="Test Groceries Shop",
            business_kind=BusinessKind.GROCERY,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        self.user = User.objects.create_user(
            username="grocer",
            password="test123",
        )
    
    def test_create_product_without_barcode(self):
        """
        A) Create product without barcode succeeds
        Barcode is ALWAYS optional
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Coca-Cola 500ml",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            barcode=None,  # NO BARCODE
            quantity_in_stock=0,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        self.assertIsNotNone(product.id)
        self.assertIsNone(product.barcode)
        self.assertEqual(product.name, "Coca-Cola 500ml")
        self.assertEqual(product.base_unit, "bottle")
    
    def test_stock_in_without_barcode(self):
        """
        B) Stock-in without barcode works
        """
        # Create product without barcode
        product = MerchProduct.objects.create(
            business=self.business,
            name="Fanta Orange 500ml",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            barcode=None,
            quantity_in_stock=0,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Stock in 50 bottles
        result = stock_in_groceries(
            business=self.business,
            location=self.location,
            product=product,
            qty=50,
            unit_label="base",
            user=self.user,
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['qty_added_base_units'], 50)
        self.assertEqual(result['new_stock_level'], 50)
        
        # Verify stock updated
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 50)
    
    def test_sell_without_barcode(self):
        """
        C) Sell without barcode works
        """
        # Create product with stock
        product = MerchProduct.objects.create(
            business=self.business,
            name="Sprite 500ml",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            barcode=None,
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Sell 10 bottles
        result = sell_groceries(
            business=self.business,
            location=self.location,
            cart_lines=[
                {
                    'product_id': product.id,
                    'qty': 10,
                    'unit_label': 'base',
                    'price_override': None,
                }
            ],
            sale_mode=SALE_MODE_RETAIL,
            payment_method='CASH',
            user=self.user,
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['items_sold'], 10)
        self.assertEqual(result['total_revenue'], Decimal("7000"))  # 10 * 700
        self.assertEqual(result['total_cost'], Decimal("5000"))  # 10 * 500
        self.assertEqual(result['total_profit'], Decimal("2000"))  # 7000 - 5000
        
        # Verify stock decreased
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 90)
        
        # Verify sale record created
        self.assertEqual(GrocerySale.objects.filter(business=self.business).count(), 1)


class GroceriesV2PackConversionTest(TestCase):
    """Test pack conversion (carton/bale/bundle → base units)"""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Groceries Shop",
            business_kind=BusinessKind.GROCERY,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        self.user = User.objects.create_user(
            username="grocer",
            password="test123",
        )
    
    def test_stock_in_by_carton(self):
        """
        D) Stock-in 2 cartons of 24 => +48 base units
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Energy Drink",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="can",
            pack_label="carton",
            bottles_per_crate=24,  # pack_size
            cost_price=Decimal("1000"),
            selling_price=Decimal("1500"),
            quantity_in_stock=0,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Stock in 2 cartons
        result = stock_in_groceries(
            business=self.business,
            location=self.location,
            product=product,
            qty=2,
            unit_label="carton",
            user=self.user,
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['qty_added_base_units'], 48)  # 2 * 24
        
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 48)
    
    def test_sell_by_carton(self):
        """
        E) Sell 1 carton => -24 base units
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Water Bottles",
            kind=BusinessKind.GROCERY,
            category_group="water",
            base_unit="bottle",
            pack_label="carton",
            bottles_per_crate=12,
            cost_price=Decimal("100"),
            selling_price=Decimal("150"),
            quantity_in_stock=48,  # 4 cartons worth
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Sell 1 carton (wholesale)
        result = sell_groceries(
            business=self.business,
            location=self.location,
            cart_lines=[
                {
                    'product_id': product.id,
                    'qty': 1,
                    'unit_label': 'carton',
                    'price_override': None,
                }
            ],
            sale_mode=SALE_MODE_WHOLESALE,
            payment_method='CASH',
            user=self.user,
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['items_sold'], 12)  # 1 carton * 12
        
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 36)  # 48 - 12
    
    def test_pack_conversion_helper(self):
        """Test to_base_units conversion helper"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Tissue Rolls",
            kind=BusinessKind.GROCERY,
            category_group="toiletries",
            base_unit="roll",
            pack_label="bale",
            bottles_per_crate=48,
            cost_price=Decimal("50"),
            selling_price=Decimal("100"),
            quantity_in_stock=0,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Test base unit conversion
        qty_base = to_base_units(10, "roll", product)
        self.assertEqual(qty_base, 10)
        
        # Test pack unit conversion
        qty_base = to_base_units(2, "bale", product)
        self.assertEqual(qty_base, 96)  # 2 * 48


class GroceriesV2WholesalePricingTest(TestCase):
    """Test wholesale vs retail pricing"""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Groceries Shop",
            business_kind=BusinessKind.GROCERY,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        self.user = User.objects.create_user(
            username="grocer",
            password="test123",
        )
    
    def test_wholesale_price_explicit(self):
        """
        F) If wholesale_price_per_pack set, use it
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Sugar 1kg Pack",
            kind=BusinessKind.GROCERY,
            category_group="sugar_staples",
            base_unit="pack",
            pack_label="bale",
            bottles_per_crate=20,
            cost_price=Decimal("2000"),
            selling_price=Decimal("2500"),  # Retail per pack
            wholesale_price_per_pack=Decimal("45000"),  # Explicit wholesale price for bale
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Get wholesale price
        wholesale_price = get_unit_price(product, "bale", SALE_MODE_WHOLESALE)
        self.assertEqual(wholesale_price, Decimal("45000"))
    
    def test_wholesale_price_derived(self):
        """
        G) If wholesale price missing, derive from retail * pack_size
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Cooking Oil 1L",
            kind=BusinessKind.GROCERY,
            category_group="cooking_oil",
            base_unit="bottle",
            pack_label="carton",
            bottles_per_crate=12,
            cost_price=Decimal("3000"),
            selling_price=Decimal("4000"),  # Retail per bottle
            wholesale_price_per_pack=None,  # No explicit wholesale price
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Get wholesale price (should be derived)
        wholesale_price = get_unit_price(product, "carton", SALE_MODE_WHOLESALE)
        expected_price = Decimal("4000") * 12  # 48000
        self.assertEqual(wholesale_price, expected_price)
    
    def test_price_override_allowed(self):
        """
        H) Price override allowed and recorded (wholesale negotiations)
        """
        product = MerchProduct.objects.create(
            business=self.business,
            name="Detergent",
            kind=BusinessKind.GROCERY,
            category_group="household",
            base_unit="box",
            cost_price=Decimal("1000"),
            selling_price=Decimal("1500"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Sell with price override (negotiated price)
        result = sell_groceries(
            business=self.business,
            location=self.location,
            cart_lines=[
                {
                    'product_id': product.id,
                    'qty': 10,
                    'unit_label': 'base',
                    'price_override': Decimal("1400"),  # Negotiated down from 1500
                }
            ],
            sale_mode=SALE_MODE_WHOLESALE,
            payment_method='CASH',
            user=self.user,
            allow_price_override=True,
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_revenue'], Decimal("14000"))  # 10 * 1400


class GroceriesV2TenantSecurityTest(TestCase):
    """Test multi-tenant isolation"""
    
    def setUp(self):
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        # Business A
        self.business_a = Business.objects.create(
            name=f"Groceries Shop Alpha {unique_id}",
            slug=f"groceries-shop-alpha-{unique_id}",
            business_kind=BusinessKind.GROCERY,
        )
        self.location_a = Location.objects.create(
            business=self.business_a,
            name="Store Alpha",
        )
        
        # Business B
        self.business_b = Business.objects.create(
            name=f"Groceries Shop Beta {unique_id}",
            slug=f"groceries-shop-beta-{unique_id}",
            business_kind=BusinessKind.GROCERY,
        )
        self.location_b = Location.objects.create(
            business=self.business_b,
            name="Store Beta",
        )
        
        self.user = User.objects.create_user(
            username=f"user_{unique_id}",
            password="test123",
        )
    
    def test_cross_business_product_access_blocked(self):
        """
        I) Cross-business isolation: products cannot leak
        """
        # Create product in Business A
        product_a = MerchProduct.objects.create(
            business=self.business_a,
            name="Product A",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Try to sell from Business B (should fail)
        with self.assertRaises(ValidationError):
            sell_groceries(
                business=self.business_b,  # Different business!
                location=self.location_b,
                cart_lines=[
                    {
                        'product_id': product_a.id,  # Product from Business A
                        'qty': 1,
                        'unit_label': 'base',
                        'price_override': None,
                    }
                ],
                sale_mode=SALE_MODE_RETAIL,
                payment_method='CASH',
                user=self.user,
            )
    
    def test_barcode_scoped_to_business(self):
        """
        J) Barcode lookup must be business-scoped
        """
        # Create same barcode in both businesses
        product_a = MerchProduct.objects.create(
            business=self.business_a,
            name="Product A",
            kind=BusinessKind.GROCERY,
            barcode="12345",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        product_b = MerchProduct.objects.create(
            business=self.business_b,
            name="Product B",
            kind=BusinessKind.GROCERY,
            barcode="12345",  # Same barcode
            base_unit="bottle",
            cost_price=Decimal("600"),
            selling_price=Decimal("800"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Lookup from Business A should return Product A
        from inventory.services.groceries_service import lookup_product_by_barcode
        result_a = lookup_product_by_barcode(business=self.business_a, barcode="12345")
        self.assertEqual(result_a.id, product_a.id)
        self.assertEqual(result_a.name, "Product A")
        
        # Lookup from Business B should return Product B
        result_b = lookup_product_by_barcode(business=self.business_b, barcode="12345")
        self.assertEqual(result_b.id, product_b.id)
        self.assertEqual(result_b.name, "Product B")


class GroceriesV2VerticalGatingTest(TestCase):
    """Test vertical gating (GROCERIES only)"""
    
    def setUp(self):
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        # Groceries business
        self.groceries_business = Business.objects.create(
            name=f"Groceries Shop {unique_id}",
            slug=f"groceries-shop-{unique_id}",
            business_kind=BusinessKind.GROCERY,
        )
        self.groceries_location = Location.objects.create(
            business=self.groceries_business,
            name="Store",
        )
        
        # Liquor business (wrong vertical)
        self.liquor_business = Business.objects.create(
            name=f"Liquor Store {unique_id}",
            slug=f"liquor-store-{unique_id}",
            business_kind=BusinessKind.LIQUOR,
        )
        self.liquor_location = Location.objects.create(
            business=self.liquor_business,
            name="Bar",
        )
        
        self.user = User.objects.create_user(
            username=f"user_{unique_id}",
            password="test123",
        )
    
    def test_wrong_vertical_blocked(self):
        """
        K) Wrong vertical returns error (not 200)
        """
        # Create product in liquor business
        product = MerchProduct.objects.create(
            business=self.liquor_business,
            name="Beer",
            kind=BusinessKind.LIQUOR,  # WRONG VERTICAL
            category="beer",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("1000"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        # Try to stock-in via groceries service (should fail)
        with self.assertRaises(PermissionDenied):
            stock_in_groceries(
                business=self.liquor_business,  # LIQUOR business!
                location=self.liquor_location,
                product=product,
                qty=10,
                unit_label="base",
                user=self.user,
            )


class GroceriesV2ConcurrencySafetyTest(TransactionTestCase):
    """Test concurrency safety (overselling prevention)"""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Shop",
            business_kind=BusinessKind.GROCERY,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Store",
        )
        self.user = User.objects.create_user(
            username="user",
            password="test123",
        )
        
        # Create product with limited stock
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Limited Stock Product",
            kind=BusinessKind.GROCERY,
            category_group="drinks",
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=10,  # Only 10 in stock
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
    
    def test_concurrent_sells_prevent_overselling(self):
        """
        L) Two simultaneous sells cannot oversell
        """
        errors = []
        
        def sell_7_units():
            """Try to sell 7 units"""
            try:
                with transaction.atomic():
                    sell_groceries(
                        business=self.business,
                        location=self.location,
                        cart_lines=[
                            {
                                'product_id': self.product.id,
                                'qty': 7,
                                'unit_label': 'base',
                                'price_override': None,
                            }
                        ],
                        sale_mode=SALE_MODE_RETAIL,
                        payment_method='CASH',
                        user=self.user,
                    )
            except Exception as e:
                errors.append(e)
        
        # Run two concurrent sales (7 + 7 = 14, but only 10 available)
        thread1 = threading.Thread(target=sell_7_units)
        thread2 = threading.Thread(target=sell_7_units)
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # At least one should fail (overselling prevented)
        self.assertGreaterEqual(len(errors), 1)
        
        # Verify final stock is non-negative
        self.product.refresh_from_db()
        self.assertGreaterEqual(self.product.quantity_in_stock, 0)
        
        # Verify total sold <= 10
        total_sold = GrocerySale.objects.filter(
            business=self.business,
            product=self.product
        ).aggregate(total=sum('quantity'))['total'] or 0
        self.assertLessEqual(total_sold, 10)


class GroceriesV2ValidationTest(TestCase):
    """Test input validation"""
    
    def setUp(self):
        self.business = Business.objects.create(
            name="Test Shop",
            business_kind=BusinessKind.GROCERY,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Store",
        )
        self.user = User.objects.create_user(
            username="user",
            password="test123",
        )
    
    def test_negative_qty_rejected(self):
        """Negative quantities must be rejected"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Product",
            kind=BusinessKind.GROCERY,
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=100,
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        with self.assertRaises(ValidationError):
            stock_in_groceries(
                business=self.business,
                location=self.location,
                product=product,
                qty=-10,  # NEGATIVE!
                unit_label="base",
                user=self.user,
            )
    
    def test_insufficient_stock_rejected(self):
        """Selling more than available stock must fail"""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Product",
            kind=BusinessKind.GROCERY,
            base_unit="bottle",
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=5,  # Only 5 available
            track_inventory=True,
            is_active=True,
            spec_label="",
        )
        
        with self.assertRaises(ValidationError) as cm:
            sell_groceries(
                business=self.business,
                location=self.location,
                cart_lines=[
                    {
                        'product_id': product.id,
                        'qty': 10,  # Trying to sell 10 > 5 available
                        'unit_label': 'base',
                        'price_override': None,
                    }
                ],
                sale_mode=SALE_MODE_RETAIL,
                payment_method='CASH',
                user=self.user,
            )
        
        self.assertIn("Insufficient stock", str(cm.exception))

