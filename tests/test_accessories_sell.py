"""
Tests for Accessories Normal Sell page and API.
Ensures the "Complete Sale" button works correctly with proper feedback.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Location
from inventory.models_accessories import AccessoryProduct, AccessoryStock, AccessoryStockLog
from inventory.business_kinds import BusinessKind

User = get_user_model()


class AccessoriesNormalSellTest(TestCase):
    """Test accessories normal sell page and API endpoint."""
    
    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create business with PHONES kind
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        
        # Get the default location (created automatically)
        self.location = Location.objects.filter(
            business=self.business,
            is_default=True
        ).first()
        
        # If no default location exists, create one
        if not self.location:
            self.location = Location.objects.create(
                business=self.business,
                name='Main Store',
                is_default=True
            )
        
        # Create accessory product
        self.product = AccessoryProduct.objects.create(
            business=self.business,
            name='USB Cable',
            category='cable',
            default_order_price=Decimal('50.00'),
            default_selling_price=Decimal('100.00'),
            is_active=True
        )
        
        # Create stock
        self.stock = AccessoryStock.objects.create(
            business=self.business,
            location=self.location,
            product=self.product,
            qty_on_hand=10,
            avg_cost=Decimal('50.00')
        )
        
        # Setup client and force login
        self.client = Client()
        self.client.force_login(self.user)
        
        # Set business and location in session
        session = self.client.session
        session['business_id'] = str(self.business.id)
        session['location_id'] = str(self.location.id)
        session.save()
    
    def test_accessories_normal_sell_page_loads(self):
        """Test that the sell page loads successfully."""
        url = reverse('verticals:phones_accessories_sell')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sell Accessories')
        self.assertContains(response, 'Complete Sale')
    
    def test_accessories_sell_api_success(self):
        """Test successful sale via API."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        initial_stock = self.stock.qty_on_hand
        
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': 2,
            'selling_price': '120.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify success response
        self.assertTrue(data['success'])
        self.assertIn('SOLD', data['message'])
        self.assertEqual(data['product']['id'], self.product.id)
        self.assertEqual(data['product']['stock_remaining'], initial_stock - 2)
        self.assertEqual(data['sale']['quantity'], 2)
        self.assertEqual(float(data['sale']['unit_price']), 120.00)
        
        # Verify stock was reduced
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.qty_on_hand, initial_stock - 2)
        
        # Verify sale log was created
        sale_log = AccessoryStockLog.objects.filter(
            business=self.business,
            product=self.product,
            action='SALE'
        ).first()
        
        self.assertIsNotNone(sale_log)
        self.assertEqual(sale_log.quantity, -2)  # Negative for sales
        self.assertEqual(sale_log.by_user, self.user)
    
    def test_accessories_sell_api_missing_product_id(self):
        """Test API returns error when product_id is missing."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        response = self.client.post(url, {
            'quantity': 2,
            'selling_price': '100.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Product ID required', data['error'])
    
    def test_accessories_sell_api_invalid_quantity(self):
        """Test API returns error for invalid quantity."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        # Test zero quantity
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': 0,
            'selling_price': '100.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('must be positive', data['error'])
        
        # Test negative quantity
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': -5,
            'selling_price': '100.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
    
    def test_accessories_sell_api_insufficient_stock(self):
        """Test API returns error when insufficient stock."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        initial_stock = self.stock.qty_on_hand
        
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': initial_stock + 5,  # More than available
            'selling_price': '100.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Insufficient stock', data['error'])
        self.assertIn(str(initial_stock), data['error'])  # Shows available quantity
        
        # Verify stock was NOT reduced
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.qty_on_hand, initial_stock)
    
    def test_accessories_sell_api_invalid_price(self):
        """Test API returns error for invalid selling price."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        # Test negative price
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': 1,
            'selling_price': '-50.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('must be positive', data['error'])
        
        # Test zero price
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': 1,
            'selling_price': '0',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
    
    def test_accessories_sell_api_uses_default_price_if_not_provided(self):
        """Test API uses product's default price when selling_price not provided."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': 1,
            'payment_method': 'CASH'
            # No selling_price provided
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        # Should use product's default_selling_price (100.00)
        self.assertEqual(float(data['sale']['unit_price']), 100.00)
    
    def test_accessories_sell_api_requires_post(self):
        """Test API only accepts POST requests."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('POST required', data['error'])
    
    def test_accessories_sell_api_product_not_found(self):
        """Test API returns 404 when product doesn't exist."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        response = self.client.post(url, {
            'product_id': 99999,  # Non-existent
            'quantity': 1,
            'selling_price': '100.00',
            'payment_method': 'CASH'
        })
        
        self.assertEqual(response.status_code, 404)
    
    def test_accessories_sell_reduces_stock_atomically(self):
        """Test that stock reduction is atomic and consistent."""
        url = reverse('verticals:phones_accessories_sell_api')
        
        initial_stock = self.stock.qty_on_hand
        
        # Make multiple sales
        for i in range(3):
            response = self.client.post(url, {
                'product_id': self.product.id,
                'quantity': 1,
                'selling_price': '100.00',
                'payment_method': 'CASH'
            })
            self.assertEqual(response.status_code, 200)
        
        # Verify final stock
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.qty_on_hand, initial_stock - 3)
        
        # Verify sale logs count
        sale_logs_count = AccessoryStockLog.objects.filter(
            business=self.business,
            product=self.product,
            action='SALE'
        ).count()
        self.assertEqual(sale_logs_count, 3)

