"""
Comprehensive tests for GymMembershipService (SSOT).

This test suite ensures the Single Source of Truth service correctly computes:
- days_used, days_left, days_left_current
- membership_end
- next_payment_date

All tests use timezone-aware dates and consistent 30-day plan duration.

Symptoms being fixed:
- days_left_current = 0 but expected 25/30
- display shows "1/1 days" instead of "30/30 days"
- next_payment_date incorrect
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import GymMember, GymMemberStatus
from inventory.services.gym_membership import (
    GymMembershipService,
    get_membership_service,
    DEFAULT_MEMBERSHIP_DURATION_DAYS,
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
        membership_fee=Decimal("55000.00"),
    )


@pytest.fixture
def paid_member_today(gym_member):
    """Create a member who paid today (for model property tests)."""
    today = timezone.now().date()
    end_date = today + timedelta(days=29)  # 30 days inclusive
    
    gym_member.last_payment_date = today
    gym_member.membership_start = today
    gym_member.membership_end = end_date
    gym_member.status = GymMemberStatus.ACTIVE
    gym_member.save()
    
    return gym_member


@pytest.fixture
def paid_member_jan1(gym_member):
    """Create a member who paid on Jan 1, 2025."""
    jan1 = date(2025, 1, 1)
    jan30 = date(2025, 1, 30)
    
    gym_member.last_payment_date = jan1
    gym_member.membership_start = jan1
    gym_member.membership_end = jan30
    gym_member.status = GymMemberStatus.ACTIVE
    gym_member.save()
    
    return gym_member


class TestGymMembershipServiceBasics:
    """Test basic service initialization and helper methods."""
    
    def test_service_creation(self, gym_member):
        """Test: Can create a service instance."""
        service = GymMembershipService(gym_member)
        assert service is not None
        assert service.member == gym_member
    
    def test_factory_function(self, gym_member):
        """Test: Factory function creates service."""
        service = get_membership_service(gym_member)
        assert isinstance(service, GymMembershipService)
        assert service.member == gym_member
    
    def test_get_today_default(self, gym_member):
        """Test: _get_today returns current date by default."""
        service = GymMembershipService(gym_member)
        today = service._get_today()
        
        # Should be a date (not datetime)
        assert isinstance(today, date)
        # Should be today's date
        assert today == timezone.now().date()
    
    def test_get_today_with_param(self, gym_member):
        """Test: _get_today respects provided date parameter."""
        service = GymMembershipService(gym_member)
        test_date = date(2025, 1, 15)
        
        result = service._get_today(test_date)
        assert result == test_date


class TestDurationDays:
    """Test get_duration_days method."""
    
    def test_duration_days_no_membership(self, gym_member):
        """Test: Returns 30 when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_duration_days() == DEFAULT_MEMBERSHIP_DURATION_DAYS
    
    def test_duration_days_with_30_day_membership(self, paid_member_jan1):
        """Test: Returns 30 for a 30-day membership."""
        service = GymMembershipService(paid_member_jan1)
        # Jan 1 to Jan 30 = 30 days inclusive
        assert service.get_duration_days() == 30
    
    def test_duration_days_with_custom_membership(self, gym_member):
        """Test: Returns actual duration for non-standard periods."""
        # Set up a 60-day membership
        gym_member.membership_start = date(2025, 1, 1)
        gym_member.membership_end = date(2025, 3, 1)  # 60 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        # Jan 1 to Mar 1 = 60 days inclusive
        assert service.get_duration_days() == 60


class TestMembershipEnd:
    """Test get_membership_end method."""
    
    def test_membership_end_no_membership(self, gym_member):
        """Test: Returns None when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_membership_end() is None
    
    def test_membership_end_with_membership(self, paid_member_jan1):
        """Test: Returns correct end date."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_membership_end() == date(2025, 1, 30)


