# tests/test_commission_wallet.py
"""
Tests for commission wallet integration.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Product, InventoryItem, Location
from sales.models import Sale, CommissionConfig
from wallet.models import WalletTransaction, TxnType, Ledger
from tenants.utils_commission import get_phone_commission_pct, update_commission_percentage

User = get_user_model()


@pytest.fixture
def business(db):
    return Business.objects.create(name="Test Corp", slug="test-corp", status="ACTIVE")


@pytest.fixture
def location(business):
    return Location.objects.create(name="Main Store", business=business, is_default=True)


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(username="agent1", email="agent1@test.com", password="pass123")


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(username="manager1", email="mgr@test.com", password="pass123", is_staff=True)


@pytest.fixture
def agent_membership(business, location, agent_user):
    return Membership.objects.create(
        user=agent_user,
        business=business,
        location=location,
        role="AGENT",
        status="ACTIVE"
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        code="IP13PRO",
        name="iPhone 13 Pro",
        brand="Apple",
        model="iPhone 13 Pro",
        cost_price=Decimal("500000.00"),
        sale_price=Decimal("750000.00")
    )


@pytest.fixture
def inventory_item(business, product, location):
    return InventoryItem.objects.create(
        business=business,
        product=product,
        imei="123456789012345",
        current_location=location,
        status="IN_STOCK",
        order_price=Decimal("500000.00"),
        selling_price=Decimal("750000.00")
    )


@pytest.mark.django_db
class TestCommissionConfig:
    """Test commission configuration helpers."""
    
    def test_default_commission_is_10_percent(self, business):
        """Default commission should be 10%."""
        pct = get_phone_commission_pct(business)
        assert pct == Decimal("0.10")
    
    def test_get_commission_creates_config(self, business):
        """Getting commission should create config if missing."""
        assert not CommissionConfig.objects.filter(business=business).exists()
        
        pct = get_phone_commission_pct(business)
        
        assert CommissionConfig.objects.filter(business=business).exists()
        assert pct == Decimal("0.10")
    
    def test_update_commission_percentage(self, business):
        """Can update commission percentage."""
        success = update_commission_percentage(business, Decimal("15.00"))
        
        assert success
        pct = get_phone_commission_pct(business)
        assert pct == Decimal("0.15")
    
    def test_update_commission_validates_range(self, business):
        """Commission percentage must be 0-100."""
        with pytest.raises(ValueError):
            update_commission_percentage(business, Decimal("150.00"))
        
        with pytest.raises(ValueError):
            update_commission_percentage(business, Decimal("-10.00"))


@pytest.mark.django_db
class TestSaleCommissionWallet:
    """Test that sales create wallet commission transactions."""
    
    def test_sale_creates_commission_transaction(self, business, location, agent_membership, inventory_item):
        """Creating a sale should automatically create a commission wallet transaction."""
        agent = agent_membership.user
        
        # Create a sale
        sale = Sale.objects.create(
            item=inventory_item,
            agent=agent,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("750000.00"),
            commission_pct=Decimal("10.00")
        )
        
        # Check that wallet transaction was created
        txns = WalletTransaction.objects.filter(
            agent=agent,
            ledger=Ledger.AGENT,
            type=TxnType.COMMISSION
        )
        
        assert txns.exists()
        txn = txns.first()
        
        # Commission should be 10% of 750000 = 75000
        expected_commission = Decimal("75000.00")
        assert txn.amount == expected_commission
        assert txn.reference == f"SALE-{sale.id}"
        assert "Commission" in txn.note
    
    def test_commission_respects_business_config(self, business, location, agent_membership, inventory_item):
        """Commission should use business config percentage."""
        agent = agent_membership.user
        
        # Update business commission to 15%
        update_commission_percentage(business, Decimal("15.00"))
        
        # Create a sale
        sale = Sale.objects.create(
            item=inventory_item,
            agent=agent,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("1000000.00"),
            commission_pct=Decimal("15.00")
        )
        
        # Check commission amount
        txn = WalletTransaction.objects.filter(
            agent=agent,
            type=TxnType.COMMISSION
        ).first()
        
        # Commission should be 15% of 1000000 = 150000
        assert txn.amount == Decimal("150000.00")
    
    def test_multiple_sales_create_multiple_commissions(self, business, location, agent_membership, product):
        """Multiple sales should create multiple commission transactions."""
        agent = agent_membership.user
        
        # Create multiple inventory items and sales
        for i in range(3):
            item = InventoryItem.objects.create(
                business=business,
                product=product,
                imei=f"12345678901234{i}",
                current_location=location,
                status="IN_STOCK",
                selling_price=Decimal("500000.00")
            )
            
            Sale.objects.create(
                item=item,
                agent=agent,
                location=location,
                sold_at=timezone.localdate(),
                price=Decimal("500000.00"),
                commission_pct=Decimal("10.00")
            )
        
        # Should have 3 commission transactions
        txns = WalletTransaction.objects.filter(
            agent=agent,
            type=TxnType.COMMISSION
        )
        
        assert txns.count() == 3
        
        # Total commission should be 3 * 50000 = 150000
        total = sum(txn.amount for txn in txns)
        assert total == Decimal("150000.00")


@pytest.mark.django_db
class TestAgentWalletAdjustment:
    """Test manager wallet adjustment functionality."""
    
    def test_manager_can_credit_agent(self, business, agent_membership, manager_user):
        """Manager can add funds to agent wallet."""
        from wallet.agent_models import get_or_create_agent_wallet, add_manual_adjustment
        
        wallet = get_or_create_agent_wallet(agent_membership)
        initial_balance = wallet.balance
        
        # Manager credits agent
        txn = add_manual_adjustment(
            membership=agent_membership,
            amount=Decimal("100000.00"),
            is_debit=False,
            reason="Float for sales",
            created_by=manager_user
        )
        
        # Refresh wallet
        wallet = get_or_create_agent_wallet(agent_membership)
        
        assert wallet.balance == initial_balance + Decimal("100000.00")
        assert "Float for sales" in txn.description
    
    def test_manager_can_debit_agent(self, business, agent_membership, manager_user):
        """Manager can deduct funds from agent wallet."""
        from wallet.agent_models import get_or_create_agent_wallet, add_manual_adjustment, add_credit
        
        # First credit agent with some funds
        add_credit(agent_membership, Decimal("200000.00"), "Initial balance")
        
        wallet = get_or_create_agent_wallet(agent_membership)
        initial_balance = wallet.balance
        
        # Manager debits agent
        txn = add_manual_adjustment(
            membership=agent_membership,
            amount=Decimal("50000.00"),
            is_debit=True,
            reason="Penalty for damage",
            created_by=manager_user
        )
        
        # Refresh wallet
        wallet = get_or_create_agent_wallet(agent_membership)
        
        assert wallet.balance == initial_balance - Decimal("50000.00")
        assert "Penalty for damage" in txn.description


@pytest.mark.django_db
class TestCommissionSummary:
    """Test commission summary calculations."""
    
    def test_get_agent_commission_summary(self, business, location, agent_membership, product):
        """Can get commission summary for an agent."""
        from wallet.services_commission import get_agent_commission_summary
        
        agent = agent_membership.user
        
        # Create sales with commissions
        for i in range(5):
            item = InventoryItem.objects.create(
                business=business,
                product=product,
                imei=f"11111111111111{i}",
                current_location=location,
                status="IN_STOCK",
                selling_price=Decimal("400000.00")
            )
            
            Sale.objects.create(
                item=item,
                agent=agent,
                location=location,
                sold_at=timezone.localdate(),
                price=Decimal("400000.00"),
                commission_pct=Decimal("10.00")
            )
        
        # Get summary
        summary = get_agent_commission_summary(agent, business)
        
        # Should have 5 sales × 40000 commission = 200000
        assert summary["mtd_total"] == Decimal("200000.00")
        assert summary["mtd_count"] == 5
        assert summary["all_time_total"] == Decimal("200000.00")
        assert summary["all_time_count"] == 5

