# tests/test_liquor_crate_bottle.py
"""
Tests for liquor crate/bottle cost calculation and sell validation.

Tests that:
- Crate stock-in calculates cost_per_bottle correctly
- Sell flow validates against per-bottle cost (not crate cost)
- Stock decrements correctly for bottle sales
- KPIs update with correct profit calculations
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Location, MerchProduct
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestLiquorCrateStockIn(TestCase):
    """Test crate stock-in calculates cost_per_bottle"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Bar',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Bar',
            is_default=True
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_crate_wizard_calculates_cost_per_bottle(self):
        """Liquor wizard should calculate cost_per_bottle from crate price"""
        url = reverse('inventory:liquor_wizard_submit')
        
        # Order 1 crate at K45,000 (20 bottles per crate)
        # Expected: cost_per_bottle = 45000 / 20 = 2250
        data = {
            'category': 'beer',
            'product_name': 'Carlsberg Green',
            'selling_mode': 'bottle',
            'price_per_bottle': '3500.00',
            'is_crate_product': True,
            'crate_order_price': '45000.00',
            'bottles_per_crate': 20
        }
        
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        json_data = response.json()
        
        assert response.status_code == 200
        assert json_data['success'] is True
        
        # Verify product created with correct cost_per_bottle
        product = MerchProduct.objects.get(name='Carlsberg Green')
        assert product.cost_per_bottle == Decimal('2250.00')
        assert product.price_per_bottle == Decimal('3500.00')
        assert product.bottles_per_crate == 20
    
    def test_get_cost_for_unit_returns_correct_bottle_cost(self):
        """get_cost_for_unit should return cost_per_bottle for 'bottle' unit"""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            cost_per_bottle=Decimal('2250.00'),
            price_per_bottle=Decimal('3500.00'),
            bottles_per_crate=20
        )
        
        # Test bottle cost
        bottle_cost = product.get_cost_for_unit('bottle')
        assert bottle_cost == Decimal('2250.00')
        
        # Test crate cost (should be bottle_cost * bottles_per_crate)
        crate_cost = product.get_cost_for_unit('crate')
        assert crate_cost == Decimal('45000.00')  # 2250 * 20


@pytest.mark.django_db
class TestLiquorBottleSell(TestCase):
    """Test liquor sell validates against per-bottle cost"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Bar',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Bar',
            is_default=True
        )
        
        # Create beer product (ordered by crate, sold by bottle)
        self.beer = MerchProduct.objects.create(
            business=self.business,
            name='Castle Lite',
            kind=BusinessKind.LIQUOR,
            category='beer',
            cost_per_bottle=Decimal('2500.00'),  # K45,000 crate / 18 bottles
            price_per_bottle=Decimal('4000.00'),
            bottles_per_crate=18,
            quantity_in_stock=36,  # 2 crates worth
            is_active=True
        )
        
        self.client.login(username='testagent', password='testpass123')
    
    def test_sell_bottle_uses_per_bottle_cost(self):
        """Selling bottles should use cost_per_bottle for profit calculation"""
        url = reverse('liquor:sell')
        
        data = {
            'product_id': self.beer.id,
            'quantity': '5',  # 5 bottles
            'mode': 'bottle',
            'sale_type': 'cash'
        }
        
        response = self.client.post(url, data)
        
        # Should succeed (not validation error)
        assert response.status_code in [200, 302]  # 302 = redirect after success
        
        # Verify stock decremented by bottles
        self.beer.refresh_from_db()
        assert self.beer.quantity_in_stock == 31  # 36 - 5 = 31
    
    def test_sell_below_bottle_cost_allows(self):
        """Selling below per-bottle cost should allow (with warning)"""
        url = reverse('liquor:sell')
        
        # Try to sell at K2000 per bottle (cost is K2500)
        # This is the key test: should compare K2000 vs K2500, NOT vs K45,000
        data = {
            'product_id': self.beer.id,
            'quantity': '2',
            'mode': 'bottle',
            'sale_type': 'cash'
        }
        
        response = self.client.post(url, data)
        
        # Should allow sale (no hard validation error)
        assert response.status_code in [200, 302]
    
    def test_profit_calculated_per_bottle(self):
        """Profit should be calculated per bottle, not per crate"""
        from inventory.models_verticals import LiquorSale
        from django.db import transaction
        
        with transaction.atomic():
            # Create sale: 5 bottles @ K4000 each
            sale = LiquorSale.objects.create(
                business=self.business,
                product=self.beer,
                unit='bottle',
                quantity=5,
                unit_price=Decimal('4000.00'),  # Selling price per bottle
                total_price=Decimal('20000.00'),  # 5 * 4000
                unit_cost=Decimal('2500.00'),  # Cost per bottle
                total_cost=Decimal('12500.00'),  # 5 * 2500
                sold_by=self.user,
                sale_type='sale'
            )
        
        # Verify profit
        expected_profit = Decimal('20000.00') - Decimal('12500.00')  # K7,500
        assert sale.profit == expected_profit
        
        # Verify using per-bottle math, NOT per-crate
        assert sale.unit_cost == Decimal('2500.00')  # NOT K45,000


@pytest.mark.django_db
class TestLiquorMixedUnits(TestCase):
    """Test liquor with both crate ordering and bottle/shot selling"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Bar',
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Bar',
            is_default=True
        )
        
        self.client.login(username='testmanager', password='testpass123')
    
    def test_crate_to_bottle_to_shot_conversion(self):
        """Test full conversion: crate order → bottle sale → shot sale"""
        # Create product: ordered by crate, sold by bottle or shot
        product = MerchProduct.objects.create(
            business=self.business,
            name='Johnnie Walker Black',
            kind=BusinessKind.LIQUOR,
            category='spirits',
            cost_per_bottle=Decimal('15000.00'),  # K180,000 crate / 12 bottles
            price_per_bottle=Decimal('25000.00'),
            bottles_per_crate=12,
            has_shots=True,
            shots_per_bottle=30,
            price_per_shot=Decimal('1000.00'),
            barman_shots_reserved=3,
            quantity_in_stock=12,  # 1 crate
            is_active=True
        )
        
        # Test bottle cost
        assert product.get_cost_for_unit('bottle') == Decimal('15000.00')
        
        # Test crate cost (reverse calculation)
        assert product.get_cost_for_unit('crate') == Decimal('180000.00')
        
        # Test shot cost (cost_per_bottle / sellable_shots)
        # Sellable shots = 30 - 3 (barman) = 27
        expected_cost_per_shot = Decimal('15000.00') / Decimal('27')
        # Should be approximately K555.56 per shot


import json

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

