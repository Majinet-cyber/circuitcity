"""
Tests for Gym Membership Days and Next Payment Date calculations.

This test suite ensures:
1. "Days Left" never shows values like "31 / 30 days"
2. "Next Payment" is never blank for normal time-bound memberships
3. Days left calculation is accurate and capped at duration_days
4. Next payment date is exactly duration_days after last payment
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import GymMember, GymMemberStatus
from inventory.utils_gym import (
    compute_membership_days,
    compute_next_payment_date,
    get_membership_status,
    GYM_MEMBERSHIP_DAYS,
)

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
    """Create a test gym member."""
    return GymMember.objects.create(
        business=business,
        name="John Doe",
        phone="555-1234",
        email="john@example.com",
        membership_fee=Decimal("50.00"),
    )


class TestComputeMembershipDays:
    """Tests for compute_membership_days helper function."""

    def test_new_membership_today(self):
        """Test: New membership created today with duration_days = 30."""
        today = date(2025, 1, 1)
        start_date = today
        duration_days = 30

        days_left, total_days = compute_membership_days(start_date, duration_days, today)

        # Should show "30 / 30 days"
        assert days_left == 30
        assert total_days == 30

    def test_membership_after_5_days(self):
        """Test: Membership after 5 days."""
        start_date = date(2025, 1, 1)
        today = date(2025, 1, 6)  # 5 days later
        duration_days = 30

        days_left, total_days = compute_membership_days(start_date, duration_days, today)

        # Should show "25 / 30 days"
        assert days_left == 25
        assert total_days == 30

    def test_membership_after_30_days(self):
        """Test: Membership after 30 days (expired)."""
        start_date = date(2025, 1, 1)
        today = date(2025, 1, 31)  # 30 days later
        duration_days = 30

        days_left, total_days = compute_membership_days(start_date, duration_days, today)

        # Should show "0 / 30 days" (NOT negative)
        assert days_left == 0
        assert total_days == 30

    def test_membership_after_31_days(self):
        """Test: Membership after 31+ days (expired, capped at 0)."""
        start_date = date(2025, 1, 1)
        today = date(2025, 2, 1)  # 31 days later
        duration_days = 30

        days_left, total_days = compute_membership_days(start_date, duration_days, today)

        # Should show "0 / 30 days" (NOT "31 / 30 days")
        assert days_left == 0
        assert total_days == 30

    def test_never_exceeds_duration_days(self):
        """Test: Days left never exceeds duration_days."""
        start_date = date(2025, 1, 1)
        duration_days = 30

        # Test various dates: before start, at start, during, at end, after end
        test_cases = [
            (date(2024, 12, 31), 30, 30),  # 1 day before: should cap at 30
            (date(2025, 1, 1), 30, 30),  # Day 0: 30 days left (start day)
            (date(2025, 1, 2), 29, 30),  # Day 1: 29 days left (1 day elapsed)
            (date(2025, 1, 15), 16, 30),  # Day 14: 16 days left (14 days elapsed)
            (date(2025, 1, 30), 1, 30),  # Day 29: 1 day left (29 days elapsed)
            (date(2025, 1, 31), 0, 30),  # Day 30: 0 days left (30 days elapsed)
            (date(2025, 2, 1), 0, 30),  # Day 31: 0 days left (capped)
            (date(2025, 2, 10), 0, 30),  # Day 40: 0 days left (capped)
        ]

        for today, expected_left, expected_total in test_cases:
            days_left, total_days = compute_membership_days(start_date, duration_days, today)
            assert days_left == expected_left, f"Failed for today={today}: expected {expected_left}, got {days_left}"
            assert total_days == expected_total
            assert 0 <= days_left <= duration_days, f"Days left ({days_left}) should be between 0 and {duration_days}"

    def test_different_duration_days(self):
        """Test: Works with different duration_days values."""
        start_date = date(2025, 1, 1)
        today = date(2025, 1, 11)  # 10 days later

        # Test with 15-day membership
        days_left, total_days = compute_membership_days(start_date, 15, today)
        assert days_left == 5
        assert total_days == 15

        # Test with 60-day membership
        days_left, total_days = compute_membership_days(start_date, 60, today)
        assert days_left == 50
        assert total_days == 60


class TestComputeNextPaymentDate:
    """Tests for compute_next_payment_date helper function."""

    def test_next_payment_30_days_after_last_payment(self):
        """Test: Next payment is exactly 30 days after last payment."""
        last_payment_date = date(2025, 1, 1)
        duration_days = 30

        next_payment = compute_next_payment_date(last_payment_date, duration_days)

        # Should be Jan 31 (30 days after Jan 1)
        assert next_payment == date(2025, 1, 31)

    def test_next_payment_with_no_last_payment(self):
        """Test: Returns None if no payment has been made."""
        next_payment = compute_next_payment_date(None, 30)
        assert next_payment is None

    def test_next_payment_different_durations(self):
        """Test: Works with different duration values."""
        last_payment_date = date(2025, 1, 1)

        # 15-day membership
        next_payment = compute_next_payment_date(last_payment_date, 15)
        assert next_payment == date(2025, 1, 16)

        # 60-day membership
        next_payment = compute_next_payment_date(last_payment_date, 60)
        assert next_payment == date(2025, 3, 2)

    def test_next_payment_handles_month_boundaries(self):
        """Test: Correctly handles month/year boundaries."""
        # End of month
        last_payment_date = date(2025, 1, 31)
        next_payment = compute_next_payment_date(last_payment_date, 30)
        assert next_payment == date(2025, 3, 2)  # 30 days after Jan 31

        # End of year
        last_payment_date = date(2024, 12, 15)
        next_payment = compute_next_payment_date(last_payment_date, 30)
        assert next_payment == date(2025, 1, 14)  # 30 days after Dec 15


class TestGymMemberDaysLeftCurrent:
    """Tests for GymMember.days_left_current property."""

    def test_days_left_current_caps_at_duration(self, gym_member):
        """Test: days_left_current never exceeds duration_days."""
        # Set up a membership that started today
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        # Days left should be exactly 30
        assert gym_member.days_left_current == 30

        # Verify it's not 31
        assert gym_member.days_left_current <= GYM_MEMBERSHIP_DAYS

    def test_days_left_current_after_several_days(self, gym_member):
        """Test: days_left_current decreases correctly over time."""
        # Set up a membership that started 5 days ago
        start_date = timezone.now().date() - timedelta(days=5)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        # Days left should be 25 (30 - 5)
        assert gym_member.days_left_current == 25

    def test_days_left_current_expired_membership(self, gym_member):
        """Test: days_left_current returns 0 for expired membership."""
        # Set up a membership that started 35 days ago (expired)
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        # Days left should be 0 (not negative)
        assert gym_member.days_left_current == 0

    def test_days_left_current_no_payment(self, gym_member):
        """Test: days_left_current returns 0 when no payment exists."""
        # Member with no payment
        assert gym_member.days_left_current == 0


class TestGymMemberNextPaymentDate:
    """Tests for GymMember.next_payment_date method."""

    def test_next_payment_date_is_30_days_after_last_payment(self, gym_member):
        """Test: next_payment_date is exactly 30 days after last payment."""
        payment_date = date(2025, 1, 1)
        gym_member.set_paid(payment_date=payment_date, membership_fee=Decimal("50.00"))

        next_payment = gym_member.next_payment_date()

        # Should be Jan 31 (30 days after Jan 1)
        assert next_payment == date(2025, 1, 31)

    def test_next_payment_date_not_blank_for_active_membership(self, gym_member):
        """Test: next_payment_date is never None for active memberships."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        next_payment = gym_member.next_payment_date()

        # Should NOT be None
        assert next_payment is not None
        # Should be exactly 30 days from today
        assert next_payment == today + timedelta(days=30)

    def test_next_payment_date_is_none_without_payment(self, gym_member):
        """Test: next_payment_date returns None when member has never paid."""
        next_payment = gym_member.next_payment_date()
        assert next_payment is None


