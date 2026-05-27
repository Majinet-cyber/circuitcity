"""
Tests for Clothing Wizard Bugfixes
- Pricing calculation (markup vs margin)
- Barcode flow (No barcode vs Yes barcode)
- Step numbering consistency
- Success/error feedback
"""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from tenants.models import Business

User = get_user_model()


class PricingCalculationTests(TestCase):
    """Test pricing calculations: profit, margin, markup"""
    
    def test_markup_vs_margin_calculation(self):
        """Test that markup and margin are calculated correctly"""
        # Example from user: cost=36,000, sell=70,000
        cost = Decimal('36000')
        sell = Decimal('70000')
        
        profit = sell - cost  # 34,000
        markup = (profit / cost) * 100  # 94.44%
        margin = (profit / sell) * 100  # 48.57%
        
        self.assertEqual(profit, Decimal('34000'))
        self.assertAlmostEqual(float(markup), 94.44, places=1)
        self.assertAlmostEqual(float(margin), 48.57, places=1)
        
        # Rounded values
        markup_rounded = round(markup)
        margin_rounded = round(margin)
        
        self.assertEqual(markup_rounded, 94)
        self.assertEqual(margin_rounded, 49)
    
    def test_below_cost_pricing(self):
        """Test pricing below cost shows negative margin and loss"""
        cost = Decimal('50000')
        sell = Decimal('40000')
        
        profit = sell - cost  # -10,000 (loss)
        margin = (profit / sell) * 100  # -25%
        
        self.assertEqual(profit, Decimal('-10000'))
        self.assertAlmostEqual(float(margin), -25.0, places=1)
        self.assertTrue(profit < 0)
    
    def test_zero_cost_no_divide_by_zero(self):
        """Test that zero cost doesn't cause divide by zero"""
        cost = Decimal('0')
        sell = Decimal('50000')
        
        profit = sell - cost  # 50,000
        
        # Margin should still work
        margin = (profit / sell) * 100 if sell > 0 else None
        self.assertEqual(margin, Decimal('100'))
        
        # Markup is N/A (can't divide by zero)
        markup = (profit / cost) * 100 if cost > 0 else None
        self.assertIsNone(markup)
    
    def test_zero_selling_price_edge_case(self):
        """Test zero selling price edge case"""
        cost = Decimal('10000')
        sell = Decimal('0')
        
        profit = sell - cost  # -10,000
        
        # Margin can't be computed (divide by zero)
        margin = (profit / sell) * 100 if sell > 0 else None
        self.assertIsNone(margin)
        
        # Markup can be computed
        markup = (profit / cost) * 100 if cost > 0 else None
        self.assertEqual(markup, Decimal('-100'))


class ClothingWizardBarcodeFlowTests(TestCase):
    """Test clothing wizard barcode flow"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='test@example.com'
        )
        self.user.is_manager = True
        self.user.save()
        
        self.business = Business.objects.create(
            name='Test Clothing Store',
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        
        self.client.login(username='testuser', password='testpass')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_no_barcode_saves_successfully(self):
        """Test that selecting 'No barcode' allows saving without barcode"""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'gender': 'men',
            'selling_price': '70000',
            'cost_price': '36000',
            'initial_stock': '1',
            'has_barcode': 'no',
            # No barcode field provided
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
        self.assertIn('redirect', result)
        
        # Verify product was created
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertEqual(product.business, self.business)
        self.assertEqual(product.kind, BusinessKind.CLOTHING)
        self.assertFalse(product.scan_required)
    
    def test_yes_barcode_requires_barcode(self):
        """Test that selecting 'Yes barcode' requires barcode field"""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'gender': 'men',
            'selling_price': '70000',
            'cost_price': '36000',
            'initial_stock': '1',
            'has_barcode': 'yes',
            'barcode': '1234567890123'
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        
        # Verify product was created with barcode
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertEqual(product.barcode, '1234567890123')
        self.assertTrue(product.scan_required)
    
    def test_yes_barcode_without_barcode_value_still_saves(self):
        """Test that has_barcode=yes but no barcode value still saves (for edge cases)"""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'size': '42',
            'gender': 'men',
            'selling_price': '70000',
            'cost_price': '36000',
            'initial_stock': '1',
            'has_barcode': 'yes',
            # No barcode field provided (user cancelled scan)
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['success'])
        
        # Verify product was created without barcode
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertFalse(product.scan_required)


class ClothingWizardValidationTests(TestCase):
    """Test clothing wizard validation"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='test@example.com'
        )
        self.user.is_manager = True
        self.user.save()
        
        self.business = Business.objects.create(
            name='Test Clothing Store',
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        
        self.client.login(username='testuser', password='testpass')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_required_fields_validation(self):
        """Test that required fields are validated"""
        data = {
            'category': 'shoes',
            # Missing pricing fields
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        # Should fail with validation error
        result = response.json()
        self.assertFalse(result.get('success', True))
        self.assertIn('error', result)
    
    def test_invalid_pricing_data(self):
        """Test invalid pricing data"""
        data = {
            'category': 'shoes',
            'selling_price': 'invalid',
            'cost_price': '36000',
            'initial_stock': '1',
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        result = response.json()
        self.assertFalse(result['success'])
        self.assertIn('error', result)


class ClothingProductNamingTests(TestCase):
    """Test product naming from wizard data"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass',
            email='test@example.com'
        )
        self.user.is_manager = True
        self.user.save()
        
        self.business = Business.objects.create(
            name='Test Clothing Store',
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        
        self.client.login(username='testuser', password='testpass')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_shoe_product_naming(self):
        """Test shoe product naming includes brand and model"""
        data = {
            'category': 'shoes',
            'shoe_subtype': 'sneakers',
            'brand': 'Nike',
            'model': 'Air Max',
            'size': '42',
            'selling_price': '70000',
            'cost_price': '36000',
            'initial_stock': '1',
            'has_barcode': 'no'
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        result = response.json()
        self.assertTrue(result['success'])
        
        product = MerchProduct.objects.get(id=result['product_id'])
        # Name should include category, subtype, brand, model, size
        self.assertIn('Shoes', product.name)
        self.assertIn('Sneakers', product.name)
        self.assertIn('Nike', product.name)
        self.assertIn('Air Max', product.name)
        self.assertIn('42', product.name)
    
    def test_jeans_product_naming(self):
        """Test jeans product naming"""
        data = {
            'category': 'jeans',
            'jeans_type': 'skinny',
            'color': 'blue',
            'size': '32',
            'selling_price': '25000',
            'cost_price': '15000',
            'initial_stock': '5',
            'has_barcode': 'no'
        }
        
        response = self.client.post(
            reverse('inventory:clothing_wizard_submit'),
            data=json.dumps(data),
            content_type='application/json'
        )
        
        result = response.json()
        self.assertTrue(result['success'])
        
        product = MerchProduct.objects.get(id=result['product_id'])
        self.assertIn('Jeans', product.name)
        self.assertIn('Skinny', product.name)
        self.assertIn('32', product.name)
        self.assertIn('Blue', product.name)

