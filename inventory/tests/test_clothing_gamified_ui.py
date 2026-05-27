# inventory/tests/test_clothing_gamified_ui.py
"""
Test suite for the gamified clothing product creation UI.
Ensures that the card-based interface submits correct data to backend.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct

User = get_user_model()


class ClothingGamifiedUITest(TestCase):
    """Test gamified clothing product creation flow"""

    def setUp(self):
        """Create test user and business"""
        self.user = User.objects.create_user(
            username="testclothinguser",
            email="test@clothing.com",
            password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind=BusinessKind.CLOTHING,
            owner=self.user
        )
        
        # Set business as active
        self.user.profile.active_business = self.business
        self.user.profile.save()
        
        self.client = Client()
        self.client.login(username="testclothinguser", password="testpass123")

    def test_gamified_template_loads(self):
        """Test that the gamified template loads without errors"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check for the full path to template
        self.assertIn('verticals/clothing/quick_add_step2_gamified.html', [t.name for t in response.templates])

    def test_gamified_template_has_brands(self):
        """Test that brands are passed to template"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        self.assertIn('brands', response.context)
        self.assertIn('Nike', response.context['brands'])
        self.assertIn('Adidas', response.context['brands'])

    def test_gamified_template_has_subtypes(self):
        """Test that subtypes are passed to template for categories that have them"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        self.assertIn('subtypes', response.context)
        subtypes = response.context['subtypes']
        self.assertIsInstance(subtypes, list)
        # Sneakers should have subtypes
        self.assertGreater(len(subtypes), 0)

    def test_gamified_template_has_sizes(self):
        """Test that appropriate sizes are passed for footwear"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        self.assertIn('sizes', response.context)
        sizes = response.context['sizes']
        self.assertIn('40', sizes)  # EU footwear size

    def test_gamified_template_has_colors(self):
        """Test that colors are passed to template"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        self.assertIn('colors', response.context)
        colors = response.context['colors']
        self.assertIn('Black', colors)
        self.assertIn('White', colors)

    def test_create_product_nike_sneakers_minimal(self):
        """Test creating Nike sneakers with minimal data (brand + name + prices)"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        
        data = {
            'brand': '',  # No brand
            'name': 'Basic Sneakers',  # Just the name
            'size': '',
            'color': '',
            'selling_price': '15000.00',
            'cost_price': '8000.00',
            'quantity': '0',
            'barcode': '',
        }
        
        response = self.client.post(url, data, follow=False)
        
        # Should redirect to success page
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            category='sneaker'
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.name, 'Basic Sneakers')
        self.assertEqual(product.selling_price, Decimal('15000.00'))
        self.assertEqual(product.cost_price, Decimal('8000.00'))
        self.assertEqual(product.category, 'sneaker')

    def test_create_product_full_details(self):
        """Test creating product with all details (brand, size, color)"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        
        # The UI builds the name, backend will append brand, size, color
        # So we provide a simple base name
        data = {
            'brand': 'Adidas',
            'name': 'Running Shoes',  # Simple name, backend adds brand/size/color
            'size': '42',
            'color': 'Black',
            'selling_price': '18000.00',
            'cost_price': '10000.00',
            'quantity': '5',
            'barcode': 'TEST-BARCODE-001',
        }
        
        response = self.client.post(url, data, follow=False)
        
        # Should redirect to success page
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created with all details
        product = MerchProduct.objects.filter(
            business=self.business,
            brand='Adidas',
            size='42',
            color='Black'
        ).first()
        
        self.assertIsNotNone(product)
        # Backend service builds full name as: Brand Name - Size XX - Color
        self.assertIn('Adidas', product.name)
        self.assertIn('Running Shoes', product.name)
        self.assertEqual(product.selling_price, Decimal('18000.00'))
        self.assertEqual(product.cost_price, Decimal('10000.00'))
        self.assertEqual(product.quantity_in_stock, 5)
        self.assertEqual(product.barcode, 'TEST-BARCODE-001')

    def test_create_product_dress_no_size(self):
        """Test creating dress (category without required sizes)"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'dress'})
        
        data = {
            'brand': 'Zara',
            'name': 'Zara Casual Dress Red',
            'size': '',  # Dresses may not have size field
            'color': 'Red',
            'selling_price': '12000.00',
            'cost_price': '6000.00',
            'quantity': '3',
            'barcode': '',
        }
        
        response = self.client.post(url, data, follow=False)
        
        # Should still work without size
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            brand='Zara',
            color='Red'
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.category, 'dress')

    def test_validation_missing_required_fields(self):
        """Test that validation fails when required fields are missing"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        
        # Missing name
        data = {
            'brand': 'Nike',
            'name': '',  # Required!
            'selling_price': '15000.00',
            'cost_price': '8000.00',
        }
        
        response = self.client.post(url, data, follow=False)
        
        # Should not redirect (form errors)
        self.assertEqual(response.status_code, 200)
        # Check that form has errors
        self.assertIn('form', response.context)
        self.assertTrue(response.context['form'].errors)

    def test_validation_invalid_price(self):
        """Test that validation fails for invalid prices"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        
        # Negative selling price
        data = {
            'brand': 'Nike',
            'name': 'Nike Test',
            'selling_price': '-100.00',  # Invalid!
            'cost_price': '8000.00',
        }
        
        response = self.client.post(url, data, follow=False)
        
        # Should not redirect (form errors)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_no_regression_old_functionality(self):
        """Test that existing product creation still works (no regressions)"""
        # This ensures we didn't break anything
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'jacket'})
        
        data = {
            'brand': 'North Face',
            'name': 'North Face Winter Jacket',
            'size': 'XL',
            'color': 'Navy',
            'selling_price': '35000.00',
            'cost_price': '20000.00',
            'quantity': '2',
            'barcode': '',
        }
        
        response = self.client.post(url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            brand='North Face'
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.kind, BusinessKind.CLOTHING)
        self.assertEqual(product.category, 'jacket')

    def test_multiple_products_same_category(self):
        """Test creating multiple products in same category"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        
        # Create product 1
        data1 = {
            'brand': 'Nike',
            'name': 'Nike Air Max',
            'size': '40',
            'color': 'White',
            'selling_price': '15000.00',
            'cost_price': '8000.00',
            'quantity': '5',
        }
        response1 = self.client.post(url, data1, follow=False)
        self.assertEqual(response1.status_code, 302)
        
        # Create product 2
        data2 = {
            'brand': 'Adidas',
            'name': 'Adidas Ultraboost',
            'size': '42',
            'color': 'Black',
            'selling_price': '18000.00',
            'cost_price': '10000.00',
            'quantity': '3',
        }
        response2 = self.client.post(url, data2, follow=False)
        self.assertEqual(response2.status_code, 302)
        
        # Verify both products exist
        products = MerchProduct.objects.filter(
            business=self.business,
            category='sneaker'
        )
        self.assertEqual(products.count(), 2)

    def test_json_serialization_in_context(self):
        """Test that JSON data is properly serialized for JavaScript"""
        url = reverse('verticals:clothing_quick_add_step2', kwargs={'category': 'sneaker'})
        response = self.client.get(url)
        
        # Check that JSON strings are in context
        self.assertIn('brands_json', response.context)
        self.assertIn('subtypes_json', response.context)
        self.assertIn('sizes_json', response.context)
        
        # These should be valid JSON strings
        import json
        brands = json.loads(response.context['brands_json'])
        self.assertIsInstance(brands, list)

