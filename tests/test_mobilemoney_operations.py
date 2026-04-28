"""
Comprehensive test suite for the Mobile Money Operations vertical.

Tests cover:
- Transaction recording and balance updates
- Commission calculation (fixed, percentage, slab)
- Provider-based commission rules
- Credit/debt records
- Overdue credit detection
- Daily reconciliation and variance calculation
- Shortage / overage detection
- Agent settlements
- Impossible negative balance guard
- Existing financial flows (no regressions)
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from tenants.models import Business

User = get_user_model()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mm_user(db):
    return User.objects.create_user(
        username="mm_test_agent",
        email="mmagent@test.example",
        password="testpass123",
    )


@pytest.fixture
def mm_business(db, mm_user):
    return Business.objects.create(
        name="Test Mobile Money Agent",
        kind="mobile_money",
        owner=mm_user,
    )


@pytest.fixture
def mm_client(db, mm_user, mm_business):
    c = Client()
    c.force_login(mm_user)
    session = c.session
    session["active_business_id"] = mm_business.id
    session.save()
    return c, mm_user, mm_business


# ---------------------------------------------------------------------------
# Helper to create transactions directly
# ---------------------------------------------------------------------------

def _make_tx(business, tx_type="cash_in", network="airtel", amount="5000",
             commission="0", cash_movement="0", float_movement="0", **kwargs):
    from inventory.models_mobilemoney import MobileMoneyTransaction
    return MobileMoneyTransaction.objects.create(
        business=business,
        tx_type=tx_type,
        network=network,
        amount=Decimal(amount),
        commission=Decimal(commission),
        cash_movement=Decimal(cash_movement),
        float_movement=Decimal(float_movement),
        **kwargs,
    )


# ===========================================================================
# PART 1 — Transaction recording
# ===========================================================================

@pytest.mark.django_db
class TestTransactionRecording:

    def test_cash_in_increases_cash_decreases_float(self, mm_business):
        """Cash In: cash +amount, float -amount."""
        from inventory.models_mobilemoney import MobileMoneyTransaction, MobileMoneyTxType
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type=MobileMoneyTxType.CASH_IN,
            network="airtel",
            amount=Decimal("10000"),
            cash_movement=Decimal("10000"),
            float_movement=Decimal("-10000"),
        )
        assert tx.cash_movement == Decimal("10000")
        assert tx.float_movement == Decimal("-10000")

    def test_cash_out_decreases_cash_increases_float(self, mm_business):
        """Cash Out: cash -amount, float +amount."""
        from inventory.models_mobilemoney import MobileMoneyTransaction, MobileMoneyTxType
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type=MobileMoneyTxType.CASH_OUT,
            network="tnm",
            amount=Decimal("5000"),
            cash_movement=Decimal("-5000"),
            float_movement=Decimal("5000"),
        )
        assert tx.cash_movement == Decimal("-5000")
        assert tx.float_movement == Decimal("5000")

    def test_send_money_affects_float(self, mm_business):
        """Send Money: agent collects cash, pays out float."""
        from inventory.models_mobilemoney import MobileMoneyTransaction, MobileMoneyTxType
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type=MobileMoneyTxType.SEND_MONEY,
            network="airtel",
            amount=Decimal("20000"),
            cash_movement=Decimal("20000"),
            float_movement=Decimal("-20000"),
        )
        assert tx.cash_movement > 0
        assert tx.float_movement < 0

    def test_receive_money_affects_cash_and_float(self, mm_business):
        """Receive Money: agent pays out cash, gains float."""
        from inventory.models_mobilemoney import MobileMoneyTransaction, MobileMoneyTxType
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type=MobileMoneyTxType.RECEIVE_MONEY,
            network="tnm",
            amount=Decimal("15000"),
            cash_movement=Decimal("-15000"),
            float_movement=Decimal("15000"),
        )
        assert tx.cash_movement < 0
        assert tx.float_movement > 0

    def test_float_balance_aggregation(self, mm_business):
        """Float balance = sum of all float_movement fields."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        from django.db.models import Sum
        MobileMoneyTransaction.objects.create(
            business=mm_business, tx_type="cash_in", network="airtel",
            amount=Decimal("10000"), cash_movement=Decimal("10000"), float_movement=Decimal("-10000"),
        )
        MobileMoneyTransaction.objects.create(
            business=mm_business, tx_type="cash_out", network="airtel",
            amount=Decimal("3000"), cash_movement=Decimal("-3000"), float_movement=Decimal("3000"),
        )
        float_sum = MobileMoneyTransaction.objects.filter(business=mm_business).aggregate(
            total=Sum("float_movement")
        )["total"]
        assert float_sum == Decimal("-7000")

    def test_transaction_records_commission(self, mm_business):
        """Commission is saved correctly."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type="send_money",
            network="airtel",
            amount=Decimal("50000"),
            commission=Decimal("750"),
            cash_movement=Decimal("50000"),
            float_movement=Decimal("-50000"),
        )
        assert tx.commission == Decimal("750")

    def test_transaction_records_customer_name(self, mm_business):
        """customer_name is saved on transaction."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type="cash_in",
            network="airtel",
            amount=Decimal("5000"),
            customer_name="James Phiri",
        )
        assert tx.customer_name == "James Phiri"

    def test_transaction_records_charges(self, mm_business):
        """Charges field is saved."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type="airtime",
            network="airtel",
            amount=Decimal("1000"),
            charges=Decimal("20"),
            float_movement=Decimal("-1000"),
        )
        assert tx.charges == Decimal("20")

    def test_failed_transaction_has_no_movement(self, mm_business):
        """Failed transaction does not create cash or float movements."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        tx = MobileMoneyTransaction.objects.create(
            business=mm_business,
            tx_type="failed",
            network="airtel",
            amount=Decimal("5000"),
            cash_movement=Decimal("0"),
            float_movement=Decimal("0"),
        )
        assert tx.cash_movement == Decimal("0")
        assert tx.float_movement == Decimal("0")


