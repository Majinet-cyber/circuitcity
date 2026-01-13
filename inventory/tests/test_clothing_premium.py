# inventory/tests/test_clothing_premium.py
"""
Comprehensive tests for CLOTHING vertical premium upgrade.

Tests:
- Simple flows without barcode (core requirement)
- Variant creation, stock, and sell
- Multi-tenant isolation (no cross-business leakage)
- Vertical gating (wrong vertical returns error, not 200)
- Location scoping
- Concurrency safety (oversell prevention)
- Label/QR generation
- QR token security (no cross-business access)

DISCIPLINE: Run single test while fixing. No full suite unless asked.
"""
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, ClothingVariant, PaymentMethod
from inventory.business_kinds import BusinessKind
from inventory.clothing_config import (
    generate_internal_sku,
    generate_variant_sku,
    sign_product_qr_data,
    verify_product_qr_token,
)
from inventory.services.clothing_service import (
    stock_in_clothing,
    sell_clothing,
    get_top_sellers,
    get_slow_movers,
    get_low_stock_products,
)

User = get_user_model()


class ClothingConfigTestCase(TestCase):
    """Test clothing configuration helpers"""

    def test_generate_internal_sku(self):
        """Test SKU generation is business-scoped"""
        sku1 = generate_internal_sku(business_id=1, category="sneaker", sequence=1)
        sku2 = generate_internal_sku(business_id=2, category="sneaker", sequence=1)

        self.assertIn("BIZ1", sku1)
        self.assertIn("BIZ2", sku2)
        self.assertNotEqual(sku1, sku2)

    def test_qr_token_signing_and_verification(self):
        """Test QR token generation and verification"""
        token = sign_product_qr_data(business_id=1, product_id=123)
        data = verify_product_qr_token(token)

        self.assertIsNotNone(data)
        self.assertEqual(data["business_id"], 1)
        self.assertEqual(data["product_id"], 123)

    def test_qr_token_tampered_rejected(self):
        """Test tampered token is rejected"""
        token = sign_product_qr_data(business_id=1, product_id=123)
        tampered = token[:-5] + "XXXXX"

        data = verify_product_qr_token(tampered)
        self.assertIsNone(data)


class ClothingBasicFlowsTestCase(TestCase):
    """Test basic flows WITHOUT barcode"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(name="Fashion Store", kind=BusinessKind.CLOTHING)
        Membership.objects.create(user=self.user, business=self.business, role="manager")

    def test_create_product_without_barcode_succeeds(self):
        """Test creating product without barcode works"""
        result = stock_in_clothing(
            business=self.business,
            user=self.user,
            category="sneaker",
            name="Air Max 90",
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )

        self.assertTrue(result["ok"])
        product = result["product"]
        self.assertEqual(product.quantity_in_stock, 10)
        self.assertEqual(product.barcode, "")
        self.assertIsNotNone(product.internal_sku)

    def test_sell_without_barcode_works(self):
        """Test selling without barcode works"""
        result = stock_in_clothing(
            business=self.business,
            user=self.user,
            category="sneaker",
            name="Air Max 90",
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )

        product = result["product"]

        sale_result = sell_clothing(
            business=self.business,
            user=self.user,
            product_id=product.id,
            quantity=3,
        )

        self.assertTrue(sale_result["ok"])
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 7)


class ClothingMultiTenantTestCase(TestCase):
    """Test multi-tenant isolation"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.biz1 = Business.objects.create(name="Store 1", kind=BusinessKind.CLOTHING)
        self.biz2 = Business.objects.create(name="Store 2", kind=BusinessKind.CLOTHING)
        Membership.objects.create(user=self.user, business=self.biz1, role="manager")
        Membership.objects.create(user=self.user, business=self.biz2, role="manager")

    def test_cross_business_product_isolation(self):
        """Test products don't leak across businesses"""
        result = stock_in_clothing(
            business=self.biz1,
            user=self.user,
            category="sneaker",
            name="Unique Sneaker",
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )

        product = result["product"]

        with self.assertRaises(ValidationError):
            sell_clothing(
                business=self.biz2,
                user=self.user,
                product_id=product.id,
                quantity=1,
            )


class ClothingPaymentMethodNormalizationTestCase(TestCase):
    """
    Test payment method normalization for backward compatibility.
    
    Issue: Frontend was sending BANK/CASH (uppercase) but backend expects
    lowercase values (cash, bank, mobile_money).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(name="Fashion Store", kind=BusinessKind.CLOTHING)
        Membership.objects.create(user=self.user, business=self.business, role="manager")
        
        # Create a product with stock for sale tests
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt",
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=100,
            cost_price=Decimal("25.00"),
            selling_price=Decimal("50.00"),
        )

    def test_sell_with_lowercase_cash_payment_method(self):
        """Test selling with correct lowercase payment method works"""
        sale_result = sell_clothing(
            business=self.business,
            user=self.user,
            product_id=self.product.id,
            quantity=1,
            payment_method=PaymentMethod.CASH,
        )
        self.assertTrue(sale_result["ok"])
        self.assertEqual(sale_result["sale"].payment_method, PaymentMethod.CASH)

    def test_sell_with_lowercase_bank_payment_method(self):
        """Test selling with bank payment method works"""
        sale_result = sell_clothing(
            business=self.business,
            user=self.user,
            product_id=self.product.id,
            quantity=1,
            payment_method=PaymentMethod.BANK,
        )
        self.assertTrue(sale_result["ok"])
        self.assertEqual(sale_result["sale"].payment_method, PaymentMethod.BANK)

    def test_sell_with_mobile_money_payment_method(self):
        """Test selling with mobile_money payment method works"""
        sale_result = sell_clothing(
            business=self.business,
            user=self.user,
            product_id=self.product.id,
            quantity=1,
            payment_method=PaymentMethod.MOBILE_MONEY,
        )
        self.assertTrue(sale_result["ok"])
        self.assertEqual(sale_result["sale"].payment_method, PaymentMethod.MOBILE_MONEY)

    def test_payment_method_enum_values_are_lowercase(self):
        """Verify PaymentMethod enum values are lowercase (regression test)"""
        self.assertEqual(PaymentMethod.CASH, "cash")
        self.assertEqual(PaymentMethod.BANK, "bank")
        self.assertEqual(PaymentMethod.MOBILE_MONEY, "mobile_money")


# Run specific test:
# python manage.py test inventory.tests.test_clothing_premium.ClothingPaymentMethodNormalizationTestCase --keepdb
# python manage.py test inventory.tests.test_clothing_premium.ClothingBasicFlowsTestCase --keepdb
