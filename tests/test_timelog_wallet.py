# tests/test_timelog_wallet.py
"""
Tests for time-log wallet integration (bonuses and penalties).
"""
import pytest
from decimal import Decimal
from datetime import time, date
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location
from timelogs.models import AgentWorkLog, WorkingHours
from wallet.models import WalletTransaction, TxnType, Ledger
from timelogs.services_wallet import sync_timelog_to_wallet, calculate_timelog_bonuses_penalties
from sales.models import CommissionConfig

User = get_user_model()


@pytest.fixture
def business(db):
    return Business.objects.create(name="Test Biz", slug="test-biz", status="ACTIVE")


@pytest.fixture
def location(business):
    return Location.objects.create(name="Main", business=business, is_default=True)


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(username="agent1", password="pass123")


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
def working_hours(business, location):
    """Standard 8-5 working hours."""
    return WorkingHours.objects.create(
        business=business,
        location=location,
        scheduled_start=time(8, 0),
        scheduled_end=time(17, 0),
        is_active=True
    )


@pytest.fixture
def commission_config(business):
    """Commission config with bonus/penalty settings."""
    return CommissionConfig.objects.create(
        business=business,
        base_commission_pct=Decimal("10.00"),
        early_bonus_per_30min=Decimal("5000.00"),
        late_penalty_per_30min=Decimal("7000.00"),
        early_bonus_enabled=True,
        lateness_penalties_enabled=True,
        is_active=True
    )


@pytest.mark.django_db
class TestTimelogBonusCalculation:
    """Test bonus/penalty calculation from work logs."""
    
    def test_calculate_early_bonus(self, business, location, agent_user, working_hours, commission_config):
        """Agent arriving early should get bonus."""
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(timezone.localdate(), time(7, 0))  # 1 hour early
            )
        )
        
        # Calculate bonuses/penalties
        result = calculate_timelog_bonuses_penalties(work_log)
        
        # Refresh work log
        work_log.refresh_from_db()
        
        # Should have 2 blocks of 30 min = 10000 bonus
        assert work_log.bonus_amount == Decimal("10000.00")
        assert work_log.penalty_amount == Decimal("0.00")
        assert result["early_blocks"] == 2
    
    def test_calculate_late_penalty(self, business, location, agent_user, working_hours, commission_config):
        """Agent arriving late should get penalty."""
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(timezone.localdate(), time(9, 0))  # 1 hour late
            )
        )
        
        # Calculate bonuses/penalties
        result = calculate_timelog_bonuses_penalties(work_log)
        
        # Refresh work log
        work_log.refresh_from_db()
        
        # Should have 2 blocks of 30 min = 14000 penalty
        assert work_log.penalty_amount == Decimal("14000.00")
        assert work_log.bonus_amount == Decimal("0.00")
        assert result["late_blocks"] == 2
    
    def test_no_bonus_when_disabled(self, business, location, agent_user, working_hours):
        """No bonus when disabled in config."""
        config = CommissionConfig.objects.create(
            business=business,
            early_bonus_enabled=False,  # Disabled
            late_penalty_per_30min=Decimal("7000.00"),
            lateness_penalties_enabled=True,
            is_active=True
        )
        
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            scheduled_start=time(8, 0),
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(timezone.localdate(), time(7, 0))  # 1 hour early
            )
        )
        
        calculate_timelog_bonuses_penalties(work_log)
        work_log.refresh_from_db()
        
        # Should be 0 even though arrived early
        assert work_log.bonus_amount == Decimal("0.00")