class TestDaysUsed:
    """Test get_days_used method - CRITICAL for fixing '0 days used' bug."""
    
    def test_days_used_on_payment_day(self, paid_member_jan1):
        """Test: Jan 1 payment = 0 days used on Jan 1."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_used(today=date(2025, 1, 1)) == 0
    
    def test_days_used_after_1_day(self, paid_member_jan1):
        """Test: 1 day used on Jan 2."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_used(today=date(2025, 1, 2)) == 1
    
    def test_days_used_after_5_days(self, paid_member_jan1):
        """Test: 5 days used on Jan 6."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_used(today=date(2025, 1, 6)) == 5
    
    def test_days_used_after_29_days(self, paid_member_jan1):
        """Test: 29 days used on Jan 30 (last day)."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_used(today=date(2025, 1, 30)) == 29
    
    def test_days_used_after_30_days_expired(self, paid_member_jan1):
        """Test: 30 days used on Jan 31 (first expired day)."""
        service = GymMembershipService(paid_member_jan1)
        # Capped at duration_days (30)
        assert service.get_days_used(today=date(2025, 1, 31)) == 30
    
    def test_days_used_after_35_days_expired(self, paid_member_jan1):
        """Test: Still 30 days used on Feb 5 (capped at duration)."""
        service = GymMembershipService(paid_member_jan1)
        # Capped at duration_days (30)
        assert service.get_days_used(today=date(2025, 2, 5)) == 30
    
    def test_days_used_before_start_date(self, paid_member_jan1):
        """Test: 0 days used before membership starts."""
        service = GymMembershipService(paid_member_jan1)
        # Dec 31, 2024 is before Jan 1, 2025
        assert service.get_days_used(today=date(2024, 12, 31)) == 0
    
    def test_days_used_no_membership(self, gym_member):
        """Test: 0 days used when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_days_used() == 0


class TestDaysLeft:
    """Test get_days_left method - CRITICAL for fixing '1/1 days' bug."""
    
    def test_days_left_on_payment_day(self, paid_member_jan1):
        """Test: Jan 1 payment = 30 days left on Jan 1."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 1, 1)) == 30
    
    def test_days_left_after_1_day(self, paid_member_jan1):
        """Test: 29 days left on Jan 2."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 1, 2)) == 29
    
    def test_days_left_after_5_days(self, paid_member_jan1):
        """Test: 25 days left on Jan 6 - fixes the '0 but expected 25' symptom."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 1, 6)) == 25
    
    def test_days_left_on_last_day(self, paid_member_jan1):
        """Test: 1 day left on Jan 30 (last day is inclusive)."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 1, 30)) == 1
    
    def test_days_left_first_expired_day(self, paid_member_jan1):
        """Test: 0 days left on Jan 31 (expired)."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 1, 31)) == 0
    
    def test_days_left_many_days_expired(self, paid_member_jan1):
        """Test: 0 days left on Feb 5 (still expired)."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_left(today=date(2025, 2, 5)) == 0
    
    def test_days_left_no_membership(self, gym_member):
        """Test: 0 days left when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_days_left() == 0
    
    def test_days_left_never_exceeds_duration(self, paid_member_jan1):
        """Test: days_left never exceeds 30 (prevents '31/30 days' bug)."""
        service = GymMembershipService(paid_member_jan1)
        
        # Test all days from payment day through 40 days later
        for days_offset in range(0, 41):
            test_date = date(2025, 1, 1) + timedelta(days=days_offset)
            days_left = service.get_days_left(today=test_date)
            
            # Must be between 0 and 30 (inclusive)
            assert 0 <= days_left <= 30, f"days_left={days_left} on {test_date} exceeds 30"


class TestDaysLeftCurrent:
    """Test get_days_left_current method (alias for backward compatibility)."""
    
    def test_days_left_current_equals_days_left(self, paid_member_jan1):
        """Test: days_left_current returns same as days_left."""
        service = GymMembershipService(paid_member_jan1)
        test_date = date(2025, 1, 6)
        
        assert service.get_days_left_current(today=test_date) == service.get_days_left(today=test_date)
        assert service.get_days_left_current(today=test_date) == 25


