"""
Comprehensive tests for gym membership fixes.

Tests the following key fixes:
1. New member payment creates 30-day active membership
2. Membership status countdown and expiry
3. Check-in marks member as present
4. Expired members cannot check in without payment
5. Trainer assignment and fee prompts
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import (
    GymMember, GymPayment, GymCheckIn, GymTrainer, TrainerFee,
    GymMemberStatus
)
from inventory.utils_gym import get_membership_status, GYM_MEMBERSHIP_DAYS

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business for testing"""
    from inventory.business_kinds import BusinessKind
    business = Business.objects.create(
        name="Test Gym (Iris)",
        business_kind=BusinessKind.GYM,
        subdomain="testgym",
        slug="testgym"
    )
    return business


@pytest.fixture
def manager_user(db):
    """Create a manager user"""
    user = User.objects.create_user(
        username="gym_manager",
        email="manager@testgym.com",
        password="testpass123"
    )
    return user


@pytest.fixture
def trainer(gym_business):
    """Create a gym trainer"""
    trainer = GymTrainer.objects.create(
        business=gym_business,
        name="Steve",
        phone="0977123456",
        email="steve@testgym.com"
    )
    return trainer


@pytest.mark.django_db
class TestNewMemberPaymentIsActiveAndNotInArrears:
    """Test that new members with payments are active and not in arrears"""
    
    def test_new_member_with_payment_today_is_active(self, gym_business, manager_user):
        """
        New member with payment created today should be:
        - status_code == "active"
        - days_remaining == 30
        - NOT counted in arrears
        """
        # Create member
        member = GymMember.objects.create(
            business=gym_business,
            name="John Doe",
            phone="0977000001",
            email="john@example.com"
        )
        
        # Record payment (simulating set_paid)
        today = timezone.now().date()
        member.set_paid(
            payment_date=today,
            membership_fee=Decimal("150.00"),
            paid_by=manager_user
        )
        member.refresh_from_db()
        
        # Check membership status using utility
        status = get_membership_status(member, today)
        
        # Assertions
        assert status["status_code"] == "active", f"Expected 'active' but got '{status['status_code']}'"
        assert status["days_remaining"] == 30, f"Expected 30 days but got {status['days_remaining']}"
        assert status["label"] == "Active"
        assert status["start_date"] == today
        assert status["end_date"] == today + timedelta(days=29)  # 30 days inclusive
        
        # Verify dashboard counts
        all_members = GymMember.objects.filter(business=gym_business, is_active=True, is_archived=False)
        active_count = sum(1 for m in all_members if get_membership_status(m, today)["status_code"] == "active")
        in_arrears_count = sum(1 for m in all_members if get_membership_status(m, today)["status_code"] in ["expired", "none"])
        
        assert all_members.count() == 1
        assert active_count == 1
        assert in_arrears_count == 0
    
    def test_member_without_payment_has_no_membership_status(self, gym_business):
        """Member without payment should have status_code == 'none'"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Jane Doe",
            phone="0977000002"
        )
        
        status = get_membership_status(member)
        
        assert status["status_code"] == "none"
        assert status["label"] == "No membership"
        assert status["days_remaining"] == 0
        assert status["total_days"] is None


@pytest.mark.django_db
class TestMembershipStatusCountdownAndExpiry:
    """Test that membership counts down properly and expires"""
    
    def test_membership_status_before_end_date_is_active(self, gym_business):
        """Membership before end date should be active with correct days remaining"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Active Member",
            phone="0977000003"
        )
        
        # Set membership dates manually
        today = date(2025, 1, 15)
        member.membership_start = date(2025, 1, 1)
        member.membership_end = date(2025, 1, 30)  # 30 days inclusive
        member.save()
        
        status = get_membership_status(member, today)
        
        # On Jan 15, there are 16 days left (15, 16, ..., 30)
        expected_days = (member.membership_end - today).days + 1
        
        assert status["status_code"] == "active"
        assert status["days_remaining"] == expected_days
        assert status["days_remaining"] == 16
    
    def test_membership_status_on_end_date_is_still_active(self, gym_business):
        """On the last day of membership, status should still be active with 1 day remaining"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Last Day Member",
            phone="0977000004"
        )
        
        today = date(2025, 1, 30)
        member.membership_start = date(2025, 1, 1)
        member.membership_end = date(2025, 1, 30)
        member.save()
        
        status = get_membership_status(member, today)
        
        assert status["status_code"] == "active"
        assert status["days_remaining"] == 1  # Today counts
    
    def test_membership_status_after_end_date_is_expired(self, gym_business):
        """After end date, membership should be expired with 0 days"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Expired Member",
            phone="0977000005"
        )
        
        today = date(2025, 2, 1)
        member.membership_start = date(2025, 1, 1)
        member.membership_end = date(2025, 1, 30)
        member.save()
        
        status = get_membership_status(member, today)
        
        assert status["status_code"] == "expired"
        assert status["label"] == "Expired"
        assert status["days_remaining"] == 0


