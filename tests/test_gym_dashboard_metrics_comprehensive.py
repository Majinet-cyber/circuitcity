"""
Comprehensive regression tests for gym dashboard metrics.

These tests ensure the gym dashboard ALWAYS reflects real payments and costs.
This is a CRITICAL SaaS promise that cannot break.

Tests cover:
1. Revenue aggregation from GymPayment.amount field
2. Payment mix totals matching revenue
3. Costs aggregation from wallet transactions
4. Profit calculation (revenue - costs)
5. Date range filtering (Today, Last 7 Days, MTD)
6. Regression checks: non-zero amounts when payments exist
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models_verticals import (
    GymMember,
    GymPayment,
    GymSettings,
    PaymentMethod,
)
from inventory.services.gym_metrics import get_gym_dashboard_metrics, get_this_month_metrics
from inventory.utils_gym import get_business_costs_for_period

User = get_user_model()


@pytest.fixture
def gym_business(db, user):
    """Create a gym business for testing"""
    from django.utils.text import slugify
    import uuid
    
    business = Business.objects.create(
        name="Test Gym",
        slug=f"test-gym-{uuid.uuid4().hex[:8]}",
        business_kind="GYM",
        status="ACTIVE",
        created_by=user,
    )
    
    # Create gym settings
    GymSettings.objects.create(
        business=business,
        default_membership_price=Decimal("55000.00"),
        default_trainer_fee=Decimal("30000.00"),
    )
    
    return business


@pytest.fixture
def gym_member(gym_business):
    """Create a gym member for testing"""
    return GymMember.objects.create(
        business=gym_business,
        name="John Doe",
        phone="+265991234567",
        membership_start=date.today(),
        membership_end=date.today() + timedelta(days=30),
        is_active=True,
    )


@pytest.fixture
def user(db):
    """Create a test user"""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.mark.django_db
class TestGymDashboardMetrics:
    """Test suite for gym dashboard metrics calculations"""

    def test_revenue_calculation_with_single_payment(self, gym_business, gym_member, user):
        """
        CRITICAL TEST: Revenue must equal sum of payment amounts.
        This test MUST FAIL if revenue is 0 when payments exist.
        """
        # Create a payment with membership amount only
        payment = GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("55000.00"),  # This should be auto-set by save()
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # CRITICAL ASSERTION: Revenue must match payment amount
        assert metrics["revenue"] == Decimal("55000.00"), (
            f"Revenue is {metrics['revenue']} but should be MK 55000.00. "
            "Dashboard KPIs are showing 0 when payments exist!"
        )
        assert metrics["payments_count"] == 1
        
    def test_revenue_with_membership_and_trainer_fee(self, gym_business, gym_member, user):
        """
        Test that revenue includes BOTH membership amount AND trainer fee.
        Total amount = membership_amount + trainer_fee
        """
        # Create payment with trainer fee
        payment = GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("15000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )
        
        # Amount should be auto-calculated in save()
        payment.refresh_from_db()
        assert payment.amount == Decimal("70000.00"), "amount field not auto-calculated in save()"

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # Revenue must be total (membership + trainer)
        assert metrics["revenue"] == Decimal("70000.00"), (
            f"Revenue is {metrics['revenue']} but should be MK 70000.00 "
            "(55000 membership + 15000 trainer fee)"
        )

    def test_payment_mix_totals_match_revenue(self, gym_business, gym_member, user):
        """
        CRITICAL TEST: Payment mix amounts must sum to total revenue.
        This ensures consistency between KPI cards and payment mix breakdown.
        """
        # Create 4 payments with different methods
        payments_data = [
            (Decimal("55000.00"), Decimal("0.00"), PaymentMethod.CASH),
            (Decimal("55000.00"), Decimal("15000.00"), PaymentMethod.MOBILE_MONEY),
            (Decimal("60000.00"), Decimal("0.00"), PaymentMethod.CASH),
            (Decimal("55000.00"), Decimal("20000.00"), PaymentMethod.BANK),
        ]
        
        total_expected = Decimal("0.00")
        for membership, trainer, method in payments_data:
            GymPayment.objects.create(
                member=gym_member,
                membership_amount=membership,
                trainer_fee=trainer,
                payment_method=method,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),
                paid_by=user,
                paid_at=timezone.now(),
            )
            total_expected += membership + trainer

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # Revenue must match expected total
        assert metrics["revenue"] == total_expected, (
            f"Revenue is {metrics['revenue']} but should be {total_expected}"
        )
        
        # Payment mix totals must sum to revenue
        mix_total = sum(item["amount"] for item in metrics["payment_mix"])
        assert mix_total == metrics["revenue"], (
            f"Payment mix totals ({mix_total}) don't match revenue ({metrics['revenue']}). "
            "Mix cards show different amounts than KPI cards!"
        )
        
        # Check individual payment methods
        cash_total = sum(
            item["amount"] for item in metrics["payment_mix"] 
            if item["method"] == dict(PaymentMethod.choices)[PaymentMethod.CASH]
        )
        assert cash_total == Decimal("115000.00"), f"Cash total is {cash_total}, expected MK 115000.00"

    def test_date_range_filtering_mtd(self, gym_business, gym_member, user):
        """
        Test that MTD (Month-to-Date) filtering works correctly.
        Payments outside the range must be excluded.
        """
        today = date.today()
        month_start = today.replace(day=1)
        
        # Payment in current month (should be included)
        payment_current = GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=today,
            end_date=today + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )
        
        # Payment in previous month (should be excluded)
        last_month = today.replace(day=1) - timedelta(days=1)
        payment_old = GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=last_month,
            end_date=last_month + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.make_aware(
                timezone.datetime.combine(last_month, timezone.datetime.min.time())
            ),
        )

        # Get MTD metrics
        metrics = get_gym_dashboard_metrics(gym_business, month_start, today)

        # Should only include current month payment
        assert metrics["revenue"] == Decimal("55000.00"), (
            f"MTD revenue is {metrics['revenue']}, should exclude last month's payment"
        )
        assert metrics["payments_count"] == 1

    def test_costs_from_wallet_transactions(self, gym_business):
        """
        Test that costs are properly aggregated from wallet transactions.
        This ensures dashboard costs match Admin Wallet > Costs.
        """
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        today = date.today()
        
        # Create cost transactions (stored as negative in wallet)
        # Once-off cost
        WalletTransaction.objects.create(
            business=gym_business,
            amount=Decimal("-50000.00"),  # Negative for costs
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            is_recurring=False,
            effective_date=today,
            note="Rent payment",
        )
        
        # Recurring cost
        WalletTransaction.objects.create(
            business=gym_business,
            amount=Decimal("-30000.00"),
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            is_recurring=True,
            effective_from=today,
            note="Utility bill",
        )

        # Get costs for today
        costs = get_business_costs_for_period(gym_business, today, today)

        # Costs should be positive sum (abs of negative transactions)
        assert costs == Decimal("80000.00"), (
            f"Costs are {costs}, should be MK 80000.00 (50000 + 30000)"
        )

    def test_profit_calculation(self, gym_business, gym_member, user):
        """
        Test that profit = revenue - costs.
        """
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        today = date.today()
        
        # Create revenue (payment)
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("15000.00"),  # Total: 70000
            payment_method=PaymentMethod.CASH,
            start_date=today,
            end_date=today + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )
        
        # Create costs
        WalletTransaction.objects.create(
            business=gym_business,
            amount=Decimal("-20000.00"),
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            effective_date=today,
            note="Equipment repair",
        )

        # Get metrics
        metrics = get_gym_dashboard_metrics(gym_business, today, today)
        costs = get_business_costs_for_period(gym_business, today, today)

        # Calculate profit
        profit = metrics["revenue"] - costs

        assert metrics["revenue"] == Decimal("70000.00")
        assert costs == Decimal("20000.00")
        assert profit == Decimal("50000.00"), (
            f"Profit is {profit}, should be MK 50000.00 (70000 - 20000)"
        )

    def test_regression_check_nonzero_revenue_when_payments_exist(
        self, gym_business, gym_member, user
    ):
        """
        REGRESSION TEST: This test ensures the dashboard NEVER shows MK 0 revenue
        when payments exist. This is the CRITICAL bug that cannot happen again.
        """
        # Create ANY payment
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # CRITICAL REGRESSION CHECK
        assert metrics["payments_count"] > 0, "No payments found, test setup is wrong"
        assert metrics["revenue"] > 0, (
            "REGRESSION DETECTED: Dashboard shows MK 0 revenue when payments exist! "
            "This is the critical bug that must never happen again."
        )

    def test_regression_check_nonzero_costs_when_costs_exist(self, gym_business):
        """
        REGRESSION TEST: Ensure costs show non-zero when costs exist in admin wallet.
        """
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        today = date.today()
        
        # Add a cost
        WalletTransaction.objects.create(
            business=gym_business,
            amount=Decimal("-25000.00"),
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            effective_date=today,
            note="Test cost",
        )

        # Get costs
        costs = get_business_costs_for_period(gym_business, today, today)

        # CRITICAL REGRESSION CHECK
        assert costs > 0, (
            "REGRESSION DETECTED: Dashboard shows MK 0 costs when costs exist in admin wallet! "
            "This breaks the promise that admin wallet costs appear on dashboard."
        )

    def test_inactive_payments_excluded(self, gym_business, gym_member, user):
        """
        Test that inactive (cancelled/refunded) payments are excluded from metrics.
        """
        # Active payment
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
            is_active=True,
        )
        
        # Inactive payment (refunded)
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
            is_active=False,  # Excluded from metrics
        )

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # Should only count active payment
        assert metrics["revenue"] == Decimal("55000.00")
        assert metrics["payments_count"] == 1

    def test_amount_field_auto_calculated(self, gym_business, gym_member, user):
        """
        Test that the amount field is ALWAYS auto-calculated in save().
        This ensures we never have NULL amounts in the database.
        """
        # Create payment without explicitly setting amount
        payment = GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("15000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
        )

        # Reload from DB
        payment.refresh_from_db()

        # Amount should be auto-calculated
        assert payment.amount is not None, "amount field is NULL, auto-calculation failed"
        assert payment.amount == Decimal("70000.00"), (
            f"amount field is {payment.amount}, should be 70000.00 (55000 + 15000)"
        )

    def test_payment_mix_counts_match_totals(self, gym_business, gym_member, user):
        """
        Test that payment mix shows correct counts and amounts per method.
        """
        # Create 2 cash payments and 1 mobile money payment
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )
        
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("60000.00"),
            trainer_fee=Decimal("10000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )
        
        GymPayment.objects.create(
            member=gym_member,
            membership_amount=Decimal("55000.00"),
            trainer_fee=Decimal("0.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=user,
            paid_at=timezone.now(),
        )

        # Get metrics
        today = date.today()
        metrics = get_gym_dashboard_metrics(gym_business, today, today)

        # Find cash and mobile money in payment mix
        cash_item = next(
            (item for item in metrics["payment_mix"] 
             if item["method"] == dict(PaymentMethod.choices)[PaymentMethod.CASH]),
            None
        )
        mobile_item = next(
            (item for item in metrics["payment_mix"] 
             if item["method"] == dict(PaymentMethod.choices)[PaymentMethod.MOBILE_MONEY]),
            None
        )

        # Verify counts and amounts
        assert cash_item is not None, "Cash not found in payment mix"
        assert cash_item["count"] == 2, f"Cash count is {cash_item['count']}, should be 2"
        assert cash_item["amount"] == Decimal("125000.00"), (
            f"Cash amount is {cash_item['amount']}, should be 125000 (55000 + 60000 + 10000)"
        )
        
        assert mobile_item is not None, "Mobile Money not found in payment mix"
        assert mobile_item["count"] == 1
        assert mobile_item["amount"] == Decimal("55000.00")

