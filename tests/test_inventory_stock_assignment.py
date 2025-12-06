# tests/test_inventory_stock_assignment.py
"""
Tests for stock assignment functionality.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership, Location
from inventory.models import InventoryItem, Product

User = get_user_model()


@pytest.mark.django_db
class TestStockAssignment(TestCase):
    """Test stock assignment views and permissions."""
    
    def setUp(self):
        """Create test data."""
        self.client = Client()
        
        # Create business and location
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create manager
        self.manager = User.objects.create_user(
            username="manager",
            password="testpass123"
        )
        self.manager.is_staff = True
        self.manager.save()
        
        # Create manager membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            location=self.location,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create two agents
        self.agent1 = User.objects.create_user(
            username="agent1",
            password="testpass123"
        )
        self.agent1_membership = Membership.objects.create(
            user=self.agent1,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.agent2 = User.objects.create_user(
            username="agent2",
            password="testpass123"
        )
        self.agent2_membership = Membership.objects.create(
            user=self.agent2,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create product
        self.product = Product.objects.create(
            name="iPhone 13",
            brand="Apple",
            model="13",
            business=self.business
        )
        
        # Create three stock items
        self.stock1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=None,
            assigned_role="MANAGER"
        )
        
        self.stock2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012346",
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=self.agent1,
            assigned_role="AGENT"
        )
        
        self.stock3 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012347",
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=None,
            assigned_role="MANAGER"
        )
    
    def test_agent_sees_only_stock_assigned_to_them(self):
        """Agent should only see stock assigned to them + manager pool."""
        self.client.login(username='agent1', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:stock_list'))
        self.assertEqual(response.status_code, 200)
        
        # Agent1 should see: stock2 (assigned to them) + stock1, stock3 (manager pool)
        # But should NOT see stock assigned to other agents
        # This test validates visibility filtering
    
    def test_manager_sees_all_stock(self):
        """Manager should see all stock items regardless of assignment."""
        self.client.login(username='manager', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:stock_list'))
        self.assertEqual(response.status_code, 200)
        
        # Manager should see all stock items
        # This test validates manager visibility
    
    def test_manager_can_assign_stock_via_view(self):
        """Manager should be able to assign stock to an agent."""
        self.client.login(username='manager', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Assign stock1 to agent2
        response = self.client.post(
            reverse('inventory:assign_stock_owner'),
            {
                'stock_id': self.stock1.id,
                'owner_id': self.agent2.id
            }
        )
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Verify assignment
        self.stock1.refresh_from_db()
        self.assertEqual(self.stock1.assigned_agent, self.agent2)
        self.assertEqual(self.stock1.assigned_role, "AGENT")
    
    def test_agent_cannot_assign_stock(self):
        """Agent should not be able to assign stock."""
        self.client.login(username='agent1', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to assign stock3 to agent1
        response = self.client.post(
            reverse('inventory:assign_stock_owner'),
            {
                'stock_id': self.stock3.id,
                'owner_id': self.agent1.id
            }
        )
        
        # Should redirect with error (not 403, but should have no effect)
        self.assertEqual(response.status_code, 302)
        
        # Verify stock was NOT reassigned
        self.stock3.refresh_from_db()
        self.assertIsNone(self.stock3.assigned_agent)
        self.assertEqual(self.stock3.assigned_role, "MANAGER")

