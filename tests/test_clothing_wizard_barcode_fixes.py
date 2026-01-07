"""
Tests for Clothing Wizard Barcode Flow Fixes

Tests cover:
1. Barcode scanning with proper progress tracking
2. Custom numeric size input (34, 41, 45, etc.)
3. Smart pricing warnings (non-blocking)
4. Dashboard recent sales display
5. Payment method panels
"""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale
from inventory.business_kinds import BusinessKind

User = get_user_model()


class ClothingWizardBarcodeFixesTestCase(TestCase):
    """Test fixes for clothing wizard barcode flow"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            role="MANAGER"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        self.business.members.add(self.user)
        self.client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_wizard_submit_with_valid_single_barcode(self):
        """Test wizard submission with quantity=1 and single barcode"""
        data = {
            "category": "shoes",
            "shoe_subtype": "sneakers",
            "brand": "Nike",
            "size": "42",
            "gender": "men",
            "has_barcode": "yes",
            "selling_price": "25000.00",
            "cost_price": "18000.00",
            "quantity": 1,
            "initial_stock": 1,
            "barcode": "123456789012",
            "scanned_barcodes": ["123456789012"]
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        self.assertIn('product_id', result)
        
        # Verify product was created with correct barcode
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertEqual(product.barcode, "123456789012")
        self.assertEqual(product.quantity_in_stock, 1)
        self.assertEqual(product.size, "42")

    def test_wizard_submit_with_multiple_barcodes(self):
        """Test wizard submission with quantity>1 and multiple unique barcodes"""
        data = {
            "category": "shirts",
            "size": "L",
            "color": "blue",
            "has_barcode": "yes",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "quantity": 3,
            "initial_stock": 3,
            "barcodes": ["BC001", "BC002", "BC003"],
            "scanned_barcodes": ["BC001", "BC002", "BC003"]
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        
        # Verify product was created with first barcode
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertEqual(product.barcode, "BC001")
        self.assertEqual(product.quantity_in_stock, 3)

    def test_wizard_reject_duplicate_barcodes_in_list(self):
        """Test that duplicate barcodes within the list are rejected"""
        data = {
            "category": "jeans",
            "size": "32",
            "has_barcode": "yes",
            "selling_price": "12000.00",
            "quantity": 3,
            "initial_stock": 3,
            "barcodes": ["BC001", "BC001", "BC003"],  # Duplicate!
            "scanned_barcodes": ["BC001", "BC001", "BC003"]
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('Duplicate barcodes', result['error'])

    def test_wizard_reject_wrong_barcode_count(self):
        """Test that mismatched barcode count is rejected"""
        data = {
            "category": "shoes",
            "size": "40",
            "has_barcode": "yes",
            "selling_price": "20000.00",
            "quantity": 5,
            "initial_stock": 5,
            "barcodes": ["BC001", "BC002"],  # Only 2 but quantity is 5
            "scanned_barcodes": ["BC001", "BC002"]
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('scan all', result['error'].lower())

    def test_wizard_custom_numeric_size(self):
        """Test that custom numeric sizes (34, 41, 45) work correctly"""
        custom_sizes = ["34", "41", "45", "52"]
        
        for size in custom_sizes:
            with self.subTest(size=size):
                data = {
                    "category": "shoes",
                    "size": size,
                    "has_barcode": "no",
                    "selling_price": "25000.00",
                    "cost_price": "18000.00",
                    "quantity": 1,
                    "initial_stock": 1
                }
                
                response = self.client.post(
                    reverse('inventory:clothing_wizard_submit'),
                    data=json.dumps(data),
                    content_type='application/json'
                )
                
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertTrue(result['success'], f"Failed for size {size}: {result.get('error')}")
                
                # Verify product has correct size
                product = MerchProduct.objects.get(id=result['product_id'])
                self.assertEqual(product.size, size)
                self.assertIn(f"Size {size}", product.spec_label)

    def test_wizard_no_barcode_flow(self):
        """Test wizard with 'no barcode' option works smoothly"""
        data = {
            "category": "dresses",
            "size": "M",
            "color": "red",
            "has_barcode": "no",
            "selling_price": "18000.00",
            "quantity": 2,
            "initial_stock": 2
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        
        # Verify product has no barcode
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertIsNone(product.barcode)
        self.assertFalse(product.scan_required)

    def test_wizard_size_required_validation(self):
        """Test that size is required and cannot be skipped"""
        data = {
            "category": "shoes",
            "has_barcode": "no",
            "selling_price": "25000.00",
            "quantity": 1,
            "initial_stock": 1
            # Missing size!
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('Size is required', result['error'])

    def test_wizard_selling_price_validation(self):
        """Test that selling price must be greater than zero"""
        data = {
            "category": "shirts",
            "size": "L",
            "has_barcode": "no",
            "selling_price": "0",  # Invalid!
            "quantity": 1,
            "initial_stock": 1
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('Selling price must be greater than zero', result['error'])


class ClothingDashboardRecentSalesTestCase(TestCase):
    """Test that recent sales display correctly on dashboard"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            role="MANAGER"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        self.business.members.add(self.user)
        self.client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shoe - Size 42",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="42",
            selling_price=Decimal("25000.00"),
            cost_price=Decimal("18000.00"),
            quantity_in_stock=10,
            is_active=True
        )

    def test_dashboard_shows_recent_sales(self):
        """Test that dashboard displays recent sales when they exist"""
        # Create a sale
        sale = ClothingSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=1,
            unit_price=Decimal("25000.00"),
            total_price=Decimal("25000.00"),
            unit_cost=Decimal("18000.00"),
            total_cost=Decimal("18000.00"),
            payment_method="CASH",
            sold_by=self.user
        )
        
        # Load dashboard
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('recent_sales', response.context)
        recent_sales = response.context['recent_sales']
        self.assertTrue(len(recent_sales) > 0)
        self.assertEqual(recent_sales[0].id, sale.id)
        
        # Check that sale is rendered in HTML
        self.assertContains(response, self.product.name)
        self.assertContains(response, "25000")
        self.assertContains(response, "💰 Recent Sales")

    def test_dashboard_shows_empty_state_when_no_sales(self):
        """Test that dashboard shows empty state when no sales exist"""
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('recent_sales', response.context)
        recent_sales = response.context['recent_sales']
        self.assertEqual(len(recent_sales), 0)
        
        # Check empty state message
        self.assertContains(response, "No recent sales yet")


