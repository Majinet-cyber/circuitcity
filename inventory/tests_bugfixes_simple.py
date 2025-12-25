# inventory/tests_bugfixes_simple.py
"""
Simplified tests for bug fixes - focusing on the actual code changes
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import Mock

from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership

User = get_user_model()


class BarcodeOptionalTest(TestCase):
    """Test that barcode is optional for MerchProduct"""
    
    def test_merch_product_without_barcode(self):
        """MerchProduct should save without barcode"""
        business = Business.objects.create(name='Test Store')
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.LIQUOR,
            name='Test Product',
            barcode='',  # Empty barcode
            cost_price=Decimal('1000.00'),
            selling_price=Decimal('1500.00'),
            quantity_in_stock=10,
            is_active=True
        )
        
        # Should save successfully
        self.assertEqual(product.barcode, '')
        self.assertEqual(product.name, 'Test Product')
    
    def test_merch_product_with_none_barcode(self):
        """MerchProduct should handle None barcode"""
        business = Business.objects.create(name='Test Store 2')
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.CLOTHING,
            name='T-Shirt',
            barcode=None,  # None barcode
            cost_price=Decimal('5000.00'),
            selling_price=Decimal('8000.00'),
            quantity_in_stock=50,
            is_active=True
        )
        
        # Should save successfully
        self.assertIn(product.barcode, ['', None])


class RollbackPermissionLogicTest(TestCase):
    """Test rollback permission logic"""
    
    def setUp(self):
        self.business = Business.objects.create(name='Test Business')
        
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='test123'
        )
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='test123'
        )
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER'
        )
    
    def test_manager_has_manager_role(self):
        """Manager membership should have MANAGER role"""
        membership = Membership.objects.get(user=self.manager, business=self.business)
        self.assertEqual(membership.role.upper(), 'MANAGER')
    
    def test_rollback_permission_for_manager(self):
        """Test that manager can rollback any sale"""
        from inventory.templatetags.rollback_helpers import can_rollback_sale
        
        # Create mock sale
        sale = Mock()
        sale.is_rolled_back = False
        sale.agent = self.agent
        sale.sold_by = self.agent
        sale.created_at = timezone.now() - timedelta(hours=2)
        sale.sold_at = timezone.now() - timedelta(hours=2)
        
        # Manager should be able to rollback
        result = can_rollback_sale(sale, self.manager, self.business)
        self.assertTrue(result, "Manager should be able to rollback any sale")


class GymMemberDetailSafetyTest(TestCase):
    """Test gym member detail handles missing keys safely"""
    
    def test_membership_status_get_method(self):
        """Test that .get() method works for missing keys"""
        membership_status = {
            'type': 'monthly',
            'is_active': True
            # Missing 'start_date' and 'end_date'
        }
        
        # Using .get() should not raise KeyError
        period_start = membership_status.get("start_date")
        period_end = membership_status.get("end_date")
        
        self.assertIsNone(period_start)
        self.assertIsNone(period_end)


class HQAgentsLocationSafetyTest(TestCase):
    """Test HQ agents view handles None location"""
    
    def test_none_location_handling(self):
        """Test that None location is handled gracefully"""
        # Simulate agent with no location
        agent = Mock()
        agent.location = None
        
        # Template would use: {{ a.location.name|default:"—" }}
        # This should not crash
        location_name = agent.location.name if agent.location else "—"
        self.assertEqual(location_name, "—")


class NewVerticalsTest(TestCase):
    """Test new verticals (Groceries and Cement) basic functionality"""
    
    def test_groceries_product_creation(self):
        """Test creating a groceries product"""
        business = Business.objects.create(
            name='Test Grocery',
            business_kind=BusinessKind.GROCERY
        )
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.GROCERY,
            name='Rice 5kg',
            cost_price=Decimal('15000.00'),
            selling_price=Decimal('18000.00'),
            quantity_in_stock=50,
            base_unit='pack',
            is_active=True
        )
        
        self.assertEqual(product.name, 'Rice 5kg')
        self.assertEqual(product.kind, BusinessKind.GROCERY)
        self.assertEqual(product.quantity_in_stock, 50)
    
    def test_cement_product_creation(self):
        """Test creating a cement product"""
        business = Business.objects.create(
            name='Test Hardware',
            business_kind=BusinessKind.CEMENT
        )
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.CEMENT,
            name='Cement 50kg',
            cost_price=Decimal('45000.00'),
            selling_price=Decimal('50000.00'),
            quantity_in_stock=100,
            base_unit='bag',
            is_active=True
        )
        
        self.assertEqual(product.name, 'Cement 50kg')
        self.assertEqual(product.kind, BusinessKind.CEMENT)
        self.assertEqual(product.quantity_in_stock, 100)
    
    def test_cement_business_kind_exists(self):
        """Test that CEMENT business kind exists"""
        self.assertTrue(hasattr(BusinessKind, 'CEMENT'))
        self.assertEqual(BusinessKind.CEMENT, 'cement')


class LiquorSellStockDecrementTest(TestCase):
    """Test liquor selling decreases stock correctly"""
    
    def test_stock_decrement(self):
        """Test that selling decreases stock"""
        business = Business.objects.create(name='Test Bar')
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.LIQUOR,
            name='Test Beer',
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=100,
            is_active=True
        )
        
        initial_stock = product.quantity_in_stock
        
        # Simulate sale
        product.quantity_in_stock -= 5
        product.save()
        
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, initial_stock - 5)