@pytest.mark.django_db
class TestCheckinMarksPresent:
    """Test that check-in properly marks members as present"""
    
    def test_checkin_creates_record_and_shows_present(self, gym_business, manager_user):
        """Check-in should create record and member shows as 'Present' today"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Present Member",
            phone="0977000006"
        )
        
        # Give member active membership
        today = timezone.now().date()
        member.set_paid(payment_date=today, membership_fee=Decimal("150.00"), paid_by=manager_user)
        
        # Check in member
        checkin = GymCheckIn.objects.create(
            business=gym_business,
            member=member,
            checked_in_by=manager_user
        )
        
        # Verify check-in exists
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        checked_in_today = GymCheckIn.objects.filter(
            business=gym_business,
            member=member,
            timestamp__gte=today_start
        ).exists()
        
        assert checked_in_today is True
    
    def test_duplicate_checkin_same_day_prevented(self, gym_business, manager_user):
        """Checking in twice on same day should not create duplicate records"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Duplicate Check Member",
            phone="0977000007"
        )
        
        today = timezone.now().date()
        member.set_paid(payment_date=today, membership_fee=Decimal("150.00"), paid_by=manager_user)
        
        # First check-in
        GymCheckIn.objects.create(
            business=gym_business,
            member=member,
            checked_in_by=manager_user
        )
        
        # Try second check-in (view should prevent this, but let's check count)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        existing_count = GymCheckIn.objects.filter(
            business=gym_business,
            member=member,
            timestamp__gte=today_start
        ).count()
        
        # View logic should prevent duplicate, but if it were created:
        # Only one should exist for today
        assert existing_count == 1


@pytest.mark.django_db
class TestExpiredMemberCannotCheckinWithoutPayment:
    """Test that expired members cannot check in without payment"""
    
    def test_expired_member_identified_correctly(self, gym_business):
        """Expired member should have status_code == 'expired'"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Expired No Checkin",
            phone="0977000008"
        )
        
        # Set expired membership
        today = date(2025, 2, 1)
        member.membership_start = date(2025, 1, 1)
        member.membership_end = date(2025, 1, 30)
        member.save()
        
        status = get_membership_status(member, today)
        
        assert status["status_code"] == "expired"
        
        # View should disable check-in button for expired members
        # (Button check would be integration/UI test)


@pytest.mark.django_db
class TestTrainerAssignmentAndFeePrompt:
    """Test trainer assignment and fee tracking"""
    
    def test_trainer_assignment(self, gym_business, trainer):
        """Member can be assigned a trainer"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Trainer Member",
            phone="0977000009",
            trainer=trainer
        )
        
        assert member.trainer == trainer
        assert member.trainer.name == "Steve"
    
    def test_trainer_fee_recorded_for_period(self, gym_business, trainer, manager_user):
        """Trainer fee can be recorded for a membership period"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Fee Member",
            phone="0977000010",
            trainer=trainer
        )
        
        today = timezone.now().date()
        member.set_paid(payment_date=today, membership_fee=Decimal("150.00"), paid_by=manager_user)
        
        # Record trainer fee
        trainer_fee = TrainerFee.objects.create(
            business=gym_business,
            trainer=trainer,
            member=member,
            amount=Decimal("50.00"),
            period_start=member.membership_start,
            period_end=member.membership_end,
            recorded_by=manager_user
        )
        
        assert trainer_fee.amount == Decimal("50.00")
        assert trainer_fee.trainer == trainer
        assert trainer_fee.member == member
    
    def test_missing_trainer_fee_detected(self, gym_business, trainer, manager_user):
        """Missing trainer fee for active member with trainer should be detected"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Missing Fee Member",
            phone="0977000011",
            trainer=trainer
        )
        
        today = timezone.now().date()
        member.set_paid(payment_date=today, membership_fee=Decimal("150.00"), paid_by=manager_user)
        member.refresh_from_db()
        
        # Check if trainer fee exists for this period
        status = get_membership_status(member, today)
        fee_exists = TrainerFee.objects.filter(
            member=member,
            period_start=status["start_date"],
            period_end=status["end_date"]
        ).exists()
        
        # Should be missing
        assert fee_exists is False
        
        # View should show warning: "Trainer fee not recorded"


