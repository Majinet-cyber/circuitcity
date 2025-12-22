# inventory/tests/test_barcode_instant_scan.py
"""
Comprehensive tests for barcode-first instant scan-to-sell system.

Tests cover:
- Barcode normalization
- Barcode registry CRUD
- Fast lookup API
- Quick create API
- Instant sale workflow
- Stock decrements
- Undo functionality
- Multi-tenant isolation
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
import json

from tenants.models import Business
from inventory.models import MerchProduct, BarcodeRegistry
from inventory.models_pharmacy import PharmacyBatch
from inventory.models_verticals import ClothingSale
from inventory.utils_barcodes import (
    normalize_barcode_enhanced,
    register_barcode,
    lookup_barcode,
    is_valid_barcode_format
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


class BarcodeNormalizationTestCase(TestCase):
    """Test barcode normalization logic"""
    
    def test_normalize_simple_code(self):
        """Test basic normalization"""
        self.assertEqual(normalize_barcode_enhanced("  abc123  "), "ABC123")
        self.assertEqual(normalize_barcode_enhanced("xyz-789"), "XYZ789")
        self.assertEqual(normalize_barcode_enhanced("test_code"), "TESTCODE")
    
    def test_normalize_numeric_ean(self):
        """Test EAN/UPC numeric codes"""
        self.assertEqual(normalize_barcode_enhanced("1234567890123"), "1234567890123")
        self.assertEqual(normalize_barcode_enhanced("001234567890"), "001234567890")  # Preserve leading zeros
    
    def test_normalize_empty(self):
        """Test empty/None handling"""
        self.assertEqual(normalize_barcode_enhanced(None), "")
        self.assertEqual(normalize_barcode_enhanced(""), "")
        self.assertEqual(normalize_barcode_enhanced("   "), "")
    
    def test_normalize_special_chars(self):
        """Test special character removal"""
        self.assertEqual(normalize_barcode_enhanced("ABC-123-XYZ"), "ABC123XYZ")
        self.assertEqual(normalize_barcode_enhanced("TEST CODE 456"), "TESTCODE456")
    
    def test_valid_barcode_format(self):
        """Test barcode format validation"""
        self.assertTrue(is_valid_barcode_format("ABC123"))
        self.assertTrue(is_valid_barcode_format("1234567890"))
        self.assertFalse(is_valid_barcode_format("AB"))  # Too short
        self.assertFalse(is_valid_barcode_format(""))
        self.assertFalse(is_valid_barcode_format(None))


class BarcodeRegistryTestCase(TestCase):
    """Test BarcodeRegistry model and operations"""
    
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.CLOTHING
        )
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test T-Shirt",
            kind=BusinessKind.CLOTHING,
            category="shirt",
            selling_price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            quantity_in_stock=10
        )
    
    def test_register_barcode(self):
        """Test barcode registration"""
        barcode = register_barcode(
            business=self.business,
            raw_code="TEST-123",
            product=self.product,
            created_by=self.user
        )
        
        self.assertIsNotNone(barcode)
        self.assertEqual(barcode.raw_code, "TEST-123")
        self.assertEqual(barcode.normalized_code, "TEST123")
        self.assertEqual(barcode.product, self.product)
        self.assertEqual(barcode.business, self.business)
        self.assertTrue(barcode.is_active)
    
    def test_register_duplicate_barcode(self):
        """Test duplicate barcode handling (should update existing)"""
        # First registration
        barcode1 = register_barcode(
            business=self.business,
            raw_code="TEST-456",
            product=self.product
        )
        
        # Second registration with same normalized code
        product2 = MerchProduct.objects.create(
            business=self.business,
            name="Test Jacket",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            quantity_in_stock=5
        )
        
        barcode2 = register_barcode(
            business=self.business,
            raw_code="test456",  # Different raw, same normalized
            product=product2
        )
        
        # Should update existing entry
        self.assertEqual(barcode1.id, barcode2.id)
        self.assertEqual(barcode2.product, product2)
        self.assertEqual(barcode2.raw_code, "test456")  # Updated
    
    def test_lookup_barcode(self):
        """Test barcode lookup"""
        register_barcode(
            business=self.business,
            raw_code="LOOKUP-789",
            product=self.product
        )
        
        result = lookup_barcode(self.business, "lookup-789")
        
        self.assertTrue(result["found"])
        self.assertEqual(result["product"], self.product)
        self.assertIsNotNone(result["registry_entry"])
    
    def test_lookup_unknown_barcode(self):
        """Test lookup of non-existent barcode"""
        result = lookup_barcode(self.business, "UNKNOWN-CODE")
        
        self.assertFalse(result["found"])
        self.assertIsNone(result["product"])
    
    def test_multi_tenant_isolation(self):
        """Test that barcodes are isolated per business"""
        business2 = Business.objects.create(
            name="Other Business",
            kind=BusinessKind.CLOTHING
        )
        
        register_barcode(
            business=self.business,
            raw_code="SHARED-CODE",
            product=self.product
        )
        
        # Same code in different business should not be found
        result = lookup_barcode(business2, "SHARED-CODE")
        self.assertFalse(result["found"])


class BarcodeLookupAPITestCase(TestCase):
    """Test barcode lookup API endpoint"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.CLOTHING
        )
        self.user.profile.business = self.business
        self.user.profile.save()
        
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            quantity_in_stock=10
        )
        
        register_barcode(
            business=self.business,
            raw_code="TEST-API-123",
            product=self.product
        )
        
        self.client.login(username="testuser", password="testpass")
    
    def test_lookup_existing_barcode(self):
        """Test API lookup of existing barcode"""
        response = self.client.get(
            reverse('api_barcode_lookup'),
            {'code': 'TEST-API-123'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['found'])
        self.assertEqual(data['product_id'], self.product.id)
        self.assertEqual(data['product_name'], self.product.name)
        self.assertEqual(Decimal(str(data['selling_price'])), self.product.selling_price)
        self.assertEqual(data['stock_available'], 10)
        self.assertFalse(data['needs_price'])
    
    def test_lookup_unknown_barcode(self):
        """Test API lookup of unknown barcode"""
        response = self.client.get(
            reverse('api_barcode_lookup'),
            {'code': 'UNKNOWN-CODE'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data['found'])
    
    def test_lookup_missing_price(self):
        """Test API lookup when product has no selling price"""
        product_no_price = MerchProduct.objects.create(
            business=self.business,
            name="No Price Product",
            kind=BusinessKind.CLOTHING,
            selling_price=None,
            cost_price=Decimal("20.00"),
            quantity_in_stock=5
        )
        
        register_barcode(
            business=self.business,
            raw_code="NO-PRICE-CODE",
            product=product_no_price
        )
        
        response = self.client.get(
            reverse('api_barcode_lookup'),
            {'code': 'NO-PRICE-CODE'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['found'])
        self.assertTrue(data['needs_price'])


class QuickCreateAPITestCase(TestCase):
    """Test quick create API for unknown barcodes"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.CLOTHING
        )
        self.user.profile.business = self.business
        self.user.profile.save()
        
        self.client.login(username="testuser", password="testpass")
    
    def test_quick_create_clothing(self):
        """Test quick create for clothing product"""
        payload = {
            'barcode': 'NEW-CLOTHING-123',
            'vertical': 'clothing',
            'product_name': 'New T-Shirt',
            'category': 'shirt',
            'selling_price': 60.00,
            'order_price': 35.00,
            'quantity': 5,
            'size': 'XL',
            'color': 'Blue'
        }
        
        response = self.client.post(
            reverse('api_barcode_quick_create'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['ok'])
        self.assertIn('product_id', data)
        
        # Verify product was created
        product = MerchProduct.objects.get(id=data['product_id'])
        self.assertEqual(product.name, 'New T-Shirt')
        self.assertEqual(product.quantity_in_stock, 5)
        self.assertEqual(product.selling_price, Decimal('60.00'))
        
        # Verify barcode was registered
        result = lookup_barcode(self.business, 'NEW-CLOTHING-123')
        self.assertTrue(result['found'])
        self.assertEqual(result['product'], product)
    
    def test_quick_create_validation(self):
        """Test quick create validation"""
        payload = {
            'barcode': 'INVALID',
            'vertical': 'clothing',
            'product_name': '',  # Missing name
            'category': 'shirt',
            'selling_price': -10,  # Negative price
            'order_price': 20,
            'quantity': 0  # Invalid quantity
        }
        
        response = self.client.post(
            reverse('api_barcode_quick_create'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        
        self.assertFalse(data['ok'])
        self.assertIn('error', data)


class InstantSaleWorkflowTestCase(TestCase):
    """Test complete instant sale workflow"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.CLOTHING
        )
        self.user.profile.business = self.business
        self.user.profile.save()
        
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            quantity_in_stock=10
        )
        
        register_barcode(
            business=self.business,
            raw_code="INSTANT-SALE-123",
            product=self.product
        )
        
        self.client.login(username="testuser", password="testpass")
    
    def test_instant_sale_decrements_stock(self):
        """Test that instant sale decrements stock correctly"""
        initial_stock = self.product.quantity_in_stock
        
        # Simulate instant sale via fast sell API
        payload = {
            'barcode': 'INSTANT-SALE-123',
            'quantity': 1,
            'payment_method': 'cash',
            'selling_price': 50.00
        }
        
        response = self.client.post(
            '/verticals/clothing/api/fast-sell/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['ok'])
        
        # Verify stock was decremented
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, initial_stock - 1)
    
    def test_instant_sale_creates_sale_record(self):
        """Test that instant sale creates a sale record"""
        payload = {
            'barcode': 'INSTANT-SALE-123',
            'quantity': 2,
            'payment_method': 'cash',
            'selling_price': 50.00
        }
        
        response = self.client.post(
            '/verticals/clothing/api/fast-sell/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data['ok'])
        self.assertIn('sale_id', data)
        
        # Verify sale record exists
        sale = ClothingSale.objects.get(id=data['sale_id'])
        self.assertEqual(sale.product, self.product)
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.unit_price, Decimal('50.00'))
    
    def test_instant_sale_out_of_stock(self):
        """Test instant sale when product is out of stock"""
        self.product.quantity_in_stock = 0
        self.product.save()
        
        payload = {
            'barcode': 'INSTANT-SALE-123',
            'quantity': 1,
            'payment_method': 'cash',
            'selling_price': 50.00
        }
        
        response = self.client.post(
            '/verticals/clothing/api/fast-sell/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data['ok'])
        self.assertIn('stock', data['error'].lower())


class MultiTenantIsolationTestCase(TestCase):
    """Test multi-tenant isolation for barcode system"""
    
    def setUp(self):
        self.business1 = Business.objects.create(
            name="Business 1",
            kind=BusinessKind.CLOTHING
        )
        self.business2 = Business.objects.create(
            name="Business 2",
            kind=BusinessKind.CLOTHING
        )
        
        self.product1 = MerchProduct.objects.create(
            business=self.business1,
            name="Product 1",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            quantity_in_stock=10
        )
        
        self.product2 = MerchProduct.objects.create(
            business=self.business2,
            name="Product 2",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("60.00"),
            cost_price=Decimal("35.00"),
            quantity_in_stock=15
        )
    
    def test_same_barcode_different_businesses(self):
        """Test that same barcode can exist in different businesses"""
        # Register same barcode in both businesses
        barcode1 = register_barcode(
            business=self.business1,
            raw_code="SHARED-CODE",
            product=self.product1
        )
        
        barcode2 = register_barcode(
            business=self.business2,
            raw_code="SHARED-CODE",
            product=self.product2
        )
        
        self.assertIsNotNone(barcode1)
        self.assertIsNotNone(barcode2)
        self.assertNotEqual(barcode1.id, barcode2.id)
        
        # Lookup should return correct product for each business
        result1 = lookup_barcode(self.business1, "SHARED-CODE")
        result2 = lookup_barcode(self.business2, "SHARED-CODE")
        
        self.assertTrue(result1['found'])
        self.assertTrue(result2['found'])
        self.assertEqual(result1['product'], self.product1)
        self.assertEqual(result2['product'], self.product2)
    
    def test_barcode_not_leaked_across_businesses(self):
        """Test that barcodes don't leak across businesses"""
        register_barcode(
            business=self.business1,
            raw_code="PRIVATE-CODE",
            product=self.product1
        )
        
        # Lookup in business2 should fail
        result = lookup_barcode(self.business2, "PRIVATE-CODE")
        self.assertFalse(result['found'])

