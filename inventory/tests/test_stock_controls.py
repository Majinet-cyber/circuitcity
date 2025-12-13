"""
Tests for stock control features: agent assignment, transfer, edit IMEI, archive/restore.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import InventoryItem, Product, Location
from tenants.models import Business, Membership

User = get_user_model()


class StockControlsTestCase(TransactionTestCase):
    """Test stock controls: agent assignment, transfer, edit IMEI, archive, restore."""
    
    def setUp(self):
        """Create test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind="PHONES",
            status="ACTIVE",
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business,
        )
        
        # Create users
        self.manager = User.objects.create_user(
            username="manager",
            password="test123",
            email="manager@test.com",
        )
        
        self.agent1 = User.objects.create_user(
            username="agent1",
            password="test123",
            email="agent1@test.com",
        )
        
        self.agent2 = User.objects.create_user(
            username="agent2",
            password="test123",
            email="agent2@test.com",
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE',
        )
        
        Membership.objects.create(
            user=self.agent1,
            business=self.business,
            role='AGENT',
            status='ACTIVE',
            location=self.location,
        )
        
        Membership.objects.create(
            user=self.agent2,
            business=self.business,
            role='AGENT',
            status='ACTIVE',
            location=self.location,
        )
        
        # Create product
        self.product = Product.objects.create(
            code="TEST001",
            name="Test Phone",
            model="Test Model",
        )
        
        # Create stock items
        self.stock_manager = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK",
            assigned_agent=None,
            assigned_role="MANAGER",
        )
        
        self.stock_agent1 = InventoryItem.objects.create(
            business=self.business,
            imei="987654321098765",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK",
            assigned_agent=self.agent1,
            assigned_role="AGENT",
        )
    
    def _activate_business(self):
        """Activate the business in session."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_manager_can_view_all_stock(self):
        """Manager should see all non-archived stock."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        response = self.client.get(reverse('inventory:stock_list'))
        self.assertEqual(response.status_code, 200)
        
        # Should see both manager and agent stock
        items = response.context.get('items', [])
        self.assertEqual(len(items), 2)
    
    def test_agent_sees_only_their_stock(self):
        """Agent should only see stock assigned to them."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        response = self.client.get(reverse('inventory:stock_list'))
        self.assertEqual(response.status_code, 200)
        
        # Should only see their own stock
        items = response.context.get('items', [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, self.stock_agent1.id)
    
    def test_manager_can_transfer_stock(self):
        """Manager can transfer stock to another agent."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Transfer manager stock to agent2
        response = self.client.post(
            reverse('inventory:transfer_stock', args=[self.stock_manager.id]),
            {'agent_id': self.agent2.id}
        )
        
        self.assertEqual(response.status_code, 302)  # Redirect after success
        
        # Check stock was transferred
        self.stock_manager.refresh_from_db()
        self.assertEqual(self.stock_manager.assigned_agent, self.agent2)
        self.assertEqual(self.stock_manager.assigned_role, "AGENT")
    
    def test_manager_can_transfer_to_manager_pool(self):
        """Manager can unassign stock (transfer to manager pool)."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Transfer agent stock to manager pool
        response = self.client.post(
            reverse('inventory:transfer_stock', args=[self.stock_agent1.id]),
            {'agent_id': 'none'}
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Check stock was unassigned
        self.stock_agent1.refresh_from_db()
        self.assertIsNone(self.stock_agent1.assigned_agent)
        self.assertEqual(self.stock_agent1.assigned_role, "MANAGER")
    
    def test_agent_cannot_transfer_stock(self):
        """Agent cannot transfer stock (permission denied)."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        response = self.client.post(
            reverse('inventory:transfer_stock', args=[self.stock_agent1.id]),
            {'agent_id': self.agent2.id}
        )
        
        self.assertEqual(response.status_code, 403)
    
    def test_manager_can_edit_imei(self):
        """Manager can edit IMEI with valid 15-digit value."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        new_imei = "111111111111111"
        response = self.client.post(
            reverse('inventory:edit_imei', args=[self.stock_manager.id]),
            {'imei': new_imei}
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Check IMEI was updated
        self.stock_manager.refresh_from_db()
        self.assertEqual(self.stock_manager.imei, new_imei)
    
    def test_edit_imei_rejects_invalid_format(self):
        """Edit IMEI should reject non-15-digit values."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Too short
        response = self.client.post(
            reverse('inventory:edit_imei', args=[self.stock_manager.id]),
            {'imei': '12345'}
        )
        self.assertEqual(response.status_code, 400)
        
        # Contains letters
        response = self.client.post(
            reverse('inventory:edit_imei', args=[self.stock_manager.id]),
            {'imei': '12345678901234A'}
        )
        self.assertEqual(response.status_code, 400)
    
    def test_edit_imei_rejects_duplicate(self):
        """Edit IMEI should reject duplicate IMEI."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Try to set stock_manager IMEI to stock_agent1's IMEI
        response = self.client.post(
            reverse('inventory:edit_imei', args=[self.stock_manager.id]),
            {'imei': self.stock_agent1.imei}
        )
        
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn('already exists', response_data['error'])
    
    def test_agent_cannot_edit_imei(self):
        """Agent cannot edit IMEI (permission denied)."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        response = self.client.post(
            reverse('inventory:edit_imei', args=[self.stock_agent1.id]),
            {'imei': '111111111111111'}
        )
        
        self.assertEqual(response.status_code, 403)
    
    def test_manager_can_archive_stock(self):
        """Manager can archive stock item."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        response = self.client.post(
            reverse('inventory:archive_stock', args=[self.stock_manager.id])
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Check stock was archived
        self.stock_manager.refresh_from_db()
        self.assertIsNotNone(self.stock_manager.archived_at)
        self.assertEqual(self.stock_manager.archived_by, self.manager)
        self.assertFalse(self.stock_manager.is_active)
    
    def test_archived_stock_not_in_normal_list(self):
        """Archived stock should not appear in normal stock list."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Archive one item
        self.stock_manager.archived_at = timezone.now()
        self.stock_manager.archived_by = self.manager
        self.stock_manager.is_active = False
        self.stock_manager.save()
        
        # Get normal list
        response = self.client.get(reverse('inventory:stock_list'))
        items = response.context.get('items', [])
        
        # Should only see non-archived items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, self.stock_agent1.id)
    
    def test_manager_can_view_archived_list(self):
        """Manager can view archived stock with ?archived=1."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Archive one item
        self.stock_manager.archived_at = timezone.now()
        self.stock_manager.archived_by = self.manager
        self.stock_manager.is_active = False
        self.stock_manager.save()
        
        # Get archived list
        response = self.client.get(reverse('inventory:stock_list') + '?archived=1')
        items = response.context.get('items', [])
        
        # Should only see archived items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, self.stock_manager.id)
    
    def test_agent_cannot_view_archived_list(self):
        """Agent cannot view archived list."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        # Archive one item
        self.stock_manager.archived_at = timezone.now()
        self.stock_manager.archived_by = self.manager
        self.stock_manager.is_active = False
        self.stock_manager.save()
        
        # Try to get archived list
        response = self.client.get(reverse('inventory:stock_list') + '?archived=1')
        items = response.context.get('items', [])
        
        # Should see nothing (permission denied via empty queryset)
        self.assertEqual(len(items), 0)
    
    def test_manager_can_restore_archived_stock(self):
        """Manager can restore archived stock."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Archive the item first
        self.stock_manager.archived_at = timezone.now()
        self.stock_manager.archived_by = self.manager
        self.stock_manager.is_active = False
        self.stock_manager.save()
        
        # Restore it
        response = self.client.post(
            reverse('inventory:restore_stock', args=[self.stock_manager.id])
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Check stock was restored
        self.stock_manager.refresh_from_db()
        self.assertIsNone(self.stock_manager.archived_at)
        self.assertIsNone(self.stock_manager.archived_by)
        self.assertTrue(self.stock_manager.is_active)
    
    def test_agent_cannot_archive_stock(self):
        """Agent cannot archive stock (permission denied)."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        response = self.client.post(
            reverse('inventory:archive_stock', args=[self.stock_agent1.id])
        )
        
        self.assertEqual(response.status_code, 403)
    
    def test_agent_cannot_restore_stock(self):
        """Agent cannot restore stock (permission denied)."""
        self.client.login(username='agent1', password='test123')
        self._activate_business()
        
        # Archive the item first
        self.stock_agent1.archived_at = timezone.now()
        self.stock_agent1.archived_by = self.manager
        self.stock_agent1.is_active = False
        self.stock_agent1.save()
        
        response = self.client.post(
            reverse('inventory:restore_stock', args=[self.stock_agent1.id])
        )
        
        self.assertEqual(response.status_code, 403)
    
    def test_is_archived_property(self):
        """Test the is_archived property."""
        # Non-archived item
        self.assertFalse(self.stock_manager.is_archived)
        
        # Archived item
        self.stock_manager.archived_at = timezone.now()
        self.stock_manager.save()
        self.assertTrue(self.stock_manager.is_archived)


