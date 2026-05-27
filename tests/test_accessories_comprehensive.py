# tests/test_accessories_comprehensive.py
"""
Comprehensive tests for Phones Accessories system.

Tests:
- Dashboard loads and displays KPIs correctly
- Stock-in creates products and updates stock
- Fast sell with barcode scanner lookups
- Normal sell workflow
- Stock counts displayed everywhere
- No queryset slicing errors
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Location
from inventory.models_accessories import (
    AccessoryProduct, AccessoryStock, AccessoryStockLog,
    AccessoryCategory
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestAccessoriesDashboard(TestCase):
    """Test accessories dashboard displays correctly"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_default=True
        )
        
        # Create some test products and stock
        self.powerbank = AccessoryProduct.objects.create(
            business=self.business,
            name='20000mAh Powerbank',
            category=AccessoryCategory.POWERBANK,
            default_order_price=Decimal('15000.00'),
            default_selling_price=Decimal('20000.00'),
            barcode='PB20000'
        )
        
        self.stock = AccessoryStock.objects.create(
            business=self.business,
            location=self.location,
            product=self.powerbank,
            qty_on_hand=10
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_dashboard_loads_200(self):
        """Dashboard should load without errors"""
        url = reverse('verticals:phones_accessories_dashboard')
        response = self.client.get(url)
        
        # Should not get 500 error (queryset slicing bug)
        assert response.status_code == 200
        assert 'Accessories Dashboard' in str(response.content)
    
    def test_dashboard_shows_stock_count(self):
        """Dashboard should display total stock count"""
        url = reverse('verticals:phones_accessories_dashboard')
        response = self.client.get(url)
        
        assert response.status_code == 200
        # Should show 10 units in stock
        assert '10' in str(response.content)
        assert 'units in stock' in str(response.content)
    
    def test_dashboard_no_queryset_slicing_error(self):
        """Dashboard should not have queryset slicing errors"""
        # This was the bug: filtering AFTER slicing
        # Should apply location filter BEFORE slice
        url = reverse('verticals:phones_accessories_dashboard')
        response = self.client.get(url)
        
        # Should succeed, not 500
        assert response.status_code == 200


@pytest.mark.django_db
class TestAccessoriesStockIn(TestCase):
    """Test accessories stock-in flow"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_default=True
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_stock_in_page_loads(self):
        """Stock-in page should load"""
        url = reverse('verticals:phones_accessories_stock_in')
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert 'Stock In Accessories' in str(response.content)
    
    def test_stock_in_creates_product_and_stock(self):
        """Stock-in API should create product and add stock"""
        url = reverse('verticals:phones_accessories_stock_in_api')
        
        data = {
            'name': 'USB-C Cable',
            'category': AccessoryCategory.CABLE,
            'brand': 'Samsung',
            'barcode': 'USBC001',
            'order_price': '2000.00',
            'selling_price': '3000.00',
            'quantity': '50'
        }
        
        response = self.client.post(url, data)
        json_data = response.json()
        
        assert response.status_code == 200
        assert json_data['success'] is True
        
        # Verify product created
        product = AccessoryProduct.objects.get(barcode='USBC001')
        assert product.name == 'USB-C Cable'
        assert product.default_order_price == Decimal('2000.00')
        assert product.default_selling_price == Decimal('3000.00')
        
        # Verify stock created
        stock = AccessoryStock.objects.get(product=product, location=self.location)
        assert stock.qty_on_hand == 50


@pytest.mark.django_db
class TestAccessoriesFastSell(TestCase):
    """Test accessories fast sell + barcode scanner"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_default=True
        )
        
        self.charger = AccessoryProduct.objects.create(
            business=self.business,
            name='Fast Charger 65W',
            category=AccessoryCategory.CHARGER,
            default_order_price=Decimal('8000.00'),
            default_selling_price=Decimal('12000.00'),
            barcode='FC65W001'
        )
        
        self.stock = AccessoryStock.objects.create(
            business=self.business,
            location=self.location,
            product=self.charger,
            qty_on_hand=15
        )
        
        self.client.login(username='testagent', password='testpass123')
    
    def test_fast_sell_page_loads(self):
        """Fast sell page should load without errors"""
        url = reverse('verticals:phones_accessories_fast_sell')
        response = self.client.get(url)
        
        # Should not get queryset slicing error
        assert response.status_code == 200
        assert 'Fast Sell' in str(response.content)
    
    def test_fast_sell_has_scanner_button(self):
        """Fast sell should have barcode scanner button"""
        url = reverse('verticals:phones_accessories_fast_sell')
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert 'Scan Barcode' in str(response.content)
        assert 'startBarcodeScanner' in str(response.content)
    
    def test_barcode_lookup_api_finds_product(self):
        """Barcode lookup should find product by barcode"""
        url = reverse('verticals:phones_accessories_lookup_api')
        response = self.client.get(url, {'barcode': 'FC65W001'})
        
        json_data = response.json()
        
        assert response.status_code == 200
        assert json_data['success'] is True
        assert json_data['product']['name'] == 'Fast Charger 65W'
        assert json_data['product']['stock_qty'] == 15
    
    def test_barcode_lookup_shows_stock_count(self):
        """Barcode lookup should include stock count"""
        url = reverse('verticals:phones_accessories_lookup_api')
        response = self.client.get(url, {'barcode': 'FC65W001'})
        
        json_data = response.json()
        
        assert json_data['success'] is True
        assert 'stock_qty' in json_data['product']
        assert json_data['product']['stock_qty'] == 15
    
    def test_barcode_not_found_returns_404(self):
        """Unlinked barcode should return 404 for store barcode feature"""
        url = reverse('verticals:phones_accessories_lookup_api')
        response = self.client.get(url, {'barcode': 'NOTEXIST'})
        
        assert response.status_code == 404


