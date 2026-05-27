"""
Tests for liquor payment mix and unit pricing (spirits/wine).
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale, LiquorShift, PaymentMethod, LiquorUnitType, LiquorSaleType
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestLiquorPaymentMix(TestCase):
    """Test liquor sale payment mix functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Liquor Store',
            slug='test-liquor-store',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create a liquor product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=Decimal('1500.00'),
            cost_per_bottle=Decimal('1000.00'),
            quantity_in_stock=50
        )
        
        # Create shift
        self.shift = LiquorShift.objects.create(
            business=self.business,
            barman=self.user,
            created_by=self.user,
            started_at=timezone.now()
        )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_payment_mix_all_cash(self):
        """Test sale with full cash payment"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.product,
            shift=self.shift,
            unit=LiquorUnitType.BOTTLE,
            quantity=2,
            unit_price=Decimal('1500.00'),
            total_price=Decimal('3000.00'),
            unit_cost=Decimal('1000.00'),
            total_cost=Decimal('2000.00'),
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user,
            cash_amount=Decimal('3000.00'),
            bank_amount=Decimal('0.00'),
            mobile_money_amount=Decimal('0.00')
        )
        
        self.assertEqual(sale.cash_amount, Decimal('3000.00'))
        self.assertEqual(sale.payment_method, PaymentMethod.CASH)
        self.assertEqual(sale.total_price, Decimal('3000.00'))
    
    def test_payment_mix_split(self):
        """Test sale with split payment"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.product,
            shift=self.shift,
            unit=LiquorUnitType.BOTTLE,
            quantity=2,
            unit_price=Decimal('1500.00'),
            total_price=Decimal('3000.00'),
            unit_cost=Decimal('1000.00'),
            total_cost=Decimal('2000.00'),
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user,
            cash_amount=Decimal('1000.00'),
            bank_amount=Decimal('1000.00'),
            mobile_money_amount=Decimal('1000.00')
        )
        
        payment_total = sale.cash_amount + sale.bank_amount + sale.mobile_money_amount
        self.assertEqual(payment_total, sale.total_price)
        self.assertEqual(payment_total, Decimal('3000.00'))
    
    def test_payment_mix_default_to_cash(self):
        """Test that payment mix defaults to cash if all amounts are zero"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.product,
            shift=self.shift,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=Decimal('1500.00'),
            total_price=Decimal('1500.00'),
            unit_cost=Decimal('1000.00'),
            total_cost=Decimal('1000.00'),
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user
            # Not providing any payment amounts
        )
        
        # Model should auto-set cash_amount = total_price
        self.assertEqual(sale.cash_amount, Decimal('1500.00'))
        self.assertEqual(sale.payment_method, PaymentMethod.CASH)


@pytest.mark.django_db
class TestLiquorUnitPricing(TestCase):
    """Test spirits/whiskey shot pricing and wine glass pricing"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Liquor Store',
            slug='test-liquor-store',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create spirits product with shot pricing
        self.spirits_product = MerchProduct.objects.create(
            business=self.business,
            name='Test Whiskey',
            kind=BusinessKind.LIQUOR,
            category='spirits',
            has_shots=True,
            shots_per_bottle=25,
            price_per_bottle=Decimal('15000.00'),
            price_per_shot=Decimal('700.00'),
            cost_per_bottle=Decimal('10000.00'),
            cost_per_shot=Decimal('400.00'),
            quantity_in_stock=10
        )
        
        # Create wine product with glass pricing
        self.wine_product = MerchProduct.objects.create(
            business=self.business,
            name='Test Wine',
            kind=BusinessKind.LIQUOR,
            category='wine',
            has_glasses=True,
            glasses_per_bottle=5,
            price_per_bottle=Decimal('8000.00'),
            price_per_glass=Decimal('1800.00'),
            cost_per_bottle=Decimal('5000.00'),
            cost_per_glass=Decimal('1000.00'),
            quantity_in_stock=15
        )
        
        # Create shift
        self.shift = LiquorShift.objects.create(
            business=self.business,
            barman=self.user,
            created_by=self.user,
            started_at=timezone.now()
        )
    
    def test_spirits_bottle_sale(self):
        """Test selling spirits by bottle"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.spirits_product,
            shift=self.shift,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=self.spirits_product.price_per_bottle,
            total_price=self.spirits_product.price_per_bottle,
            unit_cost=self.spirits_product.cost_per_bottle,
            total_cost=self.spirits_product.cost_per_bottle,
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user
        )
        
        self.assertEqual(sale.unit, LiquorUnitType.BOTTLE)
        self.assertEqual(sale.unit_price, Decimal('15000.00'))
        self.assertEqual(sale.total_price, Decimal('15000.00'))
    
    def test_spirits_shot_sale(self):
        """Test selling spirits by shot"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.spirits_product,
            shift=self.shift,
            unit=LiquorUnitType.SHOT,
            quantity=3,
            unit_price=self.spirits_product.price_per_shot,
            total_price=Decimal('2100.00'),  # 3 * 700
            unit_cost=self.spirits_product.cost_per_shot,
            total_cost=Decimal('1200.00'),  # 3 * 400
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user
        )
        
        self.assertEqual(sale.unit, LiquorUnitType.SHOT)
        self.assertEqual(sale.unit_price, Decimal('700.00'))
        self.assertEqual(sale.quantity, 3)
        self.assertEqual(sale.total_price, Decimal('2100.00'))
    
    def test_wine_bottle_sale(self):
        """Test selling wine by bottle"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.wine_product,
            shift=self.shift,
            unit=LiquorUnitType.BOTTLE,
            quantity=2,
            unit_price=self.wine_product.price_per_bottle,
            total_price=Decimal('16000.00'),  # 2 * 8000
            unit_cost=self.wine_product.cost_per_bottle,
            total_cost=Decimal('10000.00'),  # 2 * 5000
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user
        )
        
        self.assertEqual(sale.unit, LiquorUnitType.BOTTLE)
        self.assertEqual(sale.unit_price, Decimal('8000.00'))
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.total_price, Decimal('16000.00'))
    
    def test_wine_glass_sale(self):
        """Test selling wine by glass"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.wine_product,
            shift=self.shift,
            unit=LiquorUnitType.GLASS,
            quantity=4,
            unit_price=self.wine_product.price_per_glass,
            total_price=Decimal('7200.00'),  # 4 * 1800
            unit_cost=self.wine_product.cost_per_glass,
            total_cost=Decimal('4000.00'),  # 4 * 1000
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user
        )
        
        self.assertEqual(sale.unit, LiquorUnitType.GLASS)
        self.assertEqual(sale.unit_price, Decimal('1800.00'))
        self.assertEqual(sale.quantity, 4)
        self.assertEqual(sale.total_price, Decimal('7200.00'))
    
    def test_get_price_for_unit_method(self):
        """Test MerchProduct.get_price_for_unit() method"""
        # Test bottle price
        bottle_price = self.spirits_product.get_price_for_unit('bottle')
        self.assertEqual(bottle_price, Decimal('15000.00'))
        
        # Test shot price
        shot_price = self.spirits_product.get_price_for_unit('shot')
        self.assertEqual(shot_price, Decimal('700.00'))
        
        # Test glass price
        glass_price = self.wine_product.get_price_for_unit('glass')
        self.assertEqual(glass_price, Decimal('1800.00'))
    
    def test_get_cost_for_unit_method(self):
        """Test MerchProduct.get_cost_for_unit() method"""
        # Test bottle cost
        bottle_cost = self.spirits_product.get_cost_for_unit('bottle')
        self.assertEqual(bottle_cost, Decimal('10000.00'))
        
        # Test shot cost
        shot_cost = self.spirits_product.get_cost_for_unit('shot')
        self.assertEqual(shot_cost, Decimal('400.00'))
        
        # Test glass cost
        glass_cost = self.wine_product.get_cost_for_unit('glass')
        self.assertEqual(glass_cost, Decimal('1000.00'))