class TestGetMembershipStatus:
    """Tests for get_membership_status function."""

    def test_membership_status_new_member_today(self, gym_member):
        """Test: New member today shows 30 days remaining."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        status = get_membership_status(gym_member, today)

        assert status["status_code"] == "active"
        assert status["label"] == "Active"
        assert status["days_remaining"] == 30
        assert status["total_days"] == 30
        assert status["start_date"] == today
        assert status["end_date"] == today + timedelta(days=29)

    def test_membership_status_after_5_days(self, gym_member):
        """Test: Member after 5 days shows 25 days remaining."""
        start_date = date(2025, 1, 1)
        today = date(2025, 1, 6)

        gym_member.membership_start = start_date
        gym_member.membership_end = start_date + timedelta(days=29)
        gym_member.last_payment_date = start_date
        gym_member.save()

        status = get_membership_status(gym_member, today)

        assert status["status_code"] == "active"
        assert status["days_remaining"] == 25
        assert status["total_days"] == 30

    def test_membership_status_expired(self, gym_member):
        """Test: Expired membership shows 0 days remaining."""
        start_date = date(2025, 1, 1)
        today = date(2025, 2, 1)  # 31 days later

        gym_member.membership_start = start_date
        gym_member.membership_end = start_date + timedelta(days=29)
        gym_member.last_payment_date = start_date
        gym_member.save()

        status = get_membership_status(gym_member, today)

        assert status["status_code"] == "expired"
        assert status["label"] == "Expired"
        assert status["days_remaining"] == 0

    def test_membership_status_no_membership(self, gym_member):
        """Test: Member with no membership shows correct status."""
        status = get_membership_status(gym_member)

        assert status["status_code"] == "none"
        assert status["label"] == "No membership"
        assert status["days_remaining"] == 0
        assert status["total_days"] is None


class TestCentralizedMembershipProperties:
    """Tests for the new centralized properties on GymMember model."""

    def test_duration_days_property(self, gym_member):
        """Test: duration_days property returns correct value."""
        assert gym_member.duration_days == 30

    def test_days_used_on_payment_day(self, gym_member):
        """Test: days_used is 0 on the day of payment."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        assert gym_member.days_used == 0

    def test_days_used_after_5_days(self, gym_member):
        """Test: days_used is 5 after 5 days."""
        start_date = timezone.now().date() - timedelta(days=5)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_used == 5

    def test_days_used_caps_at_duration(self, gym_member):
        """Test: days_used never exceeds duration_days."""
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_used == 30

    def test_days_left_on_payment_day(self, gym_member):
        """Test: days_left is 30 on the day of payment."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        assert gym_member.days_left == 30

    def test_days_left_after_5_days(self, gym_member):
        """Test: days_left is 25 after 5 days."""
        start_date = timezone.now().date() - timedelta(days=5)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_left == 25

    def test_days_left_expired_membership(self, gym_member):
        """Test: days_left is 0 for expired membership."""
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_left == 0

    def test_days_left_no_payment(self, gym_member):
        """Test: days_left is 0 when no payment exists."""
        assert gym_member.days_left == 0

    def test_days_left_display_on_payment_day(self, gym_member):
        """Test: days_left_display shows '30 / 30 days' on payment day."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        assert gym_member.days_left_display == "30 / 30 days"

    def test_days_left_display_after_5_days(self, gym_member):
        """Test: days_left_display shows '25 / 30 days' after 5 days."""
        start_date = timezone.now().date() - timedelta(days=5)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_left_display == "25 / 30 days"

    def test_days_left_display_expired(self, gym_member):
        """Test: days_left_display shows '0 / 30 days' when expired."""
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.days_left_display == "0 / 30 days"

    def test_next_payment_date_property_on_payment_day(self, gym_member):
        """Test: next_payment_date_property is 30 days after payment."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        expected = today + timedelta(days=30)
        assert gym_member.next_payment_date_property == expected

    def test_next_payment_date_property_no_payment(self, gym_member):
        """Test: next_payment_date_property is None without payment."""
        assert gym_member.next_payment_date_property is None

    def test_is_active_membership_fresh_payment(self, gym_member):
        """Test: is_active_membership is True on payment day."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        assert gym_member.is_active_membership is True

    def test_is_active_membership_during_period(self, gym_member):
        """Test: is_active_membership is True during membership period."""
        start_date = timezone.now().date() - timedelta(days=15)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.is_active_membership is True

    def test_is_active_membership_expired(self, gym_member):
        """Test: is_active_membership is False when expired."""
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.is_active_membership is False

    def test_is_active_membership_no_payment(self, gym_member):
        """Test: is_active_membership is False without payment."""
        assert gym_member.is_active_membership is False

    def test_status_label_active(self, gym_member):
        """Test: status_label is 'Active' for active membership."""
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        assert gym_member.status_label == "Active"

    def test_status_label_no_membership(self, gym_member):
        """Test: status_label is 'No membership' without payment."""
        assert gym_member.status_label == "No membership"

    def test_status_label_expired(self, gym_member):
        """Test: status_label is 'No membership' when expired."""
        start_date = timezone.now().date() - timedelta(days=35)
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))

        assert gym_member.status_label == "No membership"


