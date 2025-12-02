# tests/test_wallet_costs.py
"""
Tests for admin wallet cost management features.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from wallet.models import WalletTransaction, Ledger, TxnType
from wallet.utils import compute_business_costs, compute_revenue_costs_profit
from tenants.models import Business


@pytest.mark.django_db
class TestWalletCosts:
    
    def test_create_once_off_cost(self, business):
        """Test creating a once-off cost transaction."""
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Office supplies",
            business=business,
            is_recurring=False,
        )
        
        assert cost.amount == Decimal("-50000.00")
        assert not cost.is_recurring
        assert cost.ledger == Ledger.COMPANY
    
    def test_create_recurring_cost(self, business):
        """Test creating a recurring cost transaction."""
        today = timezone.localdate()
        
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-200000.00"),
            note="Monthly rent",
            business=business,
            is_recurring=True,
            recurrence="monthly",
            effective_from=today.replace(day=1),
        )
        
        assert cost.amount == Decimal("-200000.00")
        assert cost.is_recurring
        assert cost.effective_from is not None
    
    def test_compute_business_costs_once_off_only(self, business):
        """Test computing costs with only once-off costs."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create once-off cost
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Office supplies",
            business=business,
            effective_date=today,
        )
        
        result = compute_business_costs(business, month_start, today)
        
        assert result["once_off_total"] == Decimal("50000.00")
        assert result["recurring_total"] == Decimal("0.00")
        assert result["total"] == Decimal("50000.00")
    
    def test_compute_business_costs_with_recurring(self, business):
        """Test computing costs including recurring costs."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create recurring cost
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-200000.00"),
            note="Monthly rent",
            business=business,
            is_recurring=True,
            recurrence="monthly",
            effective_from=month_start,
        )
        
        result = compute_business_costs(business, month_start, today)
        
        assert result["recurring_total"] == Decimal("200000.00")
    
    def test_profit_calculation(self, business):
        """Test Revenue - Costs = Profit calculation."""
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create costs
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            business=business,
            effective_date=today,
        )
        
        revenue = Decimal("1000000.00")
        
        result = compute_revenue_costs_profit(business, revenue, month_start, today)
        
        assert result["revenue"] == Decimal("1000000.00")
        assert result["costs"] == Decimal("50000.00")
        assert result["profit"] == Decimal("950000.00")
        assert result["profit_margin"] == Decimal("95.00")
    
    def test_negative_amount_rejected(self, business):
        """Test that forms reject negative cost amounts."""
        # This would be tested with AdminCostForm
        from wallet.forms import AdminCostForm
        
        form = AdminCostForm(data={
            'amount': Decimal("-100.00"),
            'note': 'Test',
            'effective_date': timezone.localdate(),
            'type': TxnType.COST_ONCE_OFF,
        }, business=business)
        
        assert not form.is_valid()
        assert 'amount' in form.errors
    
    def test_costs_scoped_by_business(self, business):
        """Test that costs are scoped to business."""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Create another business
        other_business = Business.objects.create(
            name="Other Business",
            slug="other-biz",
            status="ACTIVE",
        )
        
        today = timezone.localdate()
        month_start = today.replace(day=1)
        
        # Create cost for main business
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            business=business,
            effective_date=today,
        )
        
        # Create cost for other business
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-30000.00"),
            business=other_business,
            effective_date=today,
        )
        
        # Compute costs for main business only
        result = compute_business_costs(business, month_start, today)
        assert result["total"] == Decimal("50000.00")
        
        # Compute costs for other business
        result_other = compute_business_costs(other_business, month_start, today)
        assert result_other["total"] == Decimal("30000.00")


@pytest.fixture
def business():
    """Create a test business."""
    return Business.objects.create(
        name="Test Business",
        slug="test-biz",
        status="ACTIVE",
    )