@pytest.mark.django_db
class TestPaymentMixWithUnitPricing(TestCase):
    """Test payment mix combined with unit pricing"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Liquor Store',
            slug='test-liquor-store',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status='ACTIVE'
        )
        
        self.wine_product = MerchProduct.objects.create(
            business=self.business,
            name='Premium Wine',
            kind=BusinessKind.LIQUOR,
            category='wine',
            has_glasses=True,
            glasses_per_bottle=5,
            price_per_bottle=Decimal('10000.00'),
            price_per_glass=Decimal('2200.00'),
            cost_per_bottle=Decimal('6000.00'),
            cost_per_glass=Decimal('1200.00'),
            quantity_in_stock=20
        )
        
        self.shift = LiquorShift.objects.create(
            business=self.business,
            barman=self.user,
            started_at=timezone.now()
        )
    
    def test_wine_glass_sale_with_payment_mix(self):
        """Test selling wine by glass with split payment"""
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.wine_product,
            shift=self.shift,
            unit=LiquorUnitType.GLASS,
            quantity=3,
            unit_price=self.wine_product.price_per_glass,
            total_price=Decimal('6600.00'),  # 3 * 2200
            unit_cost=self.wine_product.cost_per_glass,
            total_cost=Decimal('3600.00'),  # 3 * 1200
            sale_type=LiquorSaleType.SALE,
            sold_by=self.user,
            cash_amount=Decimal('3000.00'),
            bank_amount=Decimal('2000.00'),
            mobile_money_amount=Decimal('1600.00')
        )
        
        # Verify unit pricing
        self.assertEqual(sale.unit, LiquorUnitType.GLASS)
        self.assertEqual(sale.quantity, 3)
        self.assertEqual(sale.total_price, Decimal('6600.00'))
        
        # Verify payment mix
        payment_total = sale.cash_amount + sale.bank_amount + sale.mobile_money_amount
        self.assertEqual(payment_total, sale.total_price)
        
        # Verify profit calculation
        profit = sale.profit
        self.assertEqual(profit, Decimal('3000.00'))  # 6600 - 3600