class TestNextPaymentDate:
    """Test get_next_payment_date method - CRITICAL for fixing 'blank next payment' bug."""
    
    def test_next_payment_date_30_day_membership(self, paid_member_jan1):
        """Test: Next payment is Jan 31 for Jan 1 payment."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_next_payment_date() == date(2025, 1, 31)
    
    def test_next_payment_date_no_payment(self, gym_member):
        """Test: Returns None when no payment exists."""
        service = GymMembershipService(gym_member)
        assert service.get_next_payment_date() is None
    
    def test_next_payment_date_end_of_month(self, gym_member):
        """Test: Correctly handles month boundaries."""
        # Payment on Jan 31
        gym_member.last_payment_date = date(2025, 1, 31)
        gym_member.membership_start = date(2025, 1, 31)
        gym_member.membership_end = date(2025, 3, 1)  # 30 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        # 30 days after Jan 31 = Mar 2
        assert service.get_next_payment_date() == date(2025, 3, 2)
    
    def test_next_payment_date_end_of_year(self, gym_member):
        """Test: Correctly handles year boundaries."""
        # Payment on Dec 15
        gym_member.last_payment_date = date(2024, 12, 15)
        gym_member.membership_start = date(2024, 12, 15)
        gym_member.membership_end = date(2025, 1, 13)  # 30 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        # 30 days after Dec 15 = Jan 14
        assert service.get_next_payment_date() == date(2025, 1, 14)
    
    def test_next_payment_date_custom_duration(self, gym_member):
        """Test: Works with non-standard duration."""
        # 60-day membership starting Jan 1
        gym_member.last_payment_date = date(2025, 1, 1)
        gym_member.membership_start = date(2025, 1, 1)
        gym_member.membership_end = date(2025, 3, 1)  # 60 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        # 60 days after Jan 1 = Mar 2
        assert service.get_next_payment_date() == date(2025, 3, 2)


class TestDaysDisplay:
    """Test get_days_display method - CRITICAL for fixing '1/1 days' display bug."""
    
    def test_days_display_on_payment_day(self, paid_member_jan1):
        """Test: Shows '30 / 30 days' on payment day - fixes '1/1 days' bug."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_display(today=date(2025, 1, 1)) == "30 / 30 days"
    
    def test_days_display_after_5_days(self, paid_member_jan1):
        """Test: Shows '25 / 30 days' after 5 days."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_display(today=date(2025, 1, 6)) == "25 / 30 days"
    
    def test_days_display_last_day(self, paid_member_jan1):
        """Test: Shows '1 / 30 days' on last day."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_display(today=date(2025, 1, 30)) == "1 / 30 days"
    
    def test_days_display_expired(self, paid_member_jan1):
        """Test: Shows '0 / 30 days' when expired."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_days_display(today=date(2025, 1, 31)) == "0 / 30 days"
    
    def test_days_display_no_membership(self, gym_member):
        """Test: Shows '0 / 30 days' with no membership."""
        service = GymMembershipService(gym_member)
        assert service.get_days_display() == "0 / 30 days"


class TestIsActive:
    """Test is_active method."""
    
    def test_is_active_on_payment_day(self, paid_member_jan1):
        """Test: Member is active on payment day."""
        service = GymMembershipService(paid_member_jan1)
        assert service.is_active(today=date(2025, 1, 1)) is True
    
    def test_is_active_during_period(self, paid_member_jan1):
        """Test: Member is active during membership period."""
        service = GymMembershipService(paid_member_jan1)
        assert service.is_active(today=date(2025, 1, 15)) is True
    
    def test_is_active_last_day(self, paid_member_jan1):
        """Test: Member is active on last day."""
        service = GymMembershipService(paid_member_jan1)
        assert service.is_active(today=date(2025, 1, 30)) is True
    
    def test_is_active_expired(self, paid_member_jan1):
        """Test: Member is not active when expired."""
        service = GymMembershipService(paid_member_jan1)
        assert service.is_active(today=date(2025, 1, 31)) is False
    
    def test_is_active_no_payment(self, gym_member):
        """Test: Member is not active with no payment."""
        service = GymMembershipService(gym_member)
        assert service.is_active() is False


class TestStatusCode:
    """Test get_status_code method."""
    
    def test_status_code_no_membership(self, gym_member):
        """Test: Returns 'none' when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_status_code() == "none"
    
    def test_status_code_active(self, paid_member_jan1):
        """Test: Returns 'active' during membership period."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_status_code(today=date(2025, 1, 15)) == "active"
    
    def test_status_code_expired(self, paid_member_jan1):
        """Test: Returns 'expired' after membership ends."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_status_code(today=date(2025, 1, 31)) == "expired"