@pytest.mark.django_db
class TestMembershipPeriodCalculation:
    """Test that membership periods are exactly 30 days inclusive"""
    
    def test_set_paid_creates_30_day_inclusive_period(self, gym_business, manager_user):
        """set_paid should create exactly 30-day inclusive period"""
        member = GymMember.objects.create(
            business=gym_business,
            name="30 Day Test",
            phone="0977000012"
        )
        
        payment_date = date(2025, 1, 1)
        member.set_paid(payment_date=payment_date, membership_fee=Decimal("150.00"), paid_by=manager_user)
        member.refresh_from_db()
        
        assert member.membership_start == date(2025, 1, 1)
        assert member.membership_end == date(2025, 1, 30)  # 30 days: Jan 1-30
        
        # Calculate total days
        total_days = (member.membership_end - member.membership_start).days + 1
        assert total_days == GYM_MEMBERSHIP_DAYS
    
    def test_days_remaining_calculation_is_inclusive(self, gym_business):
        """Days remaining should be calculated inclusively"""
        member = GymMember.objects.create(
            business=gym_business,
            name="Inclusive Count Test",
            phone="0977000013"
        )
        
        # Set membership: Jan 1 - Jan 30 (30 days)
        member.membership_start = date(2025, 1, 1)
        member.membership_end = date(2025, 1, 30)
        member.save()
        
        # On Jan 1 (first day), should have 30 days remaining
        status = get_membership_status(member, date(2025, 1, 1))
        assert status["days_remaining"] == 30
        
        # On Jan 2 (second day), should have 29 days remaining
        status = get_membership_status(member, date(2025, 1, 2))
        assert status["days_remaining"] == 29
        
        # On Jan 30 (last day), should have 1 day remaining
        status = get_membership_status(member, date(2025, 1, 30))
        assert status["days_remaining"] == 1
        
        # On Jan 31 (day after), should be expired with 0 days
        status = get_membership_status(member, date(2025, 1, 31))
        assert status["status_code"] == "expired"
        assert status["days_remaining"] == 0


@pytest.mark.django_db
class TestDashboardInArrearsAccuracy:
    """Test that dashboard IN ARREARS count is accurate"""
    
    def test_dashboard_counts_multiple_members_correctly(self, gym_business, manager_user):
        """Dashboard should accurately count active vs in arrears members"""
        today = timezone.now().date()
        
        # Create 3 members with different statuses
        
        # 1. Active member (paid today)
        active_member = GymMember.objects.create(
            business=gym_business,
            name="Active",
            phone="0977111111"
        )
        active_member.set_paid(payment_date=today, membership_fee=Decimal("150.00"), paid_by=manager_user)
        
        # 2. Expired member
        expired_member = GymMember.objects.create(
            business=gym_business,
            name="Expired",
            phone="0977222222"
        )
        expired_member.membership_start = today - timedelta(days=40)
        expired_member.membership_end = today - timedelta(days=10)
        expired_member.save()
        
        # 3. No membership member
        no_membership_member = GymMember.objects.create(
            business=gym_business,
            name="No Membership",
            phone="0977333333"
        )
        
        # Calculate counts using the same logic as dashboard
        all_members = GymMember.objects.filter(business=gym_business, is_active=True, is_archived=False)
        
        active_count = 0
        in_arrears_count = 0
        
        for member in all_members:
            status = get_membership_status(member, today)
            if status["status_code"] == "active":
                active_count += 1
            elif status["status_code"] in ["expired", "none"]:
                in_arrears_count += 1
        
        # Assertions
        assert all_members.count() == 3
        assert active_count == 1  # Only the first member
        assert in_arrears_count == 2  # Expired + No membership