class TestIntegrationScenarios:
    """Integration tests for complete membership scenarios."""

    def test_complete_30_day_lifecycle(self, gym_member):
        """Test: Complete 30-day membership lifecycle."""
        start_date = date(2025, 1, 1)

        # Day 0: Payment made
        gym_member.set_paid(payment_date=start_date, membership_fee=Decimal("50.00"))
        assert gym_member.membership_start == start_date
        assert gym_member.membership_end == date(2025, 1, 30)
        assert gym_member.next_payment_date() == date(2025, 1, 31)

        # Day 0: Check status
        status = get_membership_status(gym_member, start_date)
        assert status["days_remaining"] == 30

        # Day 1: Check status
        status = get_membership_status(gym_member, date(2025, 1, 2))
        assert status["days_remaining"] == 29

        # Day 15: Check status
        status = get_membership_status(gym_member, date(2025, 1, 16))
        assert status["days_remaining"] == 15

        # Day 29: Last day of membership
        status = get_membership_status(gym_member, date(2025, 1, 30))
        assert status["days_remaining"] == 1
        assert status["status_code"] == "active"

        # Day 30: Membership expired, payment due
        status = get_membership_status(gym_member, date(2025, 1, 31))
        assert status["days_remaining"] == 0
        assert status["status_code"] == "expired"
        assert gym_member.next_payment_date() == date(2025, 1, 31)

    def test_prevents_31_30_days_bug(self, gym_member):
        """Test: Ensures "31 / 30 days" bug can never occur."""
        # Try various edge cases that might cause the bug
        test_dates = [
            date(2025, 1, 1),
            date(2025, 1, 31),
            date(2025, 2, 28),
            date(2025, 12, 31),
        ]

        for payment_date in test_dates:
            gym_member.set_paid(payment_date=payment_date, membership_fee=Decimal("50.00"))

            # Check days_left never exceeds 30
            assert gym_member.days_left_current <= 30, f"days_left_current exceeds 30 for payment_date={payment_date}"

            # Check via get_membership_status
            status = get_membership_status(gym_member, payment_date)
            assert status["days_remaining"] <= 30, f"days_remaining exceeds 30 for payment_date={payment_date}"

            # Check that the display would show "30 / 30 days"
            days_left, total_days = compute_membership_days(
                gym_member.membership_start, GYM_MEMBERSHIP_DAYS, payment_date
            )
            assert days_left == 30
            assert total_days == 30

    def test_next_payment_never_blank_for_paid_members(self, gym_member):
        """Test: Next payment is never None for members who have paid."""
        # Test various payment dates
        test_dates = [
            date(2025, 1, 1),
            date(2025, 1, 15),
            date(2025, 2, 1),
            date(2025, 12, 31),
        ]

        for payment_date in test_dates:
            gym_member.set_paid(payment_date=payment_date, membership_fee=Decimal("50.00"))

            next_payment = gym_member.next_payment_date()

            # Should NEVER be None
            assert next_payment is not None, f"next_payment_date is None for payment_date={payment_date}"

            # Should be exactly 30 days after payment
            expected = payment_date + timedelta(days=30)
            assert next_payment == expected, f"next_payment_date incorrect for payment_date={payment_date}"

    def test_checkin_page_shows_correct_data_on_payment_day(self, gym_member):
        """
        Test: Check-in page shows correct data on the day of payment.

        This is the main bug fix: On payment day, the check-in page should show:
        - Membership Status: "Active"
        - Days Left: "30 / 30 days"
        - Next Payment: payment_date + 30 days (not blank)
        """
        today = timezone.now().date()
        gym_member.set_paid(payment_date=today, membership_fee=Decimal("50.00"))

        # Verify all properties show correct values
        assert gym_member.status_label == "Active"
        assert gym_member.days_left == 30
        assert gym_member.days_left_display == "30 / 30 days"
        assert gym_member.is_active_membership is True
        assert gym_member.next_payment_date_property == today + timedelta(days=30)

        # Verify using get_membership_status as well
        status = get_membership_status(gym_member, today)
        assert status["status_code"] == "active"
        assert status["label"] == "Active"
        assert status["days_remaining"] == 30