class TestStatusLabel:
    """Test get_status_label method."""
    
    def test_status_label_no_membership(self, gym_member):
        """Test: Returns 'No membership' when no membership exists."""
        service = GymMembershipService(gym_member)
        assert service.get_status_label() == "No membership"
    
    def test_status_label_active(self, paid_member_jan1):
        """Test: Returns 'Active' during membership period."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_status_label(today=date(2025, 1, 15)) == "Active"
    
    def test_status_label_expired(self, paid_member_jan1):
        """Test: Returns 'Expired' after membership ends."""
        service = GymMembershipService(paid_member_jan1)
        assert service.get_status_label(today=date(2025, 1, 31)) == "Expired"


class TestGetMembershipStatus:
    """Test get_membership_status method - the main SSOT API."""
    
    def test_membership_status_complete_data_payment_day(self, paid_member_jan1):
        """Test: Returns complete status dict on payment day."""
        service = GymMembershipService(paid_member_jan1)
        status = service.get_membership_status(today=date(2025, 1, 1))
        
        # Status indicators
        assert status["status_code"] == "active"
        assert status["status_label"] == "Active"
        assert status["is_active"] is True
        
        # Period dates
        assert status["membership_start"] == date(2025, 1, 1)
        assert status["membership_end"] == date(2025, 1, 30)
        
        # Day calculations
        assert status["total_days"] == 30
        assert status["days_used"] == 0
        assert status["days_left"] == 30
        assert status["days_left_current"] == 30
        
        # Display
        assert status["days_display"] == "30 / 30 days"
        
        # Payment info
        assert status["last_payment_date"] == date(2025, 1, 1)
        assert status["next_payment_date"] == date(2025, 1, 31)
    
    def test_membership_status_after_5_days(self, paid_member_jan1):
        """Test: Returns correct status after 5 days."""
        service = GymMembershipService(paid_member_jan1)
        status = service.get_membership_status(today=date(2025, 1, 6))
        
        assert status["status_code"] == "active"
        assert status["status_label"] == "Active"
        assert status["is_active"] is True
        
        assert status["total_days"] == 30
        assert status["days_used"] == 5
        assert status["days_left"] == 25
        assert status["days_display"] == "25 / 30 days"
    
    def test_membership_status_expired(self, paid_member_jan1):
        """Test: Returns correct status when expired."""
        service = GymMembershipService(paid_member_jan1)
        status = service.get_membership_status(today=date(2025, 1, 31))
        
        assert status["status_code"] == "expired"
        assert status["status_label"] == "Expired"
        assert status["is_active"] is False
        
        assert status["total_days"] == 30
        assert status["days_used"] == 30  # Capped
        assert status["days_left"] == 0
        assert status["days_display"] == "0 / 30 days"
    
    def test_membership_status_no_membership(self, gym_member):
        """Test: Returns correct status with no membership."""
        service = GymMembershipService(gym_member)
        status = service.get_membership_status()
        
        assert status["status_code"] == "none"
        assert status["status_label"] == "No membership"
        assert status["is_active"] is False
        
        assert status["membership_start"] is None
        assert status["membership_end"] is None
        
        assert status["total_days"] == 30  # Default
        assert status["days_used"] == 0
        assert status["days_left"] == 0
        assert status["days_display"] == "0 / 30 days"
        
        assert status["last_payment_date"] is None
        assert status["next_payment_date"] is None


class TestModelIntegration:
    """Test that GymMember model properties use the SSOT service correctly."""
    
    def test_model_days_used_property(self, paid_member_today):
        """Test: Model days_used property uses SSOT service."""
        # The model should delegate to the service
        # On payment day (today), days_used should be 0
        assert paid_member_today.days_used == 0
    
    def test_model_days_left_property(self, paid_member_today):
        """Test: Model days_left property uses SSOT service."""
        # The model should delegate to the service
        # On payment day (today), days_left should be 30
        assert paid_member_today.days_left == 30
    
    def test_model_days_left_current_property(self, paid_member_today):
        """Test: Model days_left_current property uses SSOT service."""
        # The model should delegate to the service
        # On payment day (today), days_left_current should be 30
        assert paid_member_today.days_left_current == 30
    
    def test_model_days_left_display_property(self, paid_member_today):
        """Test: Model days_left_display property uses SSOT service."""
        # The model should delegate to the service
        assert paid_member_today.days_left_display == "30 / 30 days"
    
    def test_model_next_payment_date_property(self, paid_member_today):
        """Test: Model next_payment_date_property uses SSOT service."""
        # The model should delegate to the service
        today = timezone.now().date()
        expected_next_payment = today + timedelta(days=30)
        assert paid_member_today.next_payment_date_property == expected_next_payment
    
    def test_model_is_active_membership_property(self, paid_member_today):
        """Test: Model is_active_membership property uses SSOT service."""
        # The model should delegate to the service
        assert paid_member_today.is_active_membership is True
    
    def test_model_status_label_property(self, paid_member_today):
        """Test: Model status_label property uses SSOT service."""
        # The model should delegate to the service
        assert paid_member_today.status_label == "Active"
    
    def test_model_get_status_method(self, paid_member_today):
        """Test: Model get_status() method uses SSOT service."""
        status = paid_member_today.get_status()
        
        assert status["status_code"] == "active"
        assert status["days_left"] == 30
        
        today = timezone.now().date()
        expected_next_payment = today + timedelta(days=30)
        assert status["next_payment_date"] == expected_next_payment


class TestRegressionScenarios:
    """Test specific scenarios that were broken before the fix."""
    
    def test_symptom_days_left_current_zero_but_expected_25(self, paid_member_jan1):
        """
        Test: Fix symptom 'days_left_current = 0 but expected 25'.
        
        This happened when member paid 5 days ago but days_left_current returned 0.
        """
        # Simulate 5 days after payment
        service = GymMembershipService(paid_member_jan1)
        days_left = service.get_days_left_current(today=date(2025, 1, 6))
        
        # Should be 25, not 0
        assert days_left == 25
        
        # Also check via model property
        # Note: We can't easily mock timezone.now() for the model property,
        # but we verified the service works correctly
    
    def test_symptom_display_1_1_days_instead_of_30_30(self, paid_member_jan1):
        """
        Test: Fix symptom 'display shows 1/1 days instead of 30/30 days'.
        
        This happened on payment day due to incorrect calculation.
        """
        service = GymMembershipService(paid_member_jan1)
        display = service.get_days_display(today=date(2025, 1, 1))
        
        # Should be "30 / 30 days", not "1 / 1 days"
        assert display == "30 / 30 days"
    
    def test_symptom_next_payment_date_blank(self, paid_member_jan1):
        """
        Test: Fix symptom 'next_payment_date incorrect/blank'.
        
        This happened when next_payment_date was None despite having a payment.
        """
        service = GymMembershipService(paid_member_jan1)
        next_payment = service.get_next_payment_date()
        
        # Should be Jan 31, not None
        assert next_payment is not None
        assert next_payment == date(2025, 1, 31)
    
    def test_30_day_membership_starting_jan1_ends_jan30(self, paid_member_jan1):
        """
        Test: A 30-day membership starting Jan 1 has end Jan 30.
        
        This is from the user's requirement.
        """
        # Verify the membership end date is correct
        assert paid_member_jan1.membership_start == date(2025, 1, 1)
        assert paid_member_jan1.membership_end == date(2025, 1, 30)
        
        service = GymMembershipService(paid_member_jan1)
        
        # Verify the duration is 30 days
        assert service.get_duration_days() == 30
        
        # Verify days_left on Jan 1 is 30
        assert service.get_days_left(today=date(2025, 1, 1)) == 30
    
    def test_next_payment_date_matches_end_date_plus_one(self, paid_member_jan1):
        """
        Test: next_payment_date matches end date + 1.
        
        From user's requirement: next_payment_date should match the day after end date.
        """
        service = GymMembershipService(paid_member_jan1)
        
        # Membership ends Jan 30
        assert paid_member_jan1.membership_end == date(2025, 1, 30)
        
        # Next payment should be Jan 31
        assert service.get_next_payment_date() == date(2025, 1, 31)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_leap_year_february(self, gym_member):
        """Test: Correctly handles leap year February."""
        # Payment on Feb 1 of leap year 2024
        gym_member.last_payment_date = date(2024, 2, 1)
        gym_member.membership_start = date(2024, 2, 1)
        gym_member.membership_end = date(2024, 3, 1)  # 30 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        
        # Should have 30 days
        assert service.get_duration_days() == 30
        
        # Next payment should be Mar 2 (30 days after Feb 1)
        assert service.get_next_payment_date() == date(2024, 3, 2)
    
    def test_non_leap_year_february(self, gym_member):
        """Test: Correctly handles non-leap year February."""
        # Payment on Feb 1 of non-leap year 2025
        gym_member.last_payment_date = date(2025, 2, 1)
        gym_member.membership_start = date(2025, 2, 1)
        gym_member.membership_end = date(2025, 3, 2)  # 30 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        
        # Should have 30 days
        assert service.get_duration_days() == 30
        
        # Next payment should be Mar 3 (30 days after Feb 1)
        assert service.get_next_payment_date() == date(2025, 3, 3)
    
    def test_year_boundary_december_to_january(self, gym_member):
        """Test: Correctly handles year boundary."""
        # Payment on Dec 20, 2024
        gym_member.last_payment_date = date(2024, 12, 20)
        gym_member.membership_start = date(2024, 12, 20)
        gym_member.membership_end = date(2025, 1, 18)  # 30 days later
        gym_member.save()
        
        service = GymMembershipService(gym_member)
        
        # Should have 30 days
        assert service.get_duration_days() == 30
        
        # Days left on Jan 1, 2025 should be correct
        assert service.get_days_left(today=date(2025, 1, 1)) == 18
        
        # Next payment should be Jan 19 (30 days after Dec 20)
        assert service.get_next_payment_date() == date(2025, 1, 19)

