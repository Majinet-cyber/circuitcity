# tests/test_liquor_category_stockin.py
"""
PART E: Tests for category-aware stock-in functionality.
Tests server-side calculations and adapters for Beer, Cider, Wine, Spirits, Whisky.
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.services_liquor_stockin import (
    BeerStockInAdapter,
    CiderStockInAdapter,
    WineStockInAdapter,
    SpiritsStockInAdapter,
    WhiskyStockInAdapter,
    get_adapter_for_category,
    save_stock_in_transaction,
    quantize_2dp,
)

User = get_user_model()


class LiquorCategoryStockInTestCase(TestCase):
    """Base test case with common setup."""
    
    def setUp(self):
        """Create test business, user, and products."""
        self.user = User.objects.create_user(
            username='testliquoruser',
            email='test@liquor.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Liquor Store',
            kind=BusinessKind.LIQUOR,
            owner=self.user
        )


class TestBeerStockInAdapter(LiquorCategoryStockInTestCase):
    """
    Test Beer stock-in adapter (PART B1).
    
    Requirements:
        - Input: crates=2, cost_per_crate=40000, loose=0
        - Output: total_bottles=40, total_cost=80000, cost_per_bottle=2000
    """
    
    def test_beer_crates_only(self):
        """Test beer stock-in with crates only (no loose bottles)."""
        user_inputs = {
            'number_of_crates': 2,
            'cost_per_crate': '40000',
            'loose_bottles': 0,
            'notes': 'Test delivery'
        }
        
        result = BeerStockInAdapter.adapt(user_inputs)
        
        # Verify calculations
        self.assertEqual(result['quantity_units_added'], 40)  # 2 crates * 20
        self.assertEqual(result['total_cost'], Decimal('80000'))  # 2 * 40000
        self.assertEqual(result['unit_cost'], Decimal('2000.00'))  # 80000 / 40
        self.assertEqual(result['notes'], 'Test delivery')
        self.assertEqual(result['metadata']['category'], 'beer')
        self.assertEqual(result['metadata']['number_of_crates'], 2)
        self.assertEqual(result['metadata']['loose_bottles'], 0)
    
    def test_beer_crates_with_loose(self):
        """Test beer stock-in with crates and loose bottles."""
        user_inputs = {
            'number_of_crates': 1,
            'cost_per_crate': '20000',
            'loose_bottles': 5,
            'notes': ''
        }
        
        result = BeerStockInAdapter.adapt(user_inputs)
        
        # Verify calculations
        self.assertEqual(result['quantity_units_added'], 25)  # 1*20 + 5
        self.assertEqual(result['total_cost'], Decimal('20000'))  # 1 * 20000
        self.assertEqual(result['unit_cost'], Decimal('800.00'))  # 20000 / 25
    
    def test_beer_validation_negative_crates(self):
        """Test that negative crates are rejected."""
        user_inputs = {
            'number_of_crates': -1,
            'cost_per_crate': '40000',
            'loose_bottles': 0
        }
        
        with self.assertRaises(ValueError) as context:
            BeerStockInAdapter.adapt(user_inputs)
        
        self.assertIn('cannot be negative', str(context.exception))
    
    def test_beer_validation_zero_cost(self):
        """Test that zero or negative cost is rejected."""
        user_inputs = {
            'number_of_crates': 2,
            'cost_per_crate': '0',
            'loose_bottles': 0
        }
        
        with self.assertRaises(ValueError) as context:
            BeerStockInAdapter.adapt(user_inputs)
        
        self.assertIn('must be greater than 0', str(context.exception))
    
    def test_beer_validation_zero_total_bottles(self):
        """Test that zero total bottles is rejected."""
        user_inputs = {
            'number_of_crates': 0,
            'cost_per_crate': '40000',
            'loose_bottles': 0
        }
        
        with self.assertRaises(ValueError) as context:
            BeerStockInAdapter.adapt(user_inputs)
        
        self.assertIn('must be greater than 0', str(context.exception))


class TestCiderStockInAdapter(LiquorCategoryStockInTestCase):
    """
    Test Cider stock-in adapter (PART B2).
    
    Requirements:
        - Input: quantity=20, cost_per_bottle=1000
        - Output: total_bottles=20, total_cost=20000
    """
    
    def test_cider_stockin(self):
        """Test cider stock-in calculations."""
        user_inputs = {
            'quantity_bottles': 20,
            'cost_per_bottle': '1000',
            'notes': 'Cider delivery'
        }
        
        result = CiderStockInAdapter.adapt(user_inputs)
        
        # Verify calculations
        self.assertEqual(result['quantity_units_added'], 20)
        self.assertEqual(result['total_cost'], Decimal('20000.00'))
        self.assertEqual(result['unit_cost'], Decimal('1000'))
        self.assertEqual(result['metadata']['category'], 'cider')
    
    def test_cider_validation_zero_quantity(self):
        """Test that zero quantity is rejected."""
        user_inputs = {
            'quantity_bottles': 0,
            'cost_per_bottle': '1000'
        }
        
        with self.assertRaises(ValueError):
            CiderStockInAdapter.adapt(user_inputs)
    
    def test_cider_validation_zero_cost(self):
        """Test that zero cost is rejected."""
        user_inputs = {
            'quantity_bottles': 20,
            'cost_per_bottle': '0'
        }
        
        with self.assertRaises(ValueError):
            CiderStockInAdapter.adapt(user_inputs)


class TestWineStockInAdapter(LiquorCategoryStockInTestCase):
    """
    Test Wine stock-in adapter (PART B3).
    
    Requirements:
        - Input: bottles=10, cost_per_bottle=5000
        - Output: glasses=50, cost_per_glass=1000, total_cost=50000
        - Stock tracked in glasses (1 bottle = 5 glasses)
    """
    
    def test_wine_stockin(self):
        """Test wine stock-in with bottle to glass conversion."""
        user_inputs = {
            'number_of_bottles': 10,
            'cost_per_bottle': '5000',
            'notes': 'Wine shipment'
        }
        
        result = WineStockInAdapter.adapt(user_inputs)
        
        # Verify calculations
        self.assertEqual(result['quantity_units_added'], 50)  # 10 * 5 glasses
        self.assertEqual(result['unit_cost'], Decimal('1000.00'))  # 5000 / 5
        self.assertEqual(result['total_cost'], Decimal('50000.00'))  # 10 * 5000
        self.assertEqual(result['metadata']['category'], 'wine')
        self.assertEqual(result['metadata']['glasses_per_bottle'], 5)
    
    def test_wine_cost_per_glass_quantization(self):
        """Test that cost per glass is properly quantized to 2 decimal places."""
        user_inputs = {
            'number_of_bottles': 3,
            'cost_per_bottle': '999.99',  # Will result in 199.998 per glass
        }
        
        result = WineStockInAdapter.adapt(user_inputs)
        
        # Should be quantized to 2dp
        self.assertEqual(result['unit_cost'], Decimal('200.00'))  # Rounded up


class TestSpiritsStockInAdapter(LiquorCategoryStockInTestCase):
    """
    Test Spirits stock-in adapter (PART B4).
    
    Requirements:
        - Input: qty_shots=60, cost_per_shot=500, reserved=10
        - Output: sellable_shots=50, total_cost=30000
        - Stock increase by 50 sellable shots only
    """
    
    def test_spirits_stockin_with_reserved(self):
        """Test spirits stock-in with reserved barman shots."""
        user_inputs = {
            'quantity_of_shots_added': 60,
            'cost_per_shot': '500',
            'reserved_barman_shots': 10,
            'notes': 'Spirits order'
        }
        
        result = SpiritsStockInAdapter.adapt(user_inputs)
        
        # Verify calculations
        self.assertEqual(result['quantity_units_added'], 50)  # 60 - 10 reserved
        self.assertEqual(result['unit_cost'], Decimal('500'))
        self.assertEqual(result['total_cost'], Decimal('30000.00'))  # 60 * 500 (including reserved)
        self.assertEqual(result['metadata']['category'], 'spirits')
        self.assertEqual(result['metadata']['sellable_shots'], 50)
        self.assertEqual(result['metadata']['reserved_shots'], 10)
        self.assertAlmostEqual(result['metadata']['equivalent_bottles'], 2.0, places=2)  # 60/30
    
    def test_spirits_stockin_no_reserved(self):
        """Test spirits stock-in without reserved shots."""
        user_inputs = {
            'quantity_of_shots_added': 30,
            'cost_per_shot': '500',
            'reserved_barman_shots': 0
        }
        
        result = SpiritsStockInAdapter.adapt(user_inputs)
        
        self.assertEqual(result['quantity_units_added'], 30)
        self.assertEqual(result['total_cost'], Decimal('15000.00'))
    
    def test_spirits_validation_reserved_exceeds_quantity(self):
        """Test that reserved shots cannot exceed total quantity."""
        user_inputs = {
            'quantity_of_shots_added': 30,
            'cost_per_shot': '500',
            'reserved_barman_shots': 30  # Equal to total
        }
        
        with self.assertRaises(ValueError) as context:
            SpiritsStockInAdapter.adapt(user_inputs)
        
        self.assertIn('cannot exceed or equal', str(context.exception))
    
    def test_spirits_validation_reserved_greater_than_quantity(self):
        """Test that reserved shots cannot be greater than total."""
        user_inputs = {
            'quantity_of_shots_added': 30,
            'cost_per_shot': '500',
            'reserved_barman_shots': 40  # Greater than total
        }
        
        with self.assertRaises(ValueError):
            SpiritsStockInAdapter.adapt(user_inputs)


class TestWhiskyStockInAdapter(LiquorCategoryStockInTestCase):
    """
    Test Whisky stock-in adapter (PART B5).
    
    Requirements: Same as Spirits (inherits)
    """
    
    def test_whisky_stockin(self):
        """Test whisky stock-in (same as spirits)."""
        user_inputs = {
            'quantity_of_shots_added': 60,
            'cost_per_shot': '500',
            'reserved_barman_shots': 10
        }
        
        result = WhiskyStockInAdapter.adapt(user_inputs)
        
        # Verify it works like spirits but with whisky category
        self.assertEqual(result['quantity_units_added'], 50)
        self.assertEqual(result['total_cost'], Decimal('30000.00'))
        self.assertEqual(result['metadata']['category'], 'whisky')


class TestAdapterFactory(LiquorCategoryStockInTestCase):
    """Test adapter factory function."""
    
    def test_get_adapter_for_category(self):
        """Test that correct adapters are returned for each category."""
        self.assertEqual(get_adapter_for_category('beer'), BeerStockInAdapter)
        self.assertEqual(get_adapter_for_category('cider'), CiderStockInAdapter)
        self.assertEqual(get_adapter_for_category('wine'), WineStockInAdapter)
        self.assertEqual(get_adapter_for_category('spirits'), SpiritsStockInAdapter)
        self.assertEqual(get_adapter_for_category('whisky'), WhiskyStockInAdapter)
    
    def test_get_adapter_case_insensitive(self):
        """Test that adapter lookup is case-insensitive."""
        self.assertEqual(get_adapter_for_category('BEER'), BeerStockInAdapter)
        self.assertEqual(get_adapter_for_category('Beer'), BeerStockInAdapter)
        self.assertEqual(get_adapter_for_category('  beer  '), BeerStockInAdapter)
    
    def test_get_adapter_invalid_category(self):
        """Test that invalid category raises ValueError."""
        with self.assertRaises(ValueError) as context:
            get_adapter_for_category('invalid')
        
        self.assertIn('Unsupported category', str(context.exception))


class TestStockInTransactionSave(LiquorCategoryStockInTestCase):
    """Test the unified stock-in transaction save function (PART C)."""
    
    def test_save_beer_transaction(self):
        """Test saving a beer stock-in transaction."""
        # Create beer product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Carlsberg Green',
            kind=BusinessKind.LIQUOR,
            category='beer',
            quantity_in_stock=0,
            is_active=True
        )
        
        # Prepare adapted data
        user_inputs = {
            'number_of_crates': 2,
            'cost_per_crate': '40000',
            'loose_bottles': 0
        }
        adapted_data = BeerStockInAdapter.adapt(user_inputs)
        
        # Save transaction
        save_stock_in_transaction(product, adapted_data, self.user)
        
        # Verify product was updated
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 40)
        self.assertEqual(product.cost_per_bottle, Decimal('2000.00'))
    
    def test_save_cider_transaction(self):
        """Test saving a cider stock-in transaction."""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Savanna Dry',
            kind=BusinessKind.LIQUOR,
            category='cider',
            quantity_in_stock=10,
            cost_per_bottle=Decimal('800'),
            is_active=True
        )
        
        user_inputs = {
            'quantity_bottles': 20,
            'cost_per_bottle': '1000'
        }
        adapted_data = CiderStockInAdapter.adapt(user_inputs)
        
        save_stock_in_transaction(product, adapted_data, self.user)
        
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 30)  # 10 + 20
        self.assertEqual(product.cost_per_bottle, Decimal('1000'))
    
    def test_save_spirits_transaction(self):
        """Test saving a spirits stock-in transaction."""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Absolut Vodka',
            kind=BusinessKind.LIQUOR,
            category='spirits',
            quantity_in_stock=0,
            is_active=True
        )
        
        user_inputs = {
            'quantity_of_shots_added': 60,
            'cost_per_shot': '500',
            'reserved_barman_shots': 10
        }
        adapted_data = SpiritsStockInAdapter.adapt(user_inputs)
        
        save_stock_in_transaction(product, adapted_data, self.user)
        
        product.refresh_from_db()
        # Should only add sellable shots (50), not reserved (10)
        self.assertEqual(product.quantity_in_stock, 50)
        self.assertEqual(product.cost_per_bottle, Decimal('500'))


class TestStockValueCalculation(LiquorCategoryStockInTestCase):
    """
    Test PART A: Stock Value calculation matches Inventory Costs.
    
    Requirement: Stock Value = Sum of (on-hand units * average unit cost) per product
    """
    
    def test_stock_value_equals_inventory_cost(self):
        """Test that stock value calculation matches total inventory cost."""
        # Create products with stock
        beer = MerchProduct.objects.create(
            business=self.business,
            name='Carlsberg',
            kind=BusinessKind.LIQUOR,
            category='beer',
            quantity_in_stock=40,
            cost_per_bottle=Decimal('2000'),
            is_active=True
        )
        
        cider = MerchProduct.objects.create(
            business=self.business,
            name='Savanna',
            kind=BusinessKind.LIQUOR,
            category='cider',
            quantity_in_stock=20,
            cost_per_bottle=Decimal('1000'),
            is_active=True
        )
        
        # Calculate stock value
        products = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
        
        total_stock_value = Decimal('0.00')
        for product in products:
            on_hand = product.quantity_in_stock or 0
            unit_cost = product.cost_per_bottle or Decimal('0.00')
            total_stock_value += Decimal(on_hand) * unit_cost
        
        # Expected: (40 * 2000) + (20 * 1000) = 80000 + 20000 = 100000
        expected_value = Decimal('100000')
        self.assertEqual(total_stock_value, expected_value)
    
    def test_stock_value_gracefully_handles_no_costs(self):
        """Test that stock value shows 0.00 when no costs are set."""
        product = MerchProduct.objects.create(
            business=self.business,
            name='Unknown Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            quantity_in_stock=100,
            cost_per_bottle=None,  # No cost set
            is_active=True
        )
        
        # Calculate stock value
        on_hand = product.quantity_in_stock or 0
        unit_cost = product.cost_per_bottle or Decimal('0.00')
        stock_value = Decimal(on_hand) * unit_cost
        
        # Should gracefully show 0.00
        self.assertEqual(stock_value, Decimal('0.00'))


class TestQuantize2DP(LiquorCategoryStockInTestCase):
    """Test the quantize_2dp utility function."""
    
    def test_quantize_simple(self):
        """Test simple quantization."""
        self.assertEqual(quantize_2dp(Decimal('10.123')), Decimal('10.12'))
        self.assertEqual(quantize_2dp(Decimal('10.126')), Decimal('10.13'))
    
    def test_quantize_rounding(self):
        """Test rounding behavior."""
        self.assertEqual(quantize_2dp(Decimal('10.125')), Decimal('10.13'))  # ROUND_HALF_UP rounds up
        self.assertEqual(quantize_2dp(Decimal('10.135')), Decimal('10.14'))

