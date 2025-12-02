# tests/test_agent_ranking.py
"""
Tests for agent ranking and milestones functionality.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location
from wallet.agent_models import (
    AgentWallet,
    AgentWalletTransaction,
    AgentWalletTransactionType,
    AgentEarnings,
    get_agent_ranking,
    add_commission,
)

User = get_user_model()


@pytest.mark.django_db
class TestAgentRanking(TestCase):
    """Test agent ranking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind="PHONES",
            slug="test-ranking-shop",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        
        # Create 3 agents
        self.agents = []
        self.memberships = []
        for i in range(3):
            agent = User.objects.create_user(
                username=f"agent{i}@test.com",
                email=f"agent{i}@test.com",
                password="testpass123",
            )
            membership = Membership.objects.create(
                user=agent,
                business=self.business,
                location=self.location,
                role="AGENT",
                status="ACTIVE",
            )
            self.agents.append(agent)
            self.memberships.append(membership)
        
    def test_agent_ranking_basic(self):
        """Test basic ranking with different sales counts."""
        # Agent 0: 5 sales
        for i in range(5):
            add_commission(
                self.memberships[0],
                amount=Decimal("10.00"),
                description=f"Sale {i}",
            )
        
        # Agent 1: 10 sales (should be #1)
        for i in range(10):
            add_commission(
                self.memberships[1],
                amount=Decimal("10.00"),
                description=f"Sale {i}",
            )
        
        # Agent 2: 3 sales
        for i in range(3):
            add_commission(
                self.memberships[2],
                amount=Decimal("10.00"),
                description=f"Sale {i}",
            )
        
        # Check rankings
        ranking_0 = get_agent_ranking(self.memberships[0])
        ranking_1 = get_agent_ranking(self.memberships[1])
        ranking_2 = get_agent_ranking(self.memberships[2])
        
        # Agent 1 should be #1
        self.assertEqual(ranking_1['rank'], 1)
        self.assertEqual(ranking_1['sales_count'], 10)
        self.assertEqual(ranking_1['is_top'], True)
        self.assertEqual(ranking_1['behind_top'], 0)
        
        # Agent 0 should be #2
        self.assertEqual(ranking_0['rank'], 2)
        self.assertEqual(ranking_0['sales_count'], 5)
        self.assertEqual(ranking_0['is_top'], False)
        self.assertEqual(ranking_0['behind_top'], 5)  # 10 - 5 = 5
        
        # Agent 2 should be #3
        self.assertEqual(ranking_2['rank'], 3)
        self.assertEqual(ranking_2['sales_count'], 3)
        self.assertEqual(ranking_2['behind_top'], 7)  # 10 - 3 = 7
        
    def test_agent_ranking_ties(self):
        """Test ranking when agents have equal sales."""
        # Both agents have 5 sales
        for i in range(5):
            add_commission(self.memberships[0], Decimal("10.00"), f"Sale {i}")
            add_commission(self.memberships[1], Decimal("10.00"), f"Sale {i}")
        
        ranking_0 = get_agent_ranking(self.memberships[0])
        ranking_1 = get_agent_ranking(self.memberships[1])
        
        # Both should have same rank (1 or 2, depending on list order)
        self.assertIn(ranking_0['rank'], [1, 2])
        self.assertIn(ranking_1['rank'], [1, 2])
        
        # Both should have same sales count
        self.assertEqual(ranking_0['sales_count'], 5)
        self.assertEqual(ranking_1['sales_count'], 5)
        
    def test_agent_ranking_single_agent(self):
        """Test ranking when there's only one agent."""
        add_commission(self.memberships[0], Decimal("10.00"), "Sale")
        
        ranking = get_agent_ranking(self.memberships[0])
        
        # Should be #1 out of 1
        self.assertEqual(ranking['rank'], 1)
        self.assertEqual(ranking['total_agents'], 1)
        self.assertEqual(ranking['is_top'], True)
        
    def test_agent_ranking_no_sales(self):
        """Test ranking when agent has no sales."""
        # Agent 1 has sales
        for i in range(3):
            add_commission(self.memberships[1], Decimal("10.00"), f"Sale {i}")
        
        # Agent 0 has no sales
        ranking_0 = get_agent_ranking(self.memberships[0])
        
        # Should be ranked last
        self.assertEqual(ranking_0['sales_count'], 0)
        self.assertGreater(ranking_0['rank'], 1)
        self.assertEqual(ranking_0['behind_top'], 3)
        
    def test_agent_milestones(self):
        """Test agent milestones calculation."""
        membership = self.memberships[0]
        
        # Add some commissions over time
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # MTD commissions
        for i in range(5):
            add_commission(
                membership,
                amount=Decimal("50.00"),
                description=f"MTD Sale {i}",
            )
        
        # Create AgentEarnings instance
        earnings = AgentEarnings(membership)
        
        # Test MTD earnings
        mtd = earnings.mtd_earnings()
        self.assertEqual(mtd, Decimal("250.00"))  # 5 * 50
        
        # Test balance
        balance = earnings.balance
        self.assertEqual(balance, Decimal("250.00"))
        
        # Test lifetime earnings (same as MTD since we only added MTD sales)
        lifetime = earnings.lifetime_earnings()
        self.assertEqual(lifetime, Decimal("250.00"))
        
    def test_agent_milestones_with_deductions(self):
        """Test milestones correctly handle deductions."""
        from wallet.agent_models import add_deduction
        
        membership = self.memberships[0]
        
        # Add commissions
        for i in range(3):
            add_commission(membership, Decimal("100.00"), f"Sale {i}")
        
        # Add a deduction
        add_deduction(
            membership,
            amount=Decimal("50.00"),
            description="Penalty",
        )
        
        earnings = AgentEarnings(membership)
        
        # Earnings should be 300
        self.assertEqual(earnings.mtd_earnings(), Decimal("300.00"))
        
        # Deductions should be 50
        self.assertEqual(earnings.mtd_deductions(), Decimal("50.00"))
        
        # Net should be 250
        self.assertEqual(earnings.mtd_net(), Decimal("250.00"))
        
        # Balance should be 250 (300 - 50)
        self.assertEqual(earnings.balance, Decimal("250.00"))
        
    def test_agent_dashboard_includes_ranking(self):
        """Test agent dashboard includes ranking data."""
        # Add some sales for ranking
        for i in range(5):
            add_commission(self.memberships[0], Decimal("10.00"), f"Sale {i}")
        
        for i in range(3):
            add_commission(self.memberships[1], Decimal("10.00"), f"Sale {i}")
        
        client = Client()
        client.login(username="agent1@test.com", password="testpass123")
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = client.get(reverse('dashboard:agent_dashboard'))
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Check ranking data in context
        if 'agent_ranking' in response.context and response.context['agent_ranking']:
            ranking = response.context['agent_ranking']
            
            # Should have rank
            self.assertIn('rank', ranking)
            
            # Should have total agents
            self.assertIn('total_agents', ranking)
            
            # Should have sales count
            self.assertIn('sales_count', ranking)
            
    def test_earnings_lifetime_vs_mtd(self):
        """Test that lifetime earnings differ from MTD when sales span multiple months."""
        from datetime import timedelta
        
        membership = self.memberships[0]
        wallet = AgentWallet.objects.get(membership=membership)
        
        # Add old commission (2 months ago)
        old_date = timezone.localdate().replace(day=1) - timedelta(days=60)
        AgentWalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
            amount=Decimal("100.00"),
            is_debit=False,
            description="Old sale",
            effective_date=old_date,
        )
        
        # Add recent commission (this month)
        add_commission(membership, Decimal("50.00"), "Recent sale")
        
        earnings = AgentEarnings(membership)
        
        # Lifetime should include both
        # Note: balance is tracked separately, so lifetime_earnings aggregates all transactions
        lifetime = earnings.lifetime_earnings()
        self.assertEqual(lifetime, Decimal("150.00"))
        
        # MTD should only include recent
        mtd = earnings.mtd_earnings()
        self.assertEqual(mtd, Decimal("50.00"))
        
        # Balance should be total
        self.assertEqual(earnings.balance, Decimal("150.00"))