@pytest.mark.django_db
class TestAccessoriesNormalSell(TestCase):
    """Test accessories normal sell workflow"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_default=True
        )
        
        self.headset = AccessoryProduct.objects.create(
            business=self.business,
            name='Wireless Headset',
            category=AccessoryCategory.HEADSET,
            default_order_price=Decimal('25000.00'),
            default_selling_price=Decimal('35000.00')
        )
        
        self.stock = AccessoryStock.objects.create(
            business=self.business,
            location=self.location,
            product=self.headset,
            qty_on_hand=8
        )
        
        self.client.login(username='testagent', password='testpass123')
    
    def test_normal_sell_page_loads(self):
        """Normal sell page should load"""
        url = reverse('verticals:phones_accessories_sell')
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert 'Sell Accessories' in str(response.content)
    
    def test_normal_sell_shows_products_with_stock(self):
        """Normal sell should show products with stock counts"""
        url = reverse('verticals:phones_accessories_sell')
        response = self.client.get(url)
        
        assert response.status_code == 200
        content = str(response.content)
        assert 'Wireless Headset' in content
        # Should show stock count in JSON data
        assert '"stock_qty": 8' in content or '"stock_qty":8' in content
    
    def test_sell_api_decrements_stock(self):
        """Sell API should decrement stock correctly"""
        url = reverse('verticals:phones_accessories_sell_api')
        
        data = {
            'product_id': self.headset.id,
            'quantity': '2',
            'selling_price': '35000.00',
            'payment_method': 'CASH'
        }
        
        response = self.client.post(url, data)
        json_data = response.json()
        
        assert response.status_code == 200
        assert json_data['success'] is True
        
        # Verify stock decremented
        self.stock.refresh_from_db()
        assert self.stock.qty_on_hand == 6  # 8 - 2 = 6
        
        # Verify sale log created
        log = AccessoryStockLog.objects.filter(
            product=self.headset,
            action='SALE'
        ).first()
        assert log is not None
        assert log.quantity == -2  # Negative for sales
    
    def test_sell_below_cost_allows_with_warning(self):
        """Selling below cost should allow but warn"""
        url = reverse('verticals:phones_accessories_sell_api')
        
        # Try to sell at K20,000 (cost is K25,000)
        data = {
            'product_id': self.headset.id,
            'quantity': '1',
            'selling_price': '20000.00',  # Below cost
            'payment_method': 'CASH'
        }
        
        response = self.client.post(url, data)
        json_data = response.json()
        
        # Should still allow sale (no hard block)
        assert response.status_code == 200
        assert json_data['success'] is True
    
    def test_sell_insufficient_stock_fails(self):
        """Selling more than available stock should fail"""
        url = reverse('verticals:phones_accessories_sell_api')
        
        data = {
            'product_id': self.headset.id,
            'quantity': '10',  # Only 8 available
            'selling_price': '35000.00',
            'payment_method': 'CASH'
        }
        
        response = self.client.post(url, data)
        json_data = response.json()
        
        assert response.status_code == 400
        assert json_data['success'] is False
        assert 'Insufficient stock' in json_data['error']


@pytest.mark.django_db
class TestAccessoriesKPIs(TestCase):
    """Test accessories dashboard KPIs update correctly"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_default=True
        )
        
        self.product = AccessoryProduct.objects.create(
            business=self.business,
            name='Test Product',
            category=AccessoryCategory.OTHER,
            default_order_price=Decimal('1000.00'),
            default_selling_price=Decimal('1500.00')
        )
        
        self.stock = AccessoryStock.objects.create(
            business=self.business,
            location=self.location,
            product=self.product,
            qty_on_hand=100
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_kpis_update_after_sale(self):
        """Dashboard KPIs should update immediately after sale"""
        # Make a sale
        sell_url = reverse('verticals:phones_accessories_sell_api')
        sell_data = {
            'product_id': self.product.id,
            'quantity': '5',
            'selling_price': '1500.00',
            'payment_method': 'CASH'
        }
        
        response = self.client.post(sell_url, sell_data)
        assert response.status_code == 200
        
        # Check dashboard KPIs
        dashboard_url = reverse('verticals:phones_accessories_dashboard')
        response = self.client.get(dashboard_url)
        
        assert response.status_code == 200
        
        # Should show updated stock: 95 units (100 - 5)
        context = response.context
        assert context['total_stock_units'] == 95
        
        # Should show revenue: 5 * 1500 = 7500
        assert context['revenue'] == Decimal('7500.00')
        
        # Should show profit: 5 * (1500 - 1000) = 2500
        assert context['profit'] == Decimal('2500.00')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

