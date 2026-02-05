"""
Tests for gym membership proration fix.

This test suite verifies that membership days are correctly prorated based on payment amount:
- Every monthly payment buys 30 days at the current monthly membership fee
- Daily rate = monthly_fee / 30
- Days granted = amount_paid / daily_rate

Example: monthly_fee=50,000; amount_paid=55,000 => daily_rate=1,666.666... => days≈33.0
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import GymMember, GymMemberStatus
from inventory.utils_gym import calculate_prorated_days, calculate_membership_period, GYM_MEMBERSHIP_DAYS

User = get_user_model()


@pytest.fixture
def business(db):
    """Create a test business."""
    owner = User.objects.create_user(username="gymowner", password="testpass123")
    return Business.objects.create(
        name="Test Gym",
        slug="test-gym",
        status="ACTIVE",
        business_kind="gym",
        created_by=owner,
    )


@pytest.fixture
def gym_member(business):
    """Create a test gym member with monthly fee of 50,000."""
    return GymMember.objects.create(
        business=business,
        name="John Doe",
        phone="555-1234",
        email="john@example.com",
        membership_fee=Decimal("50000.00"),  # 50,000 MWK monthly fee
    )


class TestCalculateProratedDays:
    """Tests for calculate_prorated_days with custom monthly fees."""

    def test_exact_monthly_fee_grants_30_days(self):
        """Paying exactly the monthly fee should grant exactly 30 days."""
        monthly_fee = Decimal("50000.00")
        amount_paid = Decimal("50000.00")

        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)

        assert days == 30

    def test_overpayment_grants_proportional_days(self):
        """Paying more than monthly fee should grant proportionally more days."""
        monthly_fee = Decimal("50000.00")
        amount_paid = Decimal("55000.00")

        # Expected: 55,000 / (50,000/30) = 55,000 / 1,666.666... = 33.0
        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)

        assert days == 33  # Should be 33 days, not 30

    def test_double_payment_grants_60_days(self):
        """Paying double the monthly fee should grant 60 days."""
        monthly_fee = Decimal("50000.00")
        amount_paid = Decimal("100000.00")

        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)

        assert days == 60

    def test_half_payment_grants_15_days(self):
        """Paying half the monthly fee should grant 15 days."""
        monthly_fee = Decimal("50000.00")
        amount_paid = Decimal("25000.00")

        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)

        assert days == 15

    def test_minimum_payment_grants_at_least_1_day(self):
        """Any positive payment should grant at least 1 day."""
        monthly_fee = Decimal("50000.00")
        amount_paid = Decimal("100.00")  # Very small payment

        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)

        assert days >= 1

    def test_full_payment_grants_at_least_30_days(self):
        """Paying full monthly fee or more should grant at least 30 days."""
        monthly_fee = Decimal("50000.00")

        # Test exact amount
        days = calculate_prorated_days(Decimal("50000.00"), monthly_fee=monthly_fee)
        assert days >= 30

        # Test slightly more
        days = calculate_prorated_days(Decimal("50001.00"), monthly_fee=monthly_fee)
        assert days >= 30

    def test_rounding_is_fair(self):
        """Test that rounding is fair (ROUND_HALF_UP)."""
        monthly_fee = Decimal("50000.00")

        # Test case that would round down with FLOOR
        # 51,666.66 / (50,000/30) = 31.0 exactly
        amount_paid = Decimal("51666.66")
        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)
        assert days == 31

        # Test case that would round up with HALF_UP
        # 51,700 / (50,000/30) = 31.02 => rounds to 31
        amount_paid = Decimal("51700.00")
        days = calculate_prorated_days(amount_paid, monthly_fee=monthly_fee)
        assert days == 31

    def test_different_monthly_fees(self):
        """Test proration works correctly with different monthly fees."""
        # Monthly fee of 30,000
        days = calculate_prorated_days(Decimal("30000.00"), monthly_fee=Decimal("30000.00"))
        assert days == 30

        days = calculate_prorated_days(Decimal("33000.00"), monthly_fee=Decimal("30000.00"))
        assert days == 33

        # Monthly fee of 100,000
        days = calculate_prorated_days(Decimal("100000.00"), monthly_fee=Decimal("100000.00"))
        assert days == 30

        days = calculate_prorated_days(Decimal("110000.00"), monthly_fee=Decimal("100000.00"))
        assert days == 33

    def test_uses_global_constant_when_no_fee_provided(self):
        """When no monthly_fee is provided, should use GYM_MONTHLY_FEE constant."""
        from inventory.utils_gym import GYM_MONTHLY_FEE

        # Should use global constant (55,000)
        days = calculate_prorated_days(GYM_MONTHLY_FEE)
        assert days == 30

        days = calculate_prorated_days(GYM_MONTHLY_FEE * 2)
        assert days == 60


class TestCalculateMembershipPeriod:
    """Tests for calculate_membership_period with proration."""

    def test_exact_payment_grants_30_days(self, gym_member):
        """Paying exactly the monthly fee should grant exactly 30 days."""
        today = date(2025, 1, 1)
        amount = Decimal("50000.00")  # Exactly the monthly fee

        new_start, new_end, days_granted = calculate_membership_period(
            amount=amount, member=gym_member, start_date=today, today=today
        )

        assert new_start == date(2025, 1, 1)
        assert new_end == date(2025, 1, 30)  # 30 days inclusive
        assert days_granted == 30

    def test_overpayment_grants_more_than_30_days(self, gym_member):
        """Paying more than monthly fee should grant more than 30 days."""
        today = date(2025, 1, 1)
        amount = Decimal("55000.00")  # More than monthly fee

        new_start, new_end, days_granted = calculate_membership_period(
            amount=amount, member=gym_member, start_date=today, today=today
        )

        assert new_start == date(2025, 1, 1)
        assert days_granted == 33  # Should be 33 days
        assert new_end == date(2025, 2, 2)  # Jan 1 + 32 days = Feb 2 (33 days inclusive)

    def test_double_payment_grants_60_days(self, gym_member):
        """Paying double the monthly fee should grant 60 days."""
        today = date(2025, 1, 1)
        amount = Decimal("100000.00")  # Double the monthly fee

        new_start, new_end, days_granted = calculate_membership_period(
            amount=amount, member=gym_member, start_date=today, today=today
        )

        assert new_start == date(2025, 1, 1)
        assert days_granted == 60
        assert new_end == date(2025, 3, 1)  # Jan 1 + 59 days = Mar 1 (60 days inclusive)

    def test_half_payment_grants_15_days(self, gym_member):
        """Paying half the monthly fee should grant 15 days."""
        today = date(2025, 1, 1)
        amount = Decimal("25000.00")  # Half the monthly fee

        new_start, new_end, days_granted = calculate_membership_period(
            amount=amount, member=gym_member, start_date=today, today=today
        )

        assert new_start == date(2025, 1, 1)
        assert days_granted == 15
        assert new_end == date(2025, 1, 15)  # Jan 1 + 14 days = Jan 15 (15 days inclusive)

    def test_auto_extension_with_overpayment(self, gym_member):
        """Active member paying more should extend from current end date."""
        today = date(2025, 1, 15)

        # Set up active membership ending on Jan 30
        gym_member.membership_start = date(2025, 1, 1)
        gym_member.membership_end = date(2025, 1, 30)
        gym_member.save()

        # Pay 55,000 on Jan 15 (should extend from Jan 31)
        amount = Decimal("55000.00")

        new_start, new_end, days_granted = calculate_membership_period(
            amount=amount, member=gym_member, start_date=today, today=today
        )

        assert new_start == date(2025, 1, 31)  # Day after current end
        assert days_granted == 33
        assert new_end == date(2025, 3, 4)  # Jan 31 + 32 days = Mar 4 (33 days inclusive)


class TestGymMemberSetPaid:
    """Tests for GymMember.set_paid with proration."""

    def test_set_paid_with_exact_fee(self, gym_member):
        """set_paid with exact monthly fee should grant 30 days."""
        today = timezone.now().date()

        gym_member.set_paid(
            payment_date=today,
            membership_fee=Decimal("50000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("50000.00"),
        )

        assert gym_member.membership_start == today
        assert gym_member.membership_end == today + timedelta(days=29)  # 30 days inclusive
        assert gym_member.status == GymMemberStatus.ACTIVE

    def test_set_paid_with_overpayment(self, gym_member):
        """set_paid with overpayment should grant more than 30 days."""
        today = timezone.now().date()

        gym_member.set_paid(
            payment_date=today,
            membership_fee=Decimal("50000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("55000.00"),
        )

        # Should grant 33 days
        expected_end = today + timedelta(days=32)  # 33 days inclusive

        assert gym_member.membership_start == today
        assert gym_member.membership_end == expected_end
        assert gym_member.status == GymMemberStatus.ACTIVE

    def test_set_paid_with_double_payment(self, gym_member):
        """set_paid with double payment should grant 60 days."""
        today = timezone.now().date()

        gym_member.set_paid(
            payment_date=today,
            membership_fee=Decimal("50000.00"),
            trainer_fee=Decimal("0.00"),
            amount=Decimal("100000.00"),
        )

        # Should grant 60 days
        expected_end = today + timedelta(days=59)  # 60 days inclusive

        assert gym_member.membership_start == today
        assert gym_member.membership_end == expected_end
        assert gym_member.status == GymMemberStatus.ACTIVE


class TestRegressionScenarios:
    """Regression tests to ensure standard behavior is preserved."""

    def test_standard_case_still_yields_30_days(self, gym_member):
        """Standard case: paying exactly monthly fee still yields exactly 30 days."""
        today = date(2025, 1, 1)

        new_start, new_end, days_granted = calculate_membership_period(
            amount=Decimal("50000.00"), member=gym_member, start_date=today, today=today
        )

        assert days_granted == 30
        assert new_end == date(2025, 1, 30)

    def test_no_breaking_changes_to_existing_members(self, business):
        """Existing members with different monthly fees should work correctly."""
        # Member with different monthly fee
        member = GymMember.objects.create(
            business=business,
            name="Jane Doe",
            phone="555-5678",
            email="jane@example.com",
            membership_fee=Decimal("30000.00"),  # Different fee
        )

        today = timezone.now().date()

        # Pay exactly their monthly fee
        member.set_paid(
            payment_date=today,
            membership_fee=Decimal("30000.00"),
            amount=Decimal("30000.00"),
        )

        # Should still get 30 days
        expected_end = today + timedelta(days=29)
        assert member.membership_end == expected_end

    def test_minimum_grant_for_full_payment(self, gym_member):
        """Paying full monthly fee should always grant at least 30 days."""
        today = date(2025, 1, 1)

        # Even with rounding errors, should get at least 30 days
        new_start, new_end, days_granted = calculate_membership_period(
            amount=Decimal("50000.00"), member=gym_member, start_date=today, today=today
        )

        assert days_granted >= 30

