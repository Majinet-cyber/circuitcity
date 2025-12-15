"""
Tests for clothing vertical premium features:
- Dashboard KPIs (Revenue/Cost/Profit)
- Payment Mix panel
- Top models & sales trends
- Clothing Hub (stock overview)
- Gamified scan-in flow
- Gamified sell flow
"""
import pytest
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import MerchProduct, Location
from inventory.models_verticals import ClothingSale, ClothingProductLog, ClothingProductAction, PaymentMethod
from inventory.business_kinds import BusinessKind
from conftest import unique_slug

User = get_user_model()


@pytest.mark.django_db
class TestClothingDashboardKPIs(TestCase):
    """Test clothing dashboard KPI calculations"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Fashion Store',
            slug=unique_slug('Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER'
        )
        
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_dashboard_revenue_cost_profit(self):
        """Test that dashboard calculates revenue, cost, and profit correctly"""
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10
        )
        
        # Create sales this month
        now = timezone.now()
        for i in range(3):
            ClothingSale.objects.create(
                business=self.business,
                product=product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=now
            )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['revenue_mtd'], Decimal('2400.00'))  # 3 × 800
        self.assertEqual(response.context['cost_mtd'], Decimal('1500.00'))     # 3 × 500
        self.assertEqual(response.context['profit_mtd'], Decimal('900.00'))    # 2400 - 1500
        self.assertEqual(response.context['total_sales_mtd'], 3)
    
    def test_dashboard_payment_mix(self):
        """Test that payment mix is calculated correctly"""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Dress - L - Red',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('300.00'),
            selling_price=Decimal('600.00'),
            quantity_in_stock=10
        )
        
        now = timezone.now()
        
        # Create 2 cash sales
        for i in range(2):
            ClothingSale.objects.create(
                business=self.business,
                product=product,
                quantity=1,
                unit_price=Decimal('600.00'),
                total_price=Decimal('600.00'),
                unit_cost=Decimal('300.00'),
                total_cost=Decimal('300.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=now
            )
        
        # Create 1 mobile money sale
        ClothingSale.objects.create(
            business=self.business,
            product=product,
            quantity=1,
            unit_price=Decimal('600.00'),
            total_price=Decimal('600.00'),
            unit_cost=Decimal('300.00'),
            total_cost=Decimal('300.00'),
            payment_method=PaymentMethod.MOBILE_MONEY,
            sold_by=self.user,
            sold_at=now
        )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        payment_mix = response.context['payment_mix_data']
        
        # Should have 2 payment methods
        self.assertEqual(len(payment_mix), 2)
        
        # Cash should be 66.7% (1200 / 1800)
        cash_entry = next((pm for pm in payment_mix if pm['method'] == PaymentMethod.CASH), None)
        self.assertIsNotNone(cash_entry)
        self.assertAlmostEqual(float(cash_entry['percentage']), 66.7, places=1)
    
    def test_dashboard_top_model(self):
        """Test that top model is identified correctly"""
        product1 = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            quantity_in_stock=10
        )
        
        product2 = MerchProduct.objects.create(
            business=self.business,
            name='Shirt - L - White',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('200.00'),
            quantity_in_stock=10
        )
        
        now = timezone.now()
        
        # Create 5 sales for product2 (should be top)
        for i in range(5):
            ClothingSale.objects.create(
                business=self.business,
                product=product2,
                quantity=1,
                unit_price=Decimal('400.00'),
                total_price=Decimal('400.00'),
                sold_by=self.user,
                sold_at=now
            )
        
        # Create 2 sales for product1
        for i in range(2):
            ClothingSale.objects.create(
                business=self.business,
                product=product1,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                sold_by=self.user,
                sold_at=now
            )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        top_model = response.context['top_model']
        
        self.assertIsNotNone(top_model)
        self.assertEqual(top_model['product__name'], 'Shirt - L - White')
        self.assertEqual(top_model['units_sold'], 5)
    
    def test_dashboard_no_sales_returns_zero_decimals(self):
        """Test that dashboard handles no sales gracefully without 500 error"""
        # Create a product but no sales
        product = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10
        )
        
        # Dashboard should load without error even with no sales
        response = self.client.get(reverse('verticals:clothing_dashboard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        # All sales metrics should be 0, not None
        self.assertEqual(response.context['revenue_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['cost_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['profit_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['total_sales_mtd'], 0)
        # Payment mix should be empty list
        self.assertEqual(response.context['payment_mix_data'], [])
        # Top model should be None
        self.assertIsNone(response.context['top_model'])
        # Sales trend should have entries for each day in MTD period
        self.assertIsInstance(response.context['sales_trend'], list)
        # All trend entries should have 0 revenue
        for day in response.context['sales_trend']:
            self.assertEqual(day['revenue'], 0.0)
    
    def test_dashboard_inventory_metrics_with_null_prices(self):
        """Test that inventory metrics handle NULL cost_price or selling_price using Coalesce"""
        # Create product with NULL cost_price
        product1 = MerchProduct.objects.create(
            business=self.business,
            name='Product - No Cost',
            kind=BusinessKind.CLOTHING,
            cost_price=None,
            selling_price=Decimal('800.00'),
            quantity_in_stock=10,
            is_active=True,
            is_archived=False
        )
        
        # Create product with NULL selling_price
        product2 = MerchProduct.objects.create(
            business=self.business,
            name='Product - No Price',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=None,
            quantity_in_stock=5,
            is_active=True,
            is_archived=False
        )
        
        # Create product with both prices NULL
        product3 = MerchProduct.objects.create(
            business=self.business,
            name='Product - No Prices',
            kind=BusinessKind.CLOTHING,
            cost_price=None,
            selling_price=None,
            quantity_in_stock=3,
            is_active=True,
            is_archived=False
        )
        
        # Create product with both prices set (for comparison)
        product4 = MerchProduct.objects.create(
            business=self.business,
            name='Product - With Prices',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('200.00'),
            selling_price=Decimal('400.00'),
            quantity_in_stock=2,
            is_active=True,
            is_archived=False
        )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        # Inventory value should only count products with cost_price: (5 * 500) + (2 * 200) = 2500 + 400 = 2900
        # Products with NULL cost_price should be treated as 0
        self.assertEqual(response.context['inventory_value'], Decimal('2900.00'))
        
        # Retail value should only count products with selling_price: (10 * 800) + (2 * 400) = 8000 + 800 = 8800
        # Products with NULL selling_price should be treated as 0
        self.assertEqual(response.context['retail_value'], Decimal('8800.00'))
        
        # Expected margin = 8800 - 2900 = 5900
        self.assertEqual(response.context['expected_margin'], Decimal('5900.00'))


@pytest.mark.django_db
class TestClothingHub(TestCase):
    """Test clothing hub (stock overview page)"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Fashion Store',
            slug=unique_slug('Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER'
        )
        
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_hub_displays_stock_batteries(self):
        """Test that hub displays stock battery for each product"""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            quantity_in_stock=7  # 7 available
        )
        
        # Create 3 sales (initial was 10)
        for i in range(3):
            ClothingSale.objects.create(
                business=self.business,
                product=product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                sold_by=self.user
            )
        
        response = self.client.get(reverse('verticals:clothing_hub'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        panels = response.context['product_panels']
        
        self.assertEqual(len(panels), 1)
        panel = panels[0]
        
        self.assertEqual(panel['available_stock'], 7)
        self.assertEqual(panel['total_sold'], 3)
        # Battery percentage: 7 / (7 + 3) = 70%
        self.assertEqual(panel['battery_percentage'], 70)
    
    def test_hub_status_indicators(self):
        """Test that hub shows correct status indicators"""
        # Hot selling product (>10 sales)
        hot_product = MerchProduct.objects.create(
            business=self.business,
            name='Hot Item',
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=5
        )
        
        for i in range(15):
            ClothingSale.objects.create(
                business=self.business,
                product=hot_product,
                quantity=1,
                unit_price=Decimal('100.00'),
                total_price=Decimal('100.00'),
                sold_by=self.user
            )
        
        # Low stock product
        low_product = MerchProduct.objects.create(
            business=self.business,
            name='Low Stock Item',
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=2  # < 3
        )
        
        # New drop (no sales but has stock-in)
        new_product = MerchProduct.objects.create(
            business=self.business,
            name='New Item',
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=10
        )
        
        # Create stock-in log for new product (needed for "New Drop" status)
        ClothingProductLog.objects.create(
            product=new_product,
            action=ClothingProductAction.STOCK_IN,
            changes={
                'quantity_added': 10,
                'cost_price': '100.00',
                'new_stock': 10
            },
            performed_by=self.user
        )
        
        response = self.client.get(reverse('verticals:clothing_hub'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        panels = response.context['product_panels']
        
        # Find panels by product
        hot_panel = next(p for p in panels if p['product'].name == 'Hot Item')
        low_panel = next(p for p in panels if p['product'].name == 'Low Stock Item')
        new_panel = next(p for p in panels if p['product'].name == 'New Item')
        
        self.assertIn('Hot Selling', hot_panel['status'])
        self.assertIn('Low Stock', low_panel['status'])
        self.assertIn('New Drop', new_panel['status'])


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=False)
class TestClothingScanIn(TestCase):
    """Test clothing scan-in (stock-in) flow"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Fashion Store',
            slug=unique_slug('Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER'
        )
        
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_scan_in_creates_new_product(self):
        """Test that scan-in creates a new product if it doesn't exist"""
        response = self.client.post(reverse('verticals:clothing_scan_in'), {
            'category': 'suit',
            'size': 'M',
            'color': 'Black',
            'quantity': 5,
            'cost_price': '500.00',
            'selling_price': '800.00'
        }, follow=True)
        
        # Should successfully redirect and show the page (status 200 after following redirect)
        self.assertEqual(response.status_code, 200)
        
        # Product should be created
        product = MerchProduct.objects.get(
            business=self.business,
            name='Suit - M - Black'
        )
        
        self.assertEqual(product.quantity_in_stock, 5)
        self.assertEqual(product.cost_price, Decimal('500.00'))
        self.assertEqual(product.selling_price, Decimal('800.00'))
        self.assertEqual(product.category, 'suit')
        self.assertEqual(product.size, 'M')
        self.assertEqual(product.color, 'Black')
        
        # Log should be created
        log = ClothingProductLog.objects.get(
            product=product,
            action=ClothingProductAction.STOCK_IN
        )
        self.assertEqual(log.changes['quantity_added'], 5)
    
    def test_scan_in_updates_existing_product(self):
        """Test that scan-in updates stock if product exists"""
        # Create existing product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            category='suit',
            size='M',
            color='Black',
            cost_price=Decimal('500.00'),
            quantity_in_stock=10
        )
        
        response = self.client.post(reverse('verticals:clothing_scan_in'), {
            'category': 'suit',
            'size': 'M',
            'color': 'Black',
            'quantity': 3,
            'cost_price': '520.00',  # Updated cost
        }, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Product stock should be updated
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 13)  # 10 + 3
        self.assertEqual(product.cost_price, Decimal('520.00'))  # Updated


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=False)
class TestClothingSell(TestCase):
    """Test clothing sell flow"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='agent@test.com',
            email='agent@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Fashion Store',
            slug=unique_slug('Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            location=self.location,
            role='AGENT'
        )
        
        self.product = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10
        )
        
        self.client = Client()
        self.client.login(username='agent@test.com', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_sell_reduces_stock(self):
        """Test that selling reduces stock quantity"""
        response = self.client.post(reverse('verticals:clothing_sell'), {
            'product': self.product.id,
            'quantity': 2,
            'selling_price': '800.00',
            'payment_method': PaymentMethod.CASH,
            'notes': 'Test sale'
        }, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        # Stock should be reduced
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 8)  # 10 - 2
        
        # Sale should be created
        sale = ClothingSale.objects.get(product=self.product)
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.total_price, Decimal('1600.00'))  # 2 × 800
        self.assertEqual(sale.total_cost, Decimal('1000.00'))   # 2 × 500
        self.assertEqual(sale.profit, Decimal('600.00'))        # 1600 - 1000
        
        # Log should be created
        log = ClothingProductLog.objects.get(
            product=self.product,
            action=ClothingProductAction.SOLD
        )
        self.assertEqual(log.changes['quantity_sold'], 2)
    
    def test_sell_insufficient_stock(self):
        """Test that selling fails if insufficient stock"""
        response = self.client.post(reverse('verticals:clothing_sell'), {
            'product': self.product.id,
            'quantity': 20,  # More than available (10)
            'selling_price': '800.00',
            'payment_method': PaymentMethod.CASH,
        }, follow=True)
        
        # Should return to form page with error (200)
        self.assertEqual(response.status_code, 200)
        
        # Stock should not change
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 10)
        
        # No sale should be created
        self.assertEqual(ClothingSale.objects.count(), 0)
    
    def test_sell_with_different_payment_methods(self):
        """Test selling with different payment methods"""
        # Cash sale
        self.client.post(reverse('inventory:verticals:clothing_sell'), {
            'product': self.product.id,
            'quantity': 1,
            'selling_price': '800.00',
            'payment_method': PaymentMethod.CASH,
        }, follow=True)
        
        # Mobile money sale
        self.client.post(reverse('inventory:verticals:clothing_sell'), {
            'product': self.product.id,
            'quantity': 1,
            'selling_price': '800.00',
            'payment_method': PaymentMethod.MOBILE_MONEY,
        }, follow=True)
        
        # Bank sale
        self.client.post(reverse('inventory:verticals:clothing_sell'), {
            'product': self.product.id,
            'quantity': 1,
            'selling_price': '800.00',
            'payment_method': PaymentMethod.BANK,
        }, follow=True)
        
        sales = ClothingSale.objects.all()
        self.assertEqual(sales.count(), 3)
        
        payment_methods = [s.payment_method for s in sales]
        self.assertIn(PaymentMethod.CASH, payment_methods)
        self.assertIn(PaymentMethod.MOBILE_MONEY, payment_methods)
        self.assertIn(PaymentMethod.BANK, payment_methods)


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=False)
class TestClothingDashboardDateFilters(TestCase):
    """Test clothing dashboard date filtering functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Fashion Store',
            slug=unique_slug('Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER'
        )
        
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name='Test Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=100
        )
    
    def test_dashboard_mtd_default(self):
        """Test that dashboard defaults to MTD behavior when no filter is provided"""
        # Create sales this month
        now = timezone.now()
        for i in range(3):
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=now
            )
        
        # Create a sale from last month (should not be included)
        last_month = now - timedelta(days=35)
        ClothingSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=1,
            unit_price=Decimal('800.00'),
            total_price=Decimal('800.00'),
            unit_cost=Decimal('500.00'),
            total_cost=Decimal('500.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=last_month
        )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sales_mtd'], 3)  # Only this month
        self.assertEqual(response.context['active_range'], 'mtd')
    
    def test_dashboard_today_filter(self):
        """Test that ?range=today only counts today's sales"""
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        
        # Create 2 sales today
        for i in range(2):
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=now
            )
        
        # Create 3 sales yesterday
        for i in range(3):
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=yesterday
            )
        
        response = self.client.get(reverse('verticals:clothing_dashboard') + '?range=today')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sales_mtd'], 2)  # Only today
        self.assertEqual(response.context['revenue_mtd'], Decimal('1600.00'))
        self.assertEqual(response.context['active_range'], 'today')
    
    def test_dashboard_7d_filter(self):
        """Test that ?range=7d counts last 7 days"""
        now = timezone.now()
        
        # Create sales within last 7 days
        for i in range(5):
            sale_date = now - timedelta(days=i)
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=sale_date
            )
        
        # Create sales older than 7 days (should not be included)
        old_date = now - timedelta(days=10)
        for i in range(3):
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=old_date
            )
        
        response = self.client.get(reverse('verticals:clothing_dashboard') + '?range=7d')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sales_mtd'], 5)  # Only last 7 days
        self.assertEqual(response.context['active_range'], '7d')
    
    def test_dashboard_specific_date_filter(self):
        """Test that ?range=date&date=YYYY-MM-DD shows only that day"""
        now = timezone.now()
        target_date = now.date() - timedelta(days=2)
        other_date = now.date() - timedelta(days=5)
        
        # Create 3 sales on target date
        for i in range(3):
            sale_time = timezone.make_aware(
                timezone.datetime.combine(target_date, timezone.datetime.min.time())
            ) + timedelta(hours=i)
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=sale_time
            )
        
        # Create 2 sales on other date
        for i in range(2):
            sale_time = timezone.make_aware(
                timezone.datetime.combine(other_date, timezone.datetime.min.time())
            ) + timedelta(hours=i)
            ClothingSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=1,
                unit_price=Decimal('800.00'),
                total_price=Decimal('800.00'),
                unit_cost=Decimal('500.00'),
                total_cost=Decimal('500.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=sale_time
            )
        
        response = self.client.get(
            reverse('verticals:clothing_dashboard') + 
            f'?range=date&date={target_date.isoformat()}'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sales_mtd'], 3)  # Only target date
        self.assertEqual(response.context['active_range'], 'date')
        self.assertEqual(response.context['selected_date'], target_date)
    
    def test_dashboard_invalid_date_falls_back_to_mtd(self):
        """Test that invalid date parameter falls back to MTD"""
        response = self.client.get(
            reverse('verticals:clothing_dashboard') + '?range=date&date=invalid-date'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_range'], 'mtd')
    
    def test_dashboard_filters_do_not_affect_product_metrics(self):
        """Test that date filters only affect sales, not product counts"""
        # Create some products
        for i in range(5):
            MerchProduct.objects.create(
                business=self.business,
                name=f'Product {i}',
                kind=BusinessKind.CLOTHING,
                is_active=True
            )
        
        # Test with different filters
        for range_param in ['today', '7d', 'mtd']:
            response = self.client.get(
                reverse('verticals:clothing_dashboard') + f'?range={range_param}'
            )
            self.assertEqual(response.status_code, 200)
            # Product count should be 6 (1 from setUp + 5 new) regardless of date filter
            self.assertEqual(response.context['product_count'], 6)
    
    def test_dashboard_inventory_value_calculations(self):
        """Test that inventory value and retail value are calculated correctly from current stock"""
        # Create products with stock
        product1 = MerchProduct.objects.create(
            business=self.business,
            name='Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10,
            is_active=True,
            is_archived=False
        )
        
        product2 = MerchProduct.objects.create(
            business=self.business,
            name='Dress - L - Red',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('300.00'),
            selling_price=Decimal('600.00'),
            quantity_in_stock=5,
            is_active=True,
            is_archived=False
        )
        
        # Create a product with no stock (should not be included)
        product3 = MerchProduct.objects.create(
            business=self.business,
            name='Shirt - S - White',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('200.00'),
            selling_price=Decimal('400.00'),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False
        )
        
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        
        # Inventory value = (10 × 500) + (5 × 300) = 5000 + 1500 = 6500
        self.assertEqual(response.context['inventory_value'], Decimal('6500.00'))
        
        # Retail value = (10 × 800) + (5 × 600) = 8000 + 3000 = 11000
        self.assertEqual(response.context['retail_value'], Decimal('11000.00'))
        
        # Expected margin = 11000 - 6500 = 4500
        self.assertEqual(response.context['expected_margin'], Decimal('4500.00'))
    
    def test_dashboard_inventory_value_reflects_after_stock_in(self):
        """Test that inventory value updates immediately after stock-in, even without sales"""
        # Initially no stock
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['inventory_value'], Decimal('0.00'))
        self.assertEqual(response.context['retail_value'], Decimal('0.00'))
        
        # Add stock via scan-in
        self.client.post(reverse('verticals:clothing_scan_in'), {
            'category': 'suit',
            'size': 'M',
            'color': 'Black',
            'quantity': 10,
            'cost_price': '500.00',
            'selling_price': '800.00'
        }, follow=True)
        
        # Check dashboard again - should now show values
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['inventory_value'], Decimal('5000.00'))  # 10 × 500
        self.assertEqual(response.context['retail_value'], Decimal('8000.00'))     # 10 × 800
        self.assertEqual(response.context['expected_margin'], Decimal('3000.00'))  # 8000 - 5000
        
        # Sales metrics should still be 0 (no sales yet)
        self.assertEqual(response.context['revenue_mtd'], Decimal('0.00'))
        self.assertEqual(response.context['total_sales_mtd'], 0)
    
    def test_dashboard_business_isolation(self):
        """Test that dashboard only shows data for the active business"""
        # Create another business
        other_business = Business.objects.create(
            name='Other Fashion Store',
            slug=unique_slug('Other Fashion Store'),
            business_kind=BusinessKind.CLOTHING
        )
        
        # Create products for other business
        other_product = MerchProduct.objects.create(
            business=other_business,
            name='Other Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('1000.00'),
            selling_price=Decimal('1500.00'),
            quantity_in_stock=20,
            is_active=True,
            is_archived=False
        )
        
        # Create sales for other business
        now = timezone.now()
        ClothingSale.objects.create(
            business=other_business,
            product=other_product,
            quantity=5,
            unit_price=Decimal('1500.00'),
            total_price=Decimal('7500.00'),
            unit_cost=Decimal('1000.00'),
            total_cost=Decimal('5000.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now
        )
        
        # Create product and sale for our business
        our_product = MerchProduct.objects.create(
            business=self.business,
            name='Our Suit - M - Black',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10,
            is_active=True,
            is_archived=False
        )
        
        ClothingSale.objects.create(
            business=self.business,
            product=our_product,
            quantity=2,
            unit_price=Decimal('800.00'),
            total_price=Decimal('1600.00'),
            unit_cost=Decimal('500.00'),
            total_cost=Decimal('1000.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now
        )
        
        # Check dashboard - should only show our business data
        response = self.client.get(reverse('verticals:clothing_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        # Should only show our business's revenue
        self.assertEqual(response.context['revenue_mtd'], Decimal('1600.00'))
        # Should only show our business's inventory value
        self.assertEqual(response.context['inventory_value'], Decimal('5000.00'))  # 10 × 500
        # Should only show our business's retail value
        self.assertEqual(response.context['retail_value'], Decimal('8000.00'))  # 10 × 800
        # Should only show our business's sales count
        self.assertEqual(response.context['total_sales_mtd'], 1)
    
    def test_dashboard_location_scoping(self):
        """Test that dashboard respects location filtering when location is provided"""
        # Create two locations
        location1 = Location.objects.create(
            business=self.business,
            name='Location 1'
        )
        location2 = Location.objects.create(
            business=self.business,
            name='Location 2'
        )
        
        # Create products (products don't have location, but sales might)
        product1 = MerchProduct.objects.create(
            business=self.business,
            name='Product 1',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=10,
            is_active=True,
            is_archived=False
        )
        
        product2 = MerchProduct.objects.create(
            business=self.business,
            name='Product 2',
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal('300.00'),
            selling_price=Decimal('600.00'),
            quantity_in_stock=5,
            is_active=True,
            is_archived=False
        )
        
        now = timezone.now()
        
        # Create sales - if ClothingSale has location field, test it
        # Note: This test will gracefully skip location filtering if the field doesn't exist
        sale1 = ClothingSale.objects.create(
            business=self.business,
            product=product1,
            quantity=2,
            unit_price=Decimal('800.00'),
            total_price=Decimal('1600.00'),
            unit_cost=Decimal('500.00'),
            total_cost=Decimal('1000.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now
        )
        
        sale2 = ClothingSale.objects.create(
            business=self.business,
            product=product2,
            quantity=1,
            unit_price=Decimal('600.00'),
            total_price=Decimal('600.00'),
            unit_cost=Decimal('300.00'),
            total_cost=Decimal('300.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now
        )
        
        # If ClothingSale has location field, set it
        if hasattr(ClothingSale, 'location'):
            sale1.location = location1
            sale1.save()
            sale2.location = location2
            sale2.save()
            
            # Set location in session
            session = self.client.session
            session['active_location_id'] = location1.id
            session.save()
            
            # Check dashboard with location1 filter
            response = self.client.get(reverse('verticals:clothing_dashboard'))
            
            self.assertEqual(response.status_code, 200)
            # Should only show location1's revenue (sale1)
            self.assertEqual(response.context['revenue_mtd'], Decimal('1600.00'))
            # Inventory values should show all products (products don't have location)
            # But this tests that location scoping works for sales
            self.assertEqual(response.context['total_sales_mtd'], 1)  # Only sale1
        else:
            # If location field doesn't exist, just verify the dashboard works
            response = self.client.get(reverse('verticals:clothing_dashboard'))
            self.assertEqual(response.status_code, 200)
            # Should show all sales (no location filtering)
            self.assertEqual(response.context['total_sales_mtd'], 2)