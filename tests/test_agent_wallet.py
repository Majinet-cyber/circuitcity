# tests/test_agent_wallet.py
"""
Tests for agent wallet features: commissions, deductions, manual adjustments.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.contrib.auth import get_user_model

from wallet.agent_models import (
    AgentWallet,
    AgentWalletTransaction,
    get_or_create_agent_wallet,
    add_commission,
    add_deduction,
    add_manual_adjustment,
    AgentEarnings,
    get_agent_ranking,
)
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestAgentWallet:
    
    def test_create_agent_wallet(self, membership):
        """Test creating an agent wallet."""
        wallet = get_or_create_agent_wallet(membership)
        
        assert wallet.membership == membership
        assert wallet.balance == Decimal("0.00")
    
    def test_add_commission(self, membership):
        """Test adding a commission to agent wallet."""
        initial_balance = get_or_create_agent_wallet(membership).balance
        
        txn = add_commission(
            membership=membership,
            amount=Decimal("5000.00"),
            description="Sale commission",
        )
        
        wallet = AgentWallet.objects.get(membership=membership)
        assert wallet.balance == initial_balance + Decimal("5000.00")
        assert not txn.is_debit
    
    def test_add_deduction(self, membership):
        """Test adding a deduction to agent wallet."""
        # First add some balance
        add_commission(membership, Decimal("10000.00"))
        
        initial_balance = AgentWallet.objects.get(membership=membership).balance
        
        txn = add_deduction(
            membership=membership,
            amount=Decimal("2000.00"),
            description="Lateness penalty",
        )
        
        wallet = AgentWallet.objects.get(membership=membership)
        assert wallet.balance == initial_balance - Decimal("2000.00")
        assert txn.is_debit
    
    def test_deduction_insufficient_balance(self, membership):
        """Test that deduction fails with insufficient balance."""
        from django.core.exceptions import ValidationError
        
        # Wallet starts at 0
        with pytest.raises(ValidationError):
            add_deduction(
                membership=membership,
                amount=Decimal("5000.00"),
                description="Penalty",
            )
    
    def test_manual_adjustment_credit(self, membership, admin_user):
        """Test manual adjustment (credit)."""
        initial_balance = get_or_create_agent_wallet(membership).balance
        
        txn = add_manual_adjustment(
            membership=membership,
            amount=Decimal("3000.00"),
            is_debit=False,
            reason="Performance bonus",
            created_by=admin_user,
        )
        
        wallet = AgentWallet.objects.get(membership=membership)
        assert wallet.balance == initial_balance + Decimal("3000.00")
        assert txn.reason == "Performance bonus"
        assert txn.created_by == admin_user
    
    def test_manual_adjustment_debit(self, membership, admin_user):
        """Test manual adjustment (debit)."""
        # Add initial balance
        add_commission(membership, Decimal("10000.00"))
        
        initial_balance = AgentWallet.objects.get(membership=membership).balance
        
        txn = add_manual_adjustment(
            membership=membership,
            amount=Decimal("2000.00"),
            is_debit=True,
            reason="Equipment damage",
            created_by=admin_user,
        )
        
        wallet = AgentWallet.objects.get(membership=membership).balance
        assert wallet == initial_balance - Decimal("2000.00")
    
    def test_manual_adjustment_requires_reason(self, membership, admin_user):
        """Test that manual adjustment requires a reason."""
        from django.core.exceptions import ValidationError
        
        with pytest.raises(ValidationError):
            add_manual_adjustment(
                membership=membership,
                amount=Decimal("1000.00"),
                is_debit=False,
                reason="",  # Empty reason
                created_by=admin_user,
            )
    
    def test_agent_earnings_mtd(self, membership):
        """Test MTD earnings calculation."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Add commissions
        for i in range(3):
            add_commission(membership, Decimal("5000.00"), effective_date=today)
        
        earnings = AgentEarnings(membership)
        assert earnings.mtd_earnings() == Decimal("15000.00")
    
    def test_agent_earnings_with_deductions(self, membership):
        """Test earnings with deductions."""
        today = timezone.localdate()
        
        # Add commissions
        add_commission(membership, Decimal("10000.00"), effective_date=today)
        add_commission(membership, Decimal("8000.00"), effective_date=today)
        
        # Add deduction
        add_deduction(membership, Decimal("3000.00"), effective_date=today)
        
        earnings = AgentEarnings(membership)
        assert earnings.mtd_earnings() == Decimal("18000.00")
        assert earnings.mtd_deductions() == Decimal("3000.00")
        assert earnings.mtd_net() == Decimal("15000.00")
    
    def test_agent_ranking(self, membership, location):
        """Test agent ranking calculation."""
        # Create another agent
        other_agent = User.objects.create_user(
            username="other_agent",
            email="other@example.com",
        )
        other_membership = Membership.objects.create(
            user=other_agent,
            business=membership.business,
            location=location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Give main agent 5 sales (commissions)
        for i in range(5):
            add_commission(membership, Decimal("1000.00"))
        
        # Give other agent 8 sales
        for i in range(8):
            add_commission(other_membership, Decimal("1000.00"))
        
        # Check ranking
        ranking = get_agent_ranking(membership)
        
        assert ranking["rank"] == 2
        assert ranking["total_agents"] == 2
        assert ranking["sales_count"] == 5
        assert ranking["top_sales_count"] == 8
        assert ranking["behind_top"] == 3
        assert not ranking["is_top"]
    
    def test_agent_ranking_tied(self, membership, location):
        """Test agent ranking with tied sales."""
        # Create another agent with same sales count
        other_agent = User.objects.create_user(
            username="other_agent",
            email="other@example.com",
        )
        other_membership = Membership.objects.create(
            user=other_agent,
            business=membership.business,
            location=location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Give both agents 5 sales
        for i in range(5):
            add_commission(membership, Decimal("1000.00"))
            add_commission(other_membership, Decimal("1000.00"))
        
        ranking = get_agent_ranking(membership)
        
        assert ranking["rank"] in [1, 2]  # Could be either depending on order
        assert ranking["behind_top"] == 0


@pytest.fixture
def business():
    """Create a test business."""
    return Business.objects.create(
        name="Test Business",
        slug="test-biz",
        status="ACTIVE",
    )


@pytest.fixture
def location(business):
    """Create a test location."""
    from inventory.models import Location
    return Location.objects.create(
        business=business,
        name="Main Store",
    )


@pytest.fixture
def agent_user():
    """Create a test agent user."""
    return User.objects.create_user(
        username="agent1",
        email="agent1@example.com",
        password="testpass123",
    )


@pytest.fixture
def admin_user():
    """Create a test admin user."""
    return User.objects.create_user(
        username="admin",
        email="admin@example.com",
        password="adminpass123",
        is_staff=True,
    )


@pytest.fixture
def membership(agent_user, business, location):
    """Create a test membership."""
    return Membership.objects.create(
        user=agent_user,
        business=business,
        location=location,
        role="AGENT",
        status="ACTIVE",
    )