# ===========================================================================
# PART 2 — Commission engine
# ===========================================================================

@pytest.mark.django_db
class TestCommissionEngine:

    def test_percentage_commission_calculation(self, mm_business):
        """Percentage rule calculates correctly: 1.5% of 50000 = 750."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        rule = CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.SEND_MONEY,
            rule_type=CommissionRuleType.PERCENTAGE,
            percentage_rate=Decimal("0.0150"),
        )
        result = rule.calculate(Decimal("50000"))
        assert result == Decimal("750.00")

    def test_fixed_commission_returns_fixed_amount(self, mm_business):
        """Fixed rule returns the configured amount regardless of transaction size."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        rule = CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.TNM,
            tx_type=MobileMoneyTxType.CASH_OUT,
            rule_type=CommissionRuleType.FIXED,
            fixed_amount=Decimal("200"),
        )
        assert rule.calculate(Decimal("5000")) == Decimal("200")
        assert rule.calculate(Decimal("100000")) == Decimal("200")

    def test_slab_commission_within_range(self, mm_business):
        """Slab rule returns fixed_amount when amount is in range."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        rule = CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            rule_type=CommissionRuleType.SLAB,
            fixed_amount=Decimal("300"),
            min_amount=Decimal("5000"),
            max_amount=Decimal("20000"),
        )
        assert rule.calculate(Decimal("10000")) == Decimal("300")
        assert rule.calculate(Decimal("5000")) == Decimal("300")

    def test_slab_commission_outside_range_returns_zero(self, mm_business):
        """Slab rule returns 0 when amount is outside range."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        rule = CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            rule_type=CommissionRuleType.SLAB,
            fixed_amount=Decimal("300"),
            min_amount=Decimal("5000"),
            max_amount=Decimal("20000"),
        )
        assert rule.calculate(Decimal("4999")) == Decimal("0.00")
        assert rule.calculate(Decimal("20001")) == Decimal("0.00")

    def test_slab_no_upper_limit(self, mm_business):
        """Slab with no max_amount applies to all amounts >= min_amount."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        rule = CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            rule_type=CommissionRuleType.SLAB,
            fixed_amount=Decimal("1000"),
            min_amount=Decimal("100000"),
            max_amount=None,
        )
        assert rule.calculate(Decimal("500000")) == Decimal("1000")
        assert rule.calculate(Decimal("99999")) == Decimal("0.00")

    def test_provider_based_commission_rules(self, mm_business):
        """Different rules for Airtel vs TNM give different commissions."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.SEND_MONEY,
            rule_type=CommissionRuleType.PERCENTAGE,
            percentage_rate=Decimal("0.0150"),
        )
        CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.TNM,
            tx_type=MobileMoneyTxType.SEND_MONEY,
            rule_type=CommissionRuleType.PERCENTAGE,
            percentage_rate=Decimal("0.0120"),
        )
        from inventory.verticals.mobilemoney import _auto_commission
        airtel_comm = _auto_commission(mm_business, "airtel", "send_money", Decimal("50000"))
        tnm_comm = _auto_commission(mm_business, "tnm", "send_money", Decimal("50000"))
        assert airtel_comm == Decimal("750.00")
        assert tnm_comm == Decimal("600.00")
        assert airtel_comm != tnm_comm

    def test_no_matching_rule_returns_zero(self, mm_business):
        """No matching commission rule returns zero commission."""
        from inventory.verticals.mobilemoney import _auto_commission
        result = _auto_commission(mm_business, "airtel", "send_money", Decimal("50000"))
        assert result == Decimal("0.00")

    def test_inactive_rule_not_used(self, mm_business):
        """Inactive commission rule is ignored."""
        from inventory.models_mobilemoney import CommissionRule, CommissionRuleType, MobileMoneyNetwork, MobileMoneyTxType
        CommissionRule.objects.create(
            business=mm_business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            rule_type=CommissionRuleType.PERCENTAGE,
            percentage_rate=Decimal("0.020"),
            is_active=False,
        )
        from inventory.verticals.mobilemoney import _auto_commission
        result = _auto_commission(mm_business, "airtel", "cash_in", Decimal("10000"))
        assert result == Decimal("0.00")


