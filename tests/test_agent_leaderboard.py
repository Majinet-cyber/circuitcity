# tests/test_agent_leaderboard.py
"""
Tests for agent leaderboard functionality.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership, Location
from inventory.models import Product
from sales.models import Sale
from wallet.models import WalletTransaction, Ledger
from tenants.services.leaderboard import get_agent_leaderboard, get_current_agent_rank

User = get_user_model()


@pytest.mark.django_db
class TestAgentLeaderboard(TestCase):
    """Test agent leaderboard service."""
    
    def setUp(self):
        """Create test data."""
        # Create business and location
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create product
        self.product = Product.objects.create(
            name="iPhone 13",
            brand="Apple",
            model="13",
            business=self.business
        )
        
        # Create three agents
        self.agent1 = User.objects.create_user(
            username="agent1",
            first_name="Alice",
            last_name="Smith",
            password="testpass123"
        )
        Membership.objects.create(
            user=self.agent1,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.agent2 = User.objects.create_user(
            username="agent2",
            first_name="Bob",
            last_name="Jones",
            password="testpass123"
        )
        Membership.objects.create(
            user=self.agent2,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.agent3 = User.objects.create_user(
            username="agent3",
            first_name="Charlie",
            last_name="Brown",
            password="testpass123"
        )
        Membership.objects.create(
            user=self.agent3,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create sales for agents (agent1 has most sales)
        today = timezone.localdate()
        start_of_month = today.replace(day=1)
        
        # Agent1: 5 sales
        for i in range(5):
            sale = Sale.objects.create(
                agent=self.agent1,
                location=self.location,
                sold_at=today,
                price=Decimal('100000')
            )
            # Create commission transaction
            WalletTransaction.objects.create(
                ledger=Ledger.AGENT,
                agent=self.agent1,
                type='commission',
                amount=Decimal('10000'),  # 10% commission
                business=self.business,
                effective_date=today
            )
        
        # Agent2: 3 sales
        for i in range(3):
            sale = Sale.objects.create(
                agent=self.agent2,
                location=self.location,
                sold_at=today,
                price=Decimal('100000')
            )
            # Create commission transaction
            WalletTransaction.objects.create(
                ledger=Ledger.AGENT,
                agent=self.agent2,
                type='commission',
                amount=Decimal('10000'),
                business=self.business,
                effective_date=today
            )
        
        # Agent3: 1 sale
        sale = Sale.objects.create(
            agent=self.agent3,
            location=self.location,
            sold_at=today,
            price=Decimal('100000')
        )
        WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=self.agent3,
            type='commission',
            amount=Decimal('10000'),
            business=self.business,
            effective_date=today
        )
        
        self.start_date = start_of_month
        self.end_date = today
    
    def test_leaderboard_orders_by_devices_sold_then_amount(self):
        """Leaderboard should order agents by devices sold, then by amount."""
        leaderboard = get_agent_leaderboard(
            business=self.business,
            start=self.start_date,
            end=self.end_date,
            limit=10
        )
        
        # Should return 3 agents
        self.assertEqual(len(leaderboard), 3)
        
        # Order should be: agent1 (5), agent2 (3), agent3 (1)
        self.assertEqual(leaderboard[0]['user_id'], self.agent1.id)
        self.assertEqual(leaderboard[0]['devices_sold'], 5)
        self.assertEqual(leaderboard[0]['rank'], 1)
        
        self.assertEqual(leaderboard[1]['user_id'], self.agent2.id)
        self.assertEqual(leaderboard[1]['devices_sold'], 3)
        self.assertEqual(leaderboard[1]['rank'], 2)
        
        self.assertEqual(leaderboard[2]['user_id'], self.agent3.id)
        self.assertEqual(leaderboard[2]['devices_sold'], 1)
        self.assertEqual(leaderboard[2]['rank'], 3)
    
    def test_leaderboard_scoped_to_business(self):
        """Leaderboard should only include agents from the specified business."""
        # Create another business with an agent
        other_business = Business.objects.create(
            name="Other Business",
            slug="other-business"
        )
        other_location = Location.objects.create(
            business=other_business,
            name="Other Store"
        )
        other_agent = User.objects.create_user(
            username="other_agent",
            password="testpass123"
        )
        Membership.objects.create(
            user=other_agent,
            business=other_business,
            location=other_location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create sale for other agent
        Sale.objects.create(
            agent=other_agent,
            location=other_location,
            sold_at=self.end_date,
            price=Decimal('1000000')  # Higher than our agents
        )
        
        # Get leaderboard for our business
        leaderboard = get_agent_leaderboard(
            business=self.business,
            start=self.start_date,
            end=self.end_date,
            limit=10
        )
        
        # Should only include our 3 agents, not the other agent
        self.assertEqual(len(leaderboard), 3)
        agent_ids = [a['user_id'] for a in leaderboard]
        self.assertNotIn(other_agent.id, agent_ids)
    
    def test_current_agent_rank_calculated_correctly(self):
        """get_current_agent_rank should return correct rank and gap."""
        # Get rank for agent2 (should be #2)
        rank_data = get_current_agent_rank(
            business=self.business,
            user=self.agent2,
            start=self.start_date,
            end=self.end_date
        )
        
        self.assertEqual(rank_data['rank'], 2)
        self.assertIsNotNone(rank_data['gap'])
        # Gap should be 2 sales (5 - 3)
        self.assertEqual(rank_data['gap'], 2)
        self.assertIn("2 sale", rank_data['gap_formatted'])
    
    def test_current_agent_rank_for_leader(self):
        """Agent #1 should have no gap."""
        rank_data = get_current_agent_rank(
            business=self.business,
            user=self.agent1,
            start=self.start_date,
            end=self.end_date
        )
        
        self.assertEqual(rank_data['rank'], 1)
        self.assertIsNone(rank_data['gap'])
        self.assertIsNone(rank_data['gap_formatted'])
    
    def test_current_agent_rank_for_agent_with_no_sales(self):
        """Agent with no sales should have no rank."""
        # Create agent with no sales
        agent_no_sales = User.objects.create_user(
            username="agent_no_sales",
            password="testpass123"
        )
        Membership.objects.create(
            user=agent_no_sales,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        rank_data = get_current_agent_rank(
            business=self.business,
            user=agent_no_sales,
            start=self.start_date,
            end=self.end_date
        )
        
        self.assertIsNone(rank_data['rank'])
        self.assertIsNone(rank_data['gap'])