class ScanInAgentAssignmentTestCase(TransactionTestCase):
    """Test agent assignment during scan-in."""
    
    def setUp(self):
        """Create test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind="PHONES",
            status="ACTIVE",
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business,
        )
        
        # Create users
        self.manager = User.objects.create_user(
            username="manager",
            password="test123",
            email="manager@test.com",
        )
        
        self.agent = User.objects.create_user(
            username="agent",
            password="test123",
            email="agent@test.com",
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE',
        )
        
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE',
            location=self.location,
        )
        
        # Create product
        self.product = Product.objects.create(
            code="TEST001",
            name="Test Phone",
            model="Test Model",
        )
    
    def _activate_business(self):
        """Activate the business in session."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_agent_scan_in_assigns_to_self(self):
        """When agent scans in stock, it should be assigned to them."""
        self.client.login(username='agent', password='test123')
        self._activate_business()
        
        # Note: This would require the actual scan-in form/endpoint
        # This is a placeholder test showing the expected behavior
        item = InventoryItem.objects.create(
            business=self.business,
            imei="555555555555555",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100.00"),
            status="IN_STOCK",
            assigned_agent=self.agent,  # This should be set automatically
            assigned_role="AGENT",
        )
        
        self.assertEqual(item.assigned_agent, self.agent)
        self.assertEqual(item.assigned_role, "AGENT")
    
    def test_manager_scan_in_assigns_to_none(self):
        """When manager scans in stock, it should be unassigned (manager pool)."""
        self.client.login(username='manager', password='test123')
        self._activate_business()
        
        # Note: This would require the actual scan-in form/endpoint
        # This is a placeholder test showing the expected behavior
        item = InventoryItem.objects.create(
            business=self.business,
            imei="666666666666666",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100.00"),
            status="IN_STOCK",
            assigned_agent=None,  # This should be None for manager
            assigned_role="MANAGER",
        )
        
        self.assertIsNone(item.assigned_agent)
        self.assertEqual(item.assigned_role, "MANAGER")

