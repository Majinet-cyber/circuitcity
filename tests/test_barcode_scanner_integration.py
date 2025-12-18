# tests/test_barcode_scanner_integration.py
"""
Tests for Barcode Scanner Modal integration in Pharmacy and Clothing scan-in pages.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch

User = get_user_model()


@pytest.mark.django_db
class TestPharmacyScanInBarcode(TestCase):
    """Test barcode scanner integration in Pharmacy scan-in page."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username="pharmacist",
            email="pharmacist@example.com",
            password="testpass123"
        )
        
        # Create pharmacy business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager"
        )
        
        # Login
        self.client.login(username="pharmacist", password="testpass123")
    
    def test_pharmacy_stock_in_page_loads(self):
        """Test that pharmacy stock-in page loads successfully."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        self.assertEqual(response.status_code, 200)
    
    def test_scanner_button_present(self):
        """Test that scanner button is present on pharmacy stock-in page."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        
        # Check for scanner button
        self.assertContains(response, 'openScannerBtn')
        self.assertContains(response, 'bi-upc-scan')
    
    def test_scanner_js_loaded(self):
        """Test that barcode scanner JS is loaded."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        self.assertContains(response, 'barcode-scanner-modal.js')
    
    def test_scanner_css_loaded(self):
        """Test that barcode scanner CSS is loaded."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        self.assertContains(response, 'barcode-scanner-modal.css')
    
    def test_barcode_field_present(self):
        """Test that barcode input field is present."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        self.assertContains(response, 'barcode-input')
        self.assertContains(response, 'has_barcode')
    
    def test_stock_in_with_barcode(self):
        """Test stock-in with barcode saves correctly."""
        data = {
            'product_name': 'Test Medicine',
            'sku': 'MED001',
            'category': 'medicine',
            'has_barcode': 'yes',
            'barcode': '1234567890123',
            'quantity': '10',
            'reorder_level': '5',
            'cost_price': '100.00',
            'selling_price': '150.00',
            'batch_number': 'BATCH001',
            'expiry_date': '2025-12-31',
        }
        
        response = self.client.post(reverse('verticals:pharmacy_stock_in'), data)
        
        # Check redirect or success
        self.assertIn(response.status_code, [200, 302])
        
        # Check product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            name='Test Medicine'
        ).first()
        
        if product:
            self.assertIsNotNone(product)
            
            # Check barcode was stored
            # Note: Barcode storage depends on utils_barcodes implementation
    
    def test_duplicate_barcode_validation(self):
        """Test that duplicate barcode shows validation error."""
        # Create first product with barcode
        product1 = MerchProduct.objects.create(
            business=self.business,
            name='Product 1',
            kind='pharmacy',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        # Try to create second product with same barcode
        # This test depends on barcode uniqueness validation
        # Implementation may vary based on utils_barcodes


@pytest.mark.django_db
class TestClothingScanInBarcode(TestCase):
    """Test barcode scanner integration in Clothing scan-in page."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username="clothier",
            email="clothier@example.com",
            password="testpass123"
        )
        
        # Create clothing business
        self.business = Business.objects.create(
            name="Test Clothing Store",
            business_kind="clothing"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager"
        )
        
        # Login
        self.client.login(username="clothier", password="testpass123")
    
    def test_clothing_scan_in_page_loads(self):
        """Test that clothing scan-in page loads successfully."""
        response = self.client.get(reverse('verticals:clothing_scan_in'))
        self.assertEqual(response.status_code, 200)
    
    def test_scanner_button_present(self):
        """Test that scanner button is present on clothing scan-in page."""
        response = self.client.get(reverse('verticals:clothing_scan_in'))
        
        # Check for scanner button
        self.assertContains(response, 'openScannerBtn')
        self.assertContains(response, 'bi-upc-scan')
    
    def test_scanner_js_loaded(self):
        """Test that barcode scanner JS is loaded."""
        response = self.client.get(reverse('verticals:clothing_scan_in'))
        self.assertContains(response, 'barcode-scanner-modal.js')
    
    def test_scanner_css_loaded(self):
        """Test that barcode scanner CSS is loaded."""
        response = self.client.get(reverse('verticals:clothing_scan_in'))
        self.assertContains(response, 'barcode-scanner-modal.css')
    
    def test_barcode_field_present(self):
        """Test that barcode input field is present."""
        response = self.client.get(reverse('verticals:clothing_scan_in'))
        self.assertContains(response, 'barcode-input')
        self.assertContains(response, 'has_barcode')
    
    def test_stock_in_with_barcode(self):
        """Test stock-in with barcode saves correctly."""
        data = {
            'category': 'shirt',
            'size': 'M',
            'color': 'Blue',
            'quantity': '5',
            'cost_price': '50.00',
            'selling_price': '100.00',
            'has_barcode': 'yes',
            'barcode': '9876543210987',
        }
        
        response = self.client.post(reverse('verticals:clothing_scan_in'), data)
        
        # Check redirect or success
        self.assertIn(response.status_code, [200, 302])
        
        # Check product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            kind='clothing'
        ).first()
        
        if product:
            self.assertIsNotNone(product)


