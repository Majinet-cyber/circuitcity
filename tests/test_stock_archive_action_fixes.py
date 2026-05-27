"""
Test Stock List Archive Action (Fix C)
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location

User = get_user_model()


@pytest.mark.django_db
class TestStockArchiveActionVisibility(TestCase):
    """Test that Archive action is visible for managers only"""
    
    def setUp(self):
        """Create business, users, and stock items for testing"""
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business'
        )
        
        # Create location
        self.location = Location.objects.create(
            name='Test Location',
            business=self.business
        )
        
        # Create manager user
        self.manager_user = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='testpass123'
        )
        self.manager_membership = Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role='MANAGER'
        )
        
        # Create agent user (non-manager)
        self.agent_user = User.objects.create_user(
            username='agent',
            email='agent@test.com',
            password='testpass123'
        )
        self.agent_membership = Membership.objects.create(
            user=self.agent_user,
            business=self.business,
            role='AGENT'
        )
        
        # Create test stock item
        self.stock_item = InventoryItem.objects.create(
            business=self.business,
            current_location=self.location,
            product='Test Phone',
            imei='123456789012345',
            status='IN_STOCK',
            order_price=100,
            selling_price=150
        )
    
    def test_manager_sees_archive_action(self):
        """Test that manager can see Archive action in stock list"""
        self.client.login(username='manager', password='testpass123')
        
        # Get stock list page
        response = self.client.get('/inventory/stock-list/')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that Archive button is present in HTML
        # The button should have data-cy="stock-archive-btn" attribute
        self.assertContains(
            response, 
            'stock-archive-btn',
            msg_prefix="Manager should see Archive button in stock actions"
        )
        
        # Check that archive URL is present
        self.assertContains(
            response,
            f'/inventory/stock/{self.stock_item.pk}/archive/',
            msg_prefix="Archive URL should be present for manager"
        )
    
    def test_agent_cannot_see_archive_action(self):
        """Test that non-manager (agent) cannot see Archive action"""
        self.client.login(username='agent', password='testpass123')
        
        # Get stock list page
        response = self.client.get('/inventory/stock-list/')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that Archive button is NOT present
        # Non-managers should see "—" instead of actions dropdown
        if response.content:
            content = response.content.decode('utf-8')
            # Should not have the actions dropdown toggle button
            self.assertNotIn(
                'stock-actions-btn',
                content,
                msg="Agent should not see Actions dropdown"
            )
    
    def test_archive_action_functionality(self):
        """Test that Archive action actually archives the item"""
        self.client.login(username='manager', password='testpass123')
        
        # Perform archive action (POST to archive URL)
        response = self.client.post(
            f'/inventory/stock/{self.stock_item.pk}/archive/',
            follow=True
        )
        
        # Should redirect after archiving
        self.assertEqual(response.status_code, 200)
        
        # Refresh item from database
        self.stock_item.refresh_from_db()
        
        # Check that item is now archived
        # (Depending on implementation, this might be is_archived=True or archived_at!=None)
        self.assertTrue(
            hasattr(self.stock_item, 'is_archived') and self.stock_item.is_archived or
            hasattr(self.stock_item, 'archived_at') and self.stock_item.archived_at is not None,
            "Item should be marked as archived after archive action"
        )
    
    def test_restore_action_visible_for_archived_items(self):
        """Test that Restore action appears for archived items (instead of Archive)"""
        self.client.login(username='manager', password='testpass123')
        
        # First archive the item
        self.client.post(f'/inventory/stock/{self.stock_item.pk}/archive/')
        
        # Get stock list with archived items shown
        response = self.client.get('/inventory/stock-list/?archived=1')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that Restore button is present (not Archive)
        self.assertContains(
            response,
            'stock-restore-btn',
            msg_prefix="Restore button should be visible for archived items"
        )
        
        # Check that Archive button is NOT present
        content = response.content.decode('utf-8')
        self.assertNotIn(
            'stock-archive-btn',
            content,
            msg="Archive button should not be visible for already-archived items"
        )


@pytest.mark.django_db
class TestStockArchiveNoRegressions(TestCase):
    """Test that archive functionality doesn't break existing features"""
    
    def setUp(self):
        """Create test data"""
        self.client = Client()
        
        self.business = Business.objects.create(name='Test Biz', slug='test-biz')
        self.location = Location.objects.create(name='Loc', business=self.business)
        
        self.manager = User.objects.create_user(
            username='mgr',
            password='pass'
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER'
        )
    
    def test_other_stock_actions_still_work(self):
        """Test that Transfer and Edit IMEI actions still work after archive changes"""
        self.client.login(username='mgr', password='pass')
        
        item = InventoryItem.objects.create(
            business=self.business,
            current_location=self.location,
            product='Phone',
            imei='111111111111111',
            status='IN_STOCK'
        )
        
        response = self.client.get('/inventory/stock-list/')
        
        # Check that Transfer action is still present
        self.assertContains(response, 'stock-transfer-btn')
        
        # Check that Edit IMEI action is still present
        self.assertContains(response, 'stock-edit-imei-btn')