class ClothingPaymentMethodPanelsTestCase(TestCase):
    """Test that payment method panels work correctly"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            role="MANAGER"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        self.business.members.add(self.user)
        self.client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt - Size L",
            kind=BusinessKind.CLOTHING,
            category="shirts",
            size="L",
            selling_price=Decimal("15000.00"),
            cost_price=Decimal("10000.00"),
            quantity_in_stock=5,
            is_active=True
        )

    def test_sell_page_renders_payment_panels(self):
        """Test that sell page renders payment method as panels, not dropdown"""
        response = self.client.get(reverse('verticals:clothing_sell'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check for payment card panels
        self.assertContains(response, 'payment-card')
        self.assertContains(response, 'data-method="CASH"')
        self.assertContains(response, 'data-method="MOBILE_MONEY"')
        self.assertContains(response, 'data-method="BANK"')
        
        # Check for gamified styling
        self.assertContains(response, '💵')  # Cash icon
        self.assertContains(response, '📱')  # Mobile Money icon
        self.assertContains(response, '🏦')  # Bank icon
        
        # Ensure it's NOT a dropdown select
        self.assertNotContains(response, '<select')

    def test_sell_with_different_payment_methods(self):
        """Test that all payment methods work when posting sale"""
        payment_methods = ["CASH", "MOBILE_MONEY", "BANK"]
        
        for method in payment_methods:
            with self.subTest(payment_method=method):
                data = {
                    "product": self.product.id,
                    "quantity": 1,
                    "selling_price": "15000.00",
                    "payment_method": method
                }
                
                response = self.client.post(
                    reverse('verticals:clothing_sell'),
                    data=data
                )
                
                # Should redirect on success
                self.assertEqual(response.status_code, 302)
                
                # Verify sale was created with correct payment method
                sale = ClothingSale.objects.filter(
                    business=self.business,
                    product=self.product,
                    payment_method=method
                ).first()
                self.assertIsNotNull(sale)
                self.assertEqual(sale.payment_method, method)


class ClothingSmartPricingTestCase(TestCase):
    """Test smart pricing warnings (non-blocking)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            role="MANAGER"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        self.business.members.add(self.user)
        self.client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_below_cost_pricing_allowed_but_warned(self):
        """Test that pricing below cost is allowed but should generate warning"""
        # This is tested client-side, so we test that backend allows it
        data = {
            "category": "shirts",
            "size": "M",
            "has_barcode": "no",
            "selling_price": "8000.00",  # Below cost
            "cost_price": "10000.00",
            "quantity": 1,
            "initial_stock": 1
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        # Should succeed (not blocked)
        self.assertTrue(result['success'])
        
        # Product should be created
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertEqual(product.selling_price, Decimal("8000.00"))
        self.assertEqual(product.cost_price, Decimal("10000.00"))

    def test_zero_or_negative_price_blocked(self):
        """Test that zero or negative selling price is hard-blocked"""
        invalid_prices = ["0", "-100", "-5000"]
        
        for price in invalid_prices:
            with self.subTest(price=price):
                data = {
                    "category": "shirts",
                    "size": "M",
                    "has_barcode": "no",
                    "selling_price": price,
                    "quantity": 1,
                    "initial_stock": 1
                }
                
                response = self.client.post(
                    reverse('inventory:clothing_wizard_submit'),
                    data=json.dumps(data),
                    content_type='application/json'
                )
                
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertFalse(result['success'])
                self.assertIn('greater than zero', result['error'].lower())