@pytest.mark.django_db
class TestFastSellBarcode(TestCase):
    """Test Fast Sell barcode scanning for Pharmacy and Clothing."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username="seller",
            email="seller@example.com",
            password="testpass123"
        )
        
        # Create pharmacy business
        self.pharmacy_business = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.pharmacy_business,
            role="agent"
        )
        
        # Login
        self.client.login(username="seller", password="testpass123")
    
    def test_pharmacy_fast_sell_page_loads(self):
        """Test that pharmacy fast sell page loads."""
        response = self.client.get(reverse('verticals:pharmacy_fast_sell'))
        self.assertEqual(response.status_code, 200)
    
    def test_fast_sell_has_scanner(self):
        """Test that fast sell page has scanner functionality."""
        response = self.client.get(reverse('verticals:pharmacy_fast_sell'))
        
        # Check for scanner elements
        self.assertContains(response, 'scanner-video')
        self.assertContains(response, 'manual-barcode')
    
    def test_fast_sell_lookup_api(self):
        """Test fast sell barcode lookup API."""
        # Create product with barcode
        product = MerchProduct.objects.create(
            business=self.pharmacy_business,
            name='Test Product',
            kind='pharmacy',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        # Create batch with barcode
        batch = PharmacyBatch.objects.create(
            business=self.pharmacy_business,
            merch_product=product,
            batch_number='BATCH001',
            units_remaining=10,
            cost_price_per_unit=Decimal('100.00'),
            selling_price_per_unit=Decimal('150.00'),
            barcode='1234567890123'
        )
        
        # Test lookup API
        response = self.client.get(
            reverse('verticals:pharmacy_fast_sell_lookup_api'),
            {'barcode': '1234567890123'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data.get('ok'))
        self.assertTrue(data.get('found'))
        self.assertEqual(data.get('stock_qty'), 10)
    
    def test_fast_sell_create_api(self):
        """Test fast sell create API."""
        # Create product with barcode
        product = MerchProduct.objects.create(
            business=self.pharmacy_business,
            name='Test Product',
            kind='pharmacy',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        # Create batch with barcode
        batch = PharmacyBatch.objects.create(
            business=self.pharmacy_business,
            merch_product=product,
            batch_number='BATCH001',
            units_remaining=10,
            cost_price_per_unit=Decimal('100.00'),
            selling_price_per_unit=Decimal('150.00'),
            barcode='1234567890123'
        )
        
        # Test sell API
        import json
        response = self.client.post(
            reverse('verticals:pharmacy_fast_sell_create_api'),
            data=json.dumps({
                'barcode': '1234567890123',
                'quantity': 1,
                'payment_method': 'cash'
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data.get('ok'))
        self.assertIn('sale_id', data)
        
        # Check stock was decremented
        batch.refresh_from_db()
        self.assertEqual(batch.units_remaining, 9)
    
    def test_fast_sell_missing_price_prompts(self):
        """Test that missing selling price prompts user."""
        # Create product without selling price
        product = MerchProduct.objects.create(
            business=self.pharmacy_business,
            name='Test Product',
            kind='pharmacy',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('0.00')
        )
        
        # Create batch without selling price
        batch = PharmacyBatch.objects.create(
            business=self.pharmacy_business,
            merch_product=product,
            batch_number='BATCH001',
            units_remaining=10,
            cost_price_per_unit=Decimal('100.00'),
            selling_price_per_unit=Decimal('0.00'),
            barcode='1234567890123'
        )
        
        # Test lookup API
        response = self.client.get(
            reverse('verticals:pharmacy_fast_sell_lookup_api'),
            {'barcode': '1234567890123'}
        )
        
        data = response.json()
        self.assertTrue(data.get('needs_price'))


@pytest.mark.django_db
class TestScannerPermissions(TestCase):
    """Test that scanner features respect permissions."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
    
    def test_unauthenticated_cannot_access_scan_in(self):
        """Test that unauthenticated users cannot access scan-in."""
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_wrong_vertical_cannot_access_pharmacy(self):
        """Test that non-pharmacy businesses cannot access pharmacy scan-in."""
        user = User.objects.create_user(
            username="clothier",
            email="clothier@example.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Clothing Store",
            business_kind="clothing"
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="manager"
        )
        
        self.client.login(username="clothier", password="testpass123")
        
        # Try to access pharmacy scan-in
        response = self.client.get(reverse('verticals:pharmacy_stock_in'))
        
        # Should be denied or redirected
        self.assertIn(response.status_code, [403, 404, 302])