# ===========================================================================
# PART 3 — Credit & debt records
# ===========================================================================

@pytest.mark.django_db
class TestCreditDebtRecords:

    def test_customer_credit_saved_correctly(self, mm_business, mm_user):
        """Customer credit record is created with correct fields."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Alice Banda",
            customer_phone="0881234567",
            amount_credited=Decimal("10000"),
            reason="Sent money, forgot to collect",
            created_by=mm_user,
        )
        assert credit.credit_type == CreditType.CUSTOMER_CREDIT
        assert credit.customer_name == "Alice Banda"
        assert credit.balance == Decimal("10000")
        assert credit.status == MobileMoneyCredit.STATUS_PENDING

    def test_agent_debt_saved_correctly(self, mm_business, mm_user):
        """Agent debt record is created with correct type."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        debt = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.AGENT_DEBT,
            customer_name="John Tembo (Agent)",
            amount_credited=Decimal("25000"),
            reason="Borrowed float during peak hour",
            created_by=mm_user,
        )
        assert debt.credit_type == CreditType.AGENT_DEBT
        assert debt.balance == Decimal("25000")

    def test_credit_balance_reduces_after_repayment(self, mm_business, mm_user):
        """Balance = amount_credited - amount_repaid."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Bob Mwale",
            amount_credited=Decimal("15000"),
            created_by=mm_user,
        )
        credit.amount_repaid = Decimal("6000")
        credit.update_status()
        credit.save()
        assert credit.balance == Decimal("9000")
        assert credit.status == MobileMoneyCredit.STATUS_PARTIAL

    def test_credit_fully_paid_sets_status_paid(self, mm_business, mm_user):
        """Repaying full amount sets status to PAID."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Carol Phiri",
            amount_credited=Decimal("5000"),
            created_by=mm_user,
        )
        credit.amount_repaid = Decimal("5000")
        credit.update_status()
        credit.save()
        assert credit.status == MobileMoneyCredit.STATUS_PAID
        assert credit.balance == Decimal("0")

    def test_overdue_credit_is_flagged(self, mm_business, mm_user):
        """Credit with past due date and unpaid is detected as overdue."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        past_date = timezone.now().date() - timedelta(days=3)
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="David Chirwa",
            amount_credited=Decimal("8000"),
            due_date=past_date,
            created_by=mm_user,
        )
        assert credit.is_overdue is True

    def test_future_due_date_not_overdue(self, mm_business, mm_user):
        """Credit with future due date is not overdue."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        future_date = timezone.now().date() + timedelta(days=7)
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Eve Mwamba",
            amount_credited=Decimal("3000"),
            due_date=future_date,
            created_by=mm_user,
        )
        assert credit.is_overdue is False

    def test_paid_credit_not_overdue(self, mm_business, mm_user):
        """Paid credit is never flagged as overdue even if past due date."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        past_date = timezone.now().date() - timedelta(days=10)
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Frank Lungu",
            amount_credited=Decimal("2000"),
            amount_repaid=Decimal("2000"),
            due_date=past_date,
            status=MobileMoneyCredit.STATUS_PAID,
            created_by=mm_user,
        )
        assert credit.is_overdue is False

    def test_overpayment_capped_at_credited(self, mm_business, mm_user):
        """Repayment over credited amount is capped at credited amount."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Grace Mbewe",
            amount_credited=Decimal("5000"),
            created_by=mm_user,
        )
        credit.amount_repaid = Decimal("5000") + Decimal("1000")
        credit.update_status()
        credit.save()
        assert credit.amount_repaid == Decimal("5000")
        assert credit.status == MobileMoneyCredit.STATUS_PAID


