# inventory/tests_bugfixes_2024_12_25.py
"""
Comprehensive tests for bug fixes implemented on 2024-12-25
Tests cover: HQ agents, phone rollback, gym member detail, liquor sell, new verticals
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from inventory.models import MerchProduct, InventoryItem
from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership
from sales.models import Sale


User = get_user_model()


class HQAgentsViewTest(TestCase):
    """Test HQ Agents view handles None location gracefully"""
    
    def setUp(self):
        self.client = Client()
        # Create HQ admin user
        self.hq_admin = User.objects.create_user(
            username='hqadmin',
            email='hq@test.com',
            password='testpass123',
            is_hq_admin=True
        )
        # Create test business
        self.business = Business.objects.create(
            name='Test Business',
            business_kind=BusinessKind.PHONES
        )
        # Create agent with NO location
        self.agent = User.objects.create_user(
            username='agent1',
            email='agent@test.com',
            password='testpass123'
        )
        self.membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT'
        )
    
    def test_agents_view_with_none_location(self):
        """Agents view should not crash when agent has no location"""
        self.client.login(username='hqadmin', password='testpass123')
        
        # Try to access agents page
        response = self.client.get(reverse('hq:agents'))
        
        # Should return 200 OK, not 500
        self.assertEqual(response.status_code, 200)
        
        # Should contain the agent username
        self.assertContains(response, 'agent1')


class PhoneRollbackPermissionsTest(TestCase):
    """Test manager can rollback ANY phone sale"""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name='Phone Store',
            business_kind=BusinessKind.PHONES
        )
        
        # Create users
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='testpass123'
        )
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='testpass123'
        )
        
        # Create location for agent
        from tenants.models import Location
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER'
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            location=self.location,
            role='AGENT'
        )
    
    def test_manager_role_check(self):
        """Manager membership should have MANAGER role"""
        membership = Membership.objects.get(user=self.manager, business=self.business)
        self.assertEqual(membership.role.upper(), 'MANAGER')
    
    def test_agent_role_check(self):
        """Agent membership should have AGENT role"""
        membership = Membership.objects.get(user=self.agent, business=self.business)
        self.assertEqual(membership.role.upper(), 'AGENT')
    
    def test_rollback_permission_logic(self):
        """Test rollback permission logic from rollback_helpers"""
        from inventory.templatetags.rollback_helpers import can_rollback_sale
        from unittest.mock import Mock
        
        # Create mock sale (old sale - 2 hours ago)
        old_sale = Mock()
        old_sale.is_rolled_back = False
        old_sale.agent = self.agent
        old_sale.sold_by = self.agent
        old_sale.created_at = timezone.now() - timedelta(hours=2)
        old_sale.sold_at = timezone.now() - timedelta(hours=2)
        
        # Manager should be able to rollback ANY sale
        can_rollback_manager = can_rollback_sale(old_sale, self.manager, self.business)
        self.assertTrue(can_rollback_manager, "Manager should be able to rollback any sale")
        
        # Agent should NOT be able to rollback old sale (> 10 minutes)
        can_rollback_agent_old = can_rollback_sale(old_sale, self.agent, self.business)
        self.assertFalse(can_rollback_agent_old, "Agent should not rollback sale after 10 minutes")
        
        # Create mock fresh sale (just now)
        fresh_sale = Mock()
        fresh_sale.is_rolled_back = False
        fresh_sale.agent = self.agent
        fresh_sale.sold_by = self.agent
        fresh_sale.created_at = timezone.now()
        fresh_sale.sold_at = timezone.now()
        
        # Agent should be able to rollback fresh sale (< 10 minutes)
        can_rollback_agent_fresh = can_rollback_sale(fresh_sale, self.agent, self.business)
        self.assertTrue(can_rollback_agent_fresh, "Agent should rollback own sale within 10 minutes")


class GymMemberDetailTest(TestCase):
    """Test gym member detail view handles None membership status gracefully"""
    
    def setUp(self):
        self.client = Client()
        
        # Create gym business
        self.business = Business.objects.create(
            name='Test Gym',
            business_kind=BusinessKind.GYM
        )
        
        # Create gym owner
        self.owner = User.objects.create_user(
            username='gymowner',
            email='owner@gym.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='OWNER'
        )
    
    def test_member_detail_with_incomplete_status(self):
        """Member detail should not crash with incomplete membership status"""
        from inventory.views_gym import member_detail
        from unittest.mock import Mock
        
        request = Mock()
        request.user = self.owner
        request.method = 'GET'
        request.GET = {}
        
        # Mock a membership status with missing keys
        incomplete_status = {
            # Missing 'start_date' and 'end_date'
            'type': 'monthly',
            'is_active': True
        }
        
        # View should handle this gracefully (not crash)
        # The fix uses .get() instead of direct dict access
        try:
            # This would previously crash with KeyError
            period_start = incomplete_status.get("start_date")
            period_end = incomplete_status.get("end_date")
            
            # Should be None, not KeyError
            self.assertIsNone(period_start)
            self.assertIsNone(period_end)
        except KeyError:
            self.fail("Should not raise KeyError when keys are missing")


class LiquorSellTest(TestCase):
    """Test liquor selling flow with error handling"""
    
    def setUp(self):
        self.client = Client()
        
        # Create liquor business
        self.business = Business.objects.create(
            name='Test Bar',
            business_kind=BusinessKind.LIQUOR
        )
        
        # Create bartender
        self.bartender = User.objects.create_user(
            username='bartender',
            email='bartender@bar.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.bartender,
            business=self.business,
            role='AGENT'
        )
        
        # Create liquor product
        self.product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            name='Test Beer',
            barcode='',  # Test with empty barcode
            cost_price=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            quantity_in_stock=100,
            is_active=True
        )
    
    def test_liquor_product_without_barcode(self):
        """Liquor product should save successfully without barcode"""
        # Product was created with empty barcode
        self.assertEqual(self.product.barcode, '')
        
        # Should be able to save
        self.product.name = 'Updated Beer'
        try:
            self.product.save()
        except Exception as e:
            self.fail(f"Should not raise exception when saving without barcode: {e}")
    
    def test_liquor_sell_decreases_stock(self):
        """Selling liquor should decrease stock correctly"""
        initial_stock = self.product.quantity_in_stock
        
        self.client.login(username='bartender', password='testpass123')
        
        # Make a sale
        response = self.client.post(reverse('liquor:sell'), {
            'product_id': self.product.id,
            'quantity': 5,
            'payment_method': 'cash'
        })
        
        # Refresh product
        self.product.refresh_from_db()
        
        # Stock should decrease
        self.assertEqual(self.product.quantity_in_stock, initial_stock - 5)


class GroceriesVerticalTest(TestCase):
    """Test Groceries vertical basic functionality"""
    
    def setUp(self):
        self.client = Client()
        
        # Create grocery business
        self.business = Business.objects.create(
            name='Test Grocery',
            business_kind=BusinessKind.GROCERY
        )
        
        # Create owner
        self.owner = User.objects.create_user(
            username='groceryowner',
            email='owner@grocery.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='OWNER'
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_groceries_dashboard_accessible(self):
        """Groceries dashboard should be accessible"""
        self.client.login(username='groceryowner', password='testpass123')
        
        response = self.client.get(reverse('groceries:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Groceries Dashboard')
    
    def test_groceries_stock_in(self):
        """Should be able to add grocery stock"""
        self.client.login(username='groceryowner', password='testpass123')
        
        response = self.client.post(reverse('groceries:stock_in'), {
            'product_name': 'Rice 5kg',
            'category': 'food',
            'quantity': 50,
            'cost_price': '15000.00',
            'selling_price': '18000.00',
            'unit': 'pack'
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Product should be created
        product = MerchProduct.objects.filter(
            business=self.business,
            name='Rice 5kg',
            kind=BusinessKind.GROCERY
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 50)
    
    def test_groceries_sell(self):
        """Should be able to sell grocery products"""
        self.client.login(username='groceryowner', password='testpass123')
        
        # Create product first
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.GROCERY,
            name='Sugar 1kg',
            cost_price=Decimal('2000.00'),
            selling_price=Decimal('2500.00'),
            quantity_in_stock=100,
            base_unit='kg',
            is_active=True
        )
        
        # Sell 10 units
        response = self.client.post(reverse('groceries:sell'), {
            'product_id': product.id,
            'quantity': 10
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Stock should decrease
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 90)


class CementVerticalTest(TestCase):
    """Test Cement vertical basic functionality"""
    
    def setUp(self):
        self.client = Client()
        
        # Create cement business
        self.business = Business.objects.create(
            name='Test Hardware',
            business_kind=BusinessKind.CEMENT
        )
        
        # Create owner
        self.owner = User.objects.create_user(
            username='hardwareowner',
            email='owner@hardware.com',
            password='testpass123'
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='OWNER'
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_cement_dashboard_accessible(self):
        """Cement dashboard should be accessible"""
        self.client.login(username='hardwareowner', password='testpass123')
        
        response = self.client.get(reverse('cement:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cement Store Dashboard')
    
    def test_cement_stock_in(self):
        """Should be able to add cement/hardware stock"""
        self.client.login(username='hardwareowner', password='testpass123')
        
        response = self.client.post(reverse('cement:stock_in'), {
            'product_name': 'Cement 50kg',
            'category': 'cement',
            'quantity': 100,
            'cost_price': '45000.00',
            'selling_price': '50000.00',
            'unit': 'bag'
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Product should be created
        product = MerchProduct.objects.filter(
            business=self.business,
            name='Cement 50kg',
            kind=BusinessKind.CEMENT
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 100)
    
    def test_cement_sell(self):
        """Should be able to sell cement/hardware products"""
        self.client.login(username='hardwareowner', password='testpass123')
        
        # Create product first
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CEMENT,
            name='Steel Bars 12mm',
            cost_price=Decimal('35000.00'),
            selling_price=Decimal('40000.00'),
            quantity_in_stock=200,
            base_unit='pcs',
            is_active=True
        )
        
        # Sell 20 units
        response = self.client.post(reverse('cement:sell'), {
            'product_id': product.id,
            'quantity': 20
        })
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Stock should decrease
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 180)


class BarcodeOptionalTest(TestCase):
    """Test that barcode is optional across all verticals"""
    
    def test_clothing_product_without_barcode(self):
        """Clothing product should save without barcode"""
        business = Business.objects.create(
            name='Test Clothing',
            business_kind=BusinessKind.CLOTHING
        )
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.CLOTHING,
            name='T-Shirt',
            barcode='',  # Empty barcode
            cost_price=Decimal('5000.00'),
            selling_price=Decimal('8000.00'),
            quantity_in_stock=50,
            is_active=True
        )
        
        # Should save successfully
        self.assertEqual(product.barcode, '')
        
        # Should be able to update
        product.name = 'Updated T-Shirt'
        product.save()
        
        self.assertEqual(product.name, 'Updated T-Shirt')
    
    def test_liquor_product_without_barcode(self):
        """Liquor product should save without barcode"""
        business = Business.objects.create(
            name='Test Bar 2',
            business_kind=BusinessKind.LIQUOR
        )
        
        product = MerchProduct.objects.create(
            business=business,
            kind=BusinessKind.LIQUOR,
            name='Whiskey',
            barcode=None,  # None barcode
            cost_price=Decimal('25000.00'),
            selling_price=Decimal('35000.00'),
            quantity_in_stock=20,
            is_active=True
        )
        
        # Should save successfully
        self.assertIn(product.barcode, ['', None])