@pytest.mark.django_db
class TestTimelogWalletSync:
    """Test syncing time logs to wallet."""
    
    def test_sync_creates_wallet_transactions(self, business, location, agent_user, agent_membership, commission_config):
        """Syncing should create wallet transactions for bonuses/penalties."""
        # Create a work log with bonus and penalty
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            bonus_amount=Decimal("10000.00"),
            penalty_amount=Decimal("5000.00"),
            wallet_processed=False
        )
        
        # Sync to wallet
        result = sync_timelog_to_wallet(work_log)
        
        # Should create 2 transactions
        assert result["already_processed"] == False
        assert len(result["transactions"]) == 2
        
        # Check bonus transaction
        bonus_txn = WalletTransaction.objects.filter(
            agent=agent_user,
            type=TxnType.BONUS,
            ledger=Ledger.AGENT
        ).first()
        
        assert bonus_txn is not None
        assert bonus_txn.amount == Decimal("10000.00")
        assert "Early arrival" in bonus_txn.note
        
        # Check penalty transaction
        penalty_txn = WalletTransaction.objects.filter(
            agent=agent_user,
            type=TxnType.PENALTY,
            ledger=Ledger.AGENT
        ).first()
        
        assert penalty_txn is not None
        assert penalty_txn.amount == Decimal("-5000.00")  # Negative for deduction
        assert "Lateness" in penalty_txn.note
        
        # Work log should be marked as processed
        work_log.refresh_from_db()
        assert work_log.wallet_processed == True
    
    def test_sync_idempotent(self, business, location, agent_user, commission_config):
        """Syncing same work log twice should not double-process."""
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            bonus_amount=Decimal("5000.00"),
            wallet_processed=False
        )
        
        # Sync first time
        result1 = sync_timelog_to_wallet(work_log)
        assert result1["already_processed"] == False
        assert len(result1["transactions"]) == 1
        
        # Sync second time
        result2 = sync_timelog_to_wallet(work_log)
        assert result2["already_processed"] == True
        assert len(result2["transactions"]) == 0
        
        # Should only have 1 transaction
        txns = WalletTransaction.objects.filter(
            agent=agent_user,
            type=TxnType.BONUS
        )
        assert txns.count() == 1
    
    def test_bulk_sync(self, business, location, agent_user, commission_config):
        """Can bulk sync multiple work logs."""
        from timelogs.services_wallet import bulk_sync_timelogs_to_wallet
        
        # Create multiple work logs
        today = timezone.localdate()
        for i in range(3):
            AgentWorkLog.objects.create(
                agent=agent_user,
                business=business,
                location=location,
                work_date=today,
                bonus_amount=Decimal("5000.00"),
                penalty_amount=Decimal("3000.00"),
                wallet_processed=False
            )
        
        # Bulk sync
        result = bulk_sync_timelogs_to_wallet(business, today, today)
        
        assert result["processed"] == 3
        assert result["total_bonus"] == Decimal("15000.00")
        assert result["total_penalty"] == Decimal("9000.00")
        
        # All should be processed
        assert AgentWorkLog.objects.filter(
            business=business,
            wallet_processed=True
        ).count() == 3


@pytest.mark.django_db
class TestAgentWalletBalance:
    """Test agent wallet balance with commissions, bonuses, and penalties."""
    
    def test_wallet_balance_includes_all_transactions(self, business, location, agent_user, agent_membership):
        """Wallet balance should reflect commissions, bonuses, penalties."""
        from wallet.agent_models import get_or_create_agent_wallet
        
        # Create various wallet transactions
        WalletTransaction.objects.create(
            agent=agent_user,
            ledger=Ledger.AGENT,
            type=TxnType.COMMISSION,
            amount=Decimal("50000.00"),
            effective_date=timezone.localdate(),
            business=business
        )
        
        WalletTransaction.objects.create(
            agent=agent_user,
            ledger=Ledger.AGENT,
            type=TxnType.BONUS,
            amount=Decimal("10000.00"),
            effective_date=timezone.localdate(),
            business=business
        )
        
        WalletTransaction.objects.create(
            agent=agent_user,
            ledger=Ledger.AGENT,
            type=TxnType.PENALTY,
            amount=Decimal("-5000.00"),
            effective_date=timezone.localdate(),
            business=business
        )
        
        # Get wallet
        wallet = get_or_create_agent_wallet(agent_membership)
        
        # Balance should be 50000 + 10000 - 5000 = 55000
        assert wallet.balance == Decimal("55000.00")