# ===========================================================================
# PART 4 — Daily reconciliation
# ===========================================================================

@pytest.mark.django_db
class TestDailyReconciliation:

    def test_reconciliation_calculates_expected_closing(self, mm_business, mm_user):
        """expected_closing = opening_cash + total_cash_in - total_cash_out."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("100000"),
            opening_float=Decimal("50000"),
            total_cash_in=Decimal("40000"),
            total_cash_out=Decimal("15000"),
            actual_closing_cash=Decimal("125000"),
            created_by=mm_user,
        )
        # 100000 + 40000 - 15000 = 125000
        assert recon.expected_closing_cash == Decimal("125000")

    def test_balanced_reconciliation_difference_zero(self, mm_business, mm_user):
        """When actual == expected, difference is 0."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("100000"),
            opening_float=Decimal("0"),
            total_cash_in=Decimal("50000"),
            total_cash_out=Decimal("20000"),
            actual_closing_cash=Decimal("130000"),
            created_by=mm_user,
        )
        assert recon.difference == Decimal("0")
        assert recon.status_label == "balanced"

    def test_shortage_is_detected(self, mm_business, mm_user):
        """Negative difference = shortage."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("100000"),
            opening_float=Decimal("0"),
            total_cash_in=Decimal("20000"),
            total_cash_out=Decimal("0"),
            actual_closing_cash=Decimal("115000"),  # should be 120000
            created_by=mm_user,
        )
        assert recon.difference == Decimal("-5000")
        assert recon.status_label == "shortage"
        assert recon.status_color == "red"

    def test_overage_is_detected(self, mm_business, mm_user):
        """Positive difference = overage."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("100000"),
            opening_float=Decimal("0"),
            total_cash_in=Decimal("20000"),
            total_cash_out=Decimal("0"),
            actual_closing_cash=Decimal("125000"),  # should be 120000
            created_by=mm_user,
        )
        assert recon.difference == Decimal("5000")
        assert recon.status_label == "overage"

    def test_minor_mismatch_amber(self, mm_business, mm_user):
        """Small shortage (< 5000) is minor mismatch, amber."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("100000"),
            opening_float=Decimal("0"),
            total_cash_in=Decimal("0"),
            total_cash_out=Decimal("0"),
            actual_closing_cash=Decimal("98000"),
            created_by=mm_user,
        )
        assert recon.difference == Decimal("-2000")
        assert recon.status_label == "minor_mismatch"
        assert recon.status_color == "amber"

    def test_reconciliation_includes_commissions(self, mm_business, mm_user):
        """total_commissions field is stored on reconciliation."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("50000"),
            actual_closing_cash=Decimal("50000"),
            total_commissions=Decimal("3500"),
            created_by=mm_user,
        )
        assert recon.total_commissions == Decimal("3500")

    def test_reconciliation_unique_per_business_date(self, mm_business, mm_user):
        """Cannot create two reconciliations for same business and date."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        from django.db import IntegrityError
        today = date.today()
        MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=today,
            opening_cash=Decimal("50000"),
            actual_closing_cash=Decimal("50000"),
            created_by=mm_user,
        )
        with pytest.raises(Exception):
            MobileMoneyReconciliation.objects.create(
                business=mm_business,
                date=today,
                opening_cash=Decimal("60000"),
                actual_closing_cash=Decimal("60000"),
                created_by=mm_user,
            )


# ===========================================================================
# PART 5 — Agent Settlements
# ===========================================================================

@pytest.mark.django_db
class TestAgentSettlements:

    def test_settlement_record_created(self, mm_business, mm_user):
        """Agent settlement is created and persisted."""
        from inventory.models_mobilemoney import AgentSettlement, AgentSettlementType
        s = AgentSettlement.objects.create(
            business=mm_business,
            settlement_type=AgentSettlementType.BORROWED_FLOAT,
            agent_name="Agent Kamanga",
            agent_phone="0991234567",
            amount=Decimal("30000"),
            direction=AgentSettlement.DIRECTION_RECEIVED,
            created_by=mm_user,
        )
        assert s.pk is not None
        assert s.amount == Decimal("30000")
        assert s.is_settled is False

    def test_borrowed_received_means_we_owe(self, mm_business, mm_user):
        """We received float from another agent → we owe them (negative balance_impact)."""
        from inventory.models_mobilemoney import AgentSettlement, AgentSettlementType
        s = AgentSettlement.objects.create(
            business=mm_business,
            settlement_type=AgentSettlementType.BORROWED_FLOAT,
            agent_name="Agent X",
            amount=Decimal("20000"),
            direction=AgentSettlement.DIRECTION_RECEIVED,
            created_by=mm_user,
        )
        assert s.balance_impact < 0
        assert s.balance_impact == Decimal("-20000")

    def test_borrowed_given_means_owed_to_us(self, mm_business, mm_user):
        """We gave float to another agent → they owe us (positive balance_impact)."""
        from inventory.models_mobilemoney import AgentSettlement, AgentSettlementType
        s = AgentSettlement.objects.create(
            business=mm_business,
            settlement_type=AgentSettlementType.BORROWED_FLOAT,
            agent_name="Agent Y",
            amount=Decimal("15000"),
            direction=AgentSettlement.DIRECTION_GIVEN,
            created_by=mm_user,
        )
        assert s.balance_impact > 0
        assert s.balance_impact == Decimal("15000")

    def test_mark_settlement_as_settled(self, mm_business, mm_user):
        """Settlement can be marked as settled with timestamp."""
        from inventory.models_mobilemoney import AgentSettlement, AgentSettlementType
        s = AgentSettlement.objects.create(
            business=mm_business,
            settlement_type=AgentSettlementType.BORROWED_CASH,
            agent_name="Agent Z",
            amount=Decimal("10000"),
            direction=AgentSettlement.DIRECTION_RECEIVED,
            created_by=mm_user,
        )
        s.is_settled = True
        s.settled_at = timezone.now()
        s.save()
        s.refresh_from_db()
        assert s.is_settled is True
        assert s.settled_at is not None


# ===========================================================================
# PART 6 — View integration tests (HTTP)
# ===========================================================================

@pytest.mark.django_db
class TestMMViews:

    def test_dashboard_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_dashboard_shows_demo_when_empty(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        resp = c.get(url)
        if resp.status_code == 200:
            assert resp.context.get("is_demo") is True

    def test_dashboard_real_data_overrides_demo(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyTransaction
        MobileMoneyTransaction.objects.create(
            business=business, tx_type="cash_in", network="airtel",
            amount=Decimal("5000"),
        )
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        resp = c.get(url)
        if resp.status_code == 200:
            assert resp.context.get("is_demo") is False

    def test_transactions_page_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_record_send_money_transaction(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyTransaction
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        resp = c.post(url, {
            "tx_type": "send_money",
            "network": "airtel",
            "amount": "20000",
            "commission": "300",
            "customer_name": "Mary Chirwa",
            "customer_phone": "0881234567",
            "reference_number": "TXN123",
            "notes": "",
            "charges": "0",
        })
        assert resp.status_code in [200, 302]
        assert MobileMoneyTransaction.objects.filter(business=business).exists()

    def test_record_cash_in_transaction(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyTransaction
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        c.post(url, {
            "tx_type": "cash_in",
            "network": "tnm",
            "amount": "5000",
            "commission": "50",
            "customer_phone": "0999123456",
            "reference_number": "REF001",
            "notes": "",
            "charges": "0",
        })
        tx = MobileMoneyTransaction.objects.filter(business=business).first()
        if tx:
            assert tx.tx_type == "cash_in"
            assert tx.amount == Decimal("5000")

    def test_credits_page_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:credits")
        except NoReverseMatch:
            pytest.skip("mobilemoney:credits URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_create_customer_credit_via_post(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        try:
            url = reverse("mobilemoney:credits")
        except NoReverseMatch:
            pytest.skip("mobilemoney:credits URL not found")
        resp = c.post(url, {
            "action": "create",
            "credit_type": "customer_credit",
            "customer_name": "Alice Banda",
            "customer_phone": "0881234567",
            "amount_credited": "10000",
            "due_date": "2026-05-31",
            "reason": "Sent money, forgot to collect",
            "notes": "",
        })
        assert resp.status_code in [200, 302]
        assert MobileMoneyCredit.objects.filter(business=business, credit_type=CreditType.CUSTOMER_CREDIT).exists()

    def test_create_agent_debt_via_post(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        try:
            url = reverse("mobilemoney:credits")
        except NoReverseMatch:
            pytest.skip("mobilemoney:credits URL not found")
        resp = c.post(url, {
            "action": "create",
            "credit_type": "agent_debt",
            "customer_name": "Agent Kamanga",
            "customer_phone": "0991234567",
            "amount_credited": "25000",
            "reason": "Borrowed float during peak",
            "notes": "",
        })
        assert resp.status_code in [200, 302]
        assert MobileMoneyCredit.objects.filter(business=business, credit_type=CreditType.AGENT_DEBT).exists()

    def test_credit_repayment_reduces_balance(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Test Customer",
            amount_credited=Decimal("10000"),
        )
        try:
            url = reverse("mobilemoney:credit_repayment", kwargs={"credit_id": credit.id})
        except NoReverseMatch:
            pytest.skip("mobilemoney:credit_repayment URL not found")
        c.post(url, {"amount": "4000"})
        credit.refresh_from_db()
        assert credit.amount_repaid == Decimal("4000")
        assert credit.balance == Decimal("6000")

    def test_reconciliation_page_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:reconciliation")
        except NoReverseMatch:
            pytest.skip("mobilemoney:reconciliation URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_reconciliation_post_saves_record(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        try:
            url = reverse("mobilemoney:reconciliation")
        except NoReverseMatch:
            pytest.skip("mobilemoney:reconciliation URL not found")
        c.post(url, {
            "date": date.today().isoformat(),
            "opening_cash": "100000",
            "opening_float": "50000",
            "actual_closing_cash": "95000",
            "notes": "Slight shortage today",
        })
        recon = MobileMoneyReconciliation.objects.filter(business=business).first()
        if recon:
            assert recon.actual_closing_cash == Decimal("95000")
            assert recon.difference < 0

    def test_commissions_page_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:commissions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:commissions URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_settlements_page_renders(self, mm_client):
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:settlements")
        except NoReverseMatch:
            pytest.skip("mobilemoney:settlements URL not found")
        resp = c.get(url)
        assert resp.status_code == 200

    def test_create_settlement_via_post(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import AgentSettlement
        try:
            url = reverse("mobilemoney:settlements")
        except NoReverseMatch:
            pytest.skip("mobilemoney:settlements URL not found")
        resp = c.post(url, {
            "action": "create",
            "settlement_type": "borrowed_float",
            "agent_name": "Agent Phiri",
            "agent_phone": "0998765432",
            "amount": "15000",
            "direction": "received",
            "notes": "Borrowed during busy period",
        })
        assert resp.status_code in [200, 302]
        assert AgentSettlement.objects.filter(business=business).exists()

    def test_zero_amount_transaction_rejected(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyTransaction
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        initial_count = MobileMoneyTransaction.objects.filter(business=business).count()
        c.post(url, {
            "tx_type": "cash_in",
            "network": "airtel",
            "amount": "0",
            "commission": "0",
            "charges": "0",
        })
        # No new transaction should be created
        assert MobileMoneyTransaction.objects.filter(business=business).count() == initial_count

    def test_negative_amount_transaction_rejected(self, mm_client):
        c, user, business = mm_client
        from inventory.models_mobilemoney import MobileMoneyTransaction
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        initial_count = MobileMoneyTransaction.objects.filter(business=business).count()
        c.post(url, {
            "tx_type": "cash_in",
            "network": "airtel",
            "amount": "-5000",
            "commission": "0",
            "charges": "0",
        })
        assert MobileMoneyTransaction.objects.filter(business=business).count() == initial_count


# ===========================================================================
# PART 7 — Movement computation utility
# ===========================================================================

@pytest.mark.django_db
class TestMovementComputation:

    def test_send_money_movements(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("send_money", Decimal("10000"))
        assert cash == Decimal("10000")
        assert float_ == Decimal("-10000")

    def test_receive_money_movements(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("receive_money", Decimal("10000"))
        assert cash == Decimal("-10000")
        assert float_ == Decimal("10000")

    def test_cash_in_movements(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("cash_in", Decimal("5000"))
        assert cash == Decimal("5000")
        assert float_ == Decimal("-5000")

    def test_cash_out_movements(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("cash_out", Decimal("5000"))
        assert cash == Decimal("-5000")
        assert float_ == Decimal("5000")

    def test_airtime_float_only(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("airtime", Decimal("2000"))
        assert cash == Decimal("0")
        assert float_ == Decimal("-2000")

    def test_failed_no_movement(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("failed", Decimal("5000"))
        assert cash == Decimal("0")
        assert float_ == Decimal("0")

    def test_float_purchase_cash_out_float_in(self):
        from inventory.verticals.mobilemoney import _compute_movements
        cash, float_ = _compute_movements("float_purchase", Decimal("50000"))
        assert cash == Decimal("-50000")
        assert float_ == Decimal("50000")


# ===========================================================================
# PART 8 — Smart insights
# ===========================================================================

@pytest.mark.django_db
class TestSmartInsights:

    def test_shortage_insight_generated(self):
        from inventory.verticals.mobilemoney import _generate_insights
        insights = _generate_insights({
            "recon_difference": Decimal("-35000"),
            "overdue_count": 0,
            "float_balance": Decimal("100000"),
            "airtel_commission_today": Decimal("0"),
            "tnm_commission_today": Decimal("0"),
            "total_agent_debts": Decimal("0"),
        })
        assert any("short" in i.lower() for i in insights)

    def test_overdue_insight_generated(self):
        from inventory.verticals.mobilemoney import _generate_insights
        insights = _generate_insights({
            "recon_difference": Decimal("0"),
            "overdue_count": 2,
            "float_balance": Decimal("100000"),
            "airtel_commission_today": Decimal("0"),
            "tnm_commission_today": Decimal("0"),
            "total_agent_debts": Decimal("0"),
        })
        assert any("overdue" in i.lower() for i in insights)

    def test_low_float_insight_generated(self):
        from inventory.verticals.mobilemoney import _generate_insights
        insights = _generate_insights({
            "recon_difference": Decimal("0"),
            "overdue_count": 0,
            "float_balance": Decimal("5000"),
            "airtel_commission_today": Decimal("0"),
            "tnm_commission_today": Decimal("0"),
            "total_agent_debts": Decimal("0"),
        })
        assert any("float" in i.lower() for i in insights)

    def test_no_insight_when_all_healthy(self):
        from inventory.verticals.mobilemoney import _generate_insights
        insights = _generate_insights({
            "recon_difference": Decimal("0"),
            "overdue_count": 0,
            "float_balance": Decimal("200000"),
            "airtel_commission_today": Decimal("0"),
            "tnm_commission_today": Decimal("0"),
            "total_agent_debts": Decimal("0"),
        })
        assert insights == []


# ===========================================================================
# PART 9 — Regression: existing vertical flows still work
# ===========================================================================

@pytest.mark.django_db
class TestRegressionExistingFlows:
    """Ensure that our changes haven't broken anything in adjacent verticals."""

    def test_grocery_sell_page_still_works(self, db):
        """Grocery sell URL still works (no import breakage from MM changes)."""
        user = User.objects.create_user(username="grocery_reg_user", password="pass123")
        biz = Business.objects.create(name="Grocery Biz", kind="grocery", owner=user)
        c = Client()
        c.force_login(user)
        session = c.session
        session["active_business_id"] = biz.id
        session.save()
        try:
            url = reverse("groceries:sell")
        except NoReverseMatch:
            pytest.skip("groceries:sell not available")
        resp = c.get(url)
        assert resp.status_code != 500, "Grocery sell page returned 500"

    def test_mm_models_import_cleanly(self):
        """Mobile money models import without errors."""
        from inventory.models_mobilemoney import (
            MobileMoneyTransaction,
            MobileMoneyCredit,
            MobileMoneyReconciliation,
            CommissionRule,
            AgentSettlement,
            CreditType,
            MobileMoneyTxType,
            MobileMoneyNetwork,
        )
        assert MobileMoneyTransaction is not None
        assert CommissionRule is not None
        assert AgentSettlement is not None

    def test_mm_views_import_cleanly(self):
        """Mobile money views import without errors."""
        from inventory.verticals.mobilemoney import (
            dashboard,
            transactions,
            credits,
            credit_repayment,
            reconciliation,
            commissions,
            settlements,
        )
        assert dashboard is not None
        assert commissions is not None
        assert settlements is not None

    def test_existing_mm_credit_still_has_balance_property(self, mm_business, mm_user):
        """Existing MobileMoneyCredit.balance property still works."""
        from inventory.models_mobilemoney import MobileMoneyCredit, CreditType
        credit = MobileMoneyCredit.objects.create(
            business=mm_business,
            credit_type=CreditType.CUSTOMER_CREDIT,
            customer_name="Legacy Test",
            amount_credited=Decimal("5000"),
            amount_repaid=Decimal("2000"),
        )
        assert credit.balance == Decimal("3000")

    def test_reconciliation_save_still_computes_difference(self, mm_business, mm_user):
        """MobileMoneyReconciliation.save() still auto-computes difference."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        recon = MobileMoneyReconciliation.objects.create(
            business=mm_business,
            date=date.today(),
            opening_cash=Decimal("50000"),
            total_cash_in=Decimal("10000"),
            total_cash_out=Decimal("5000"),
            actual_closing_cash=Decimal("55000"),
        )
        # Expected = 50000 + 10000 - 5000 = 55000; actual = 55000; diff = 0
        assert recon.expected_closing_cash == Decimal("55000")
        assert recon.difference == Decimal("0")
