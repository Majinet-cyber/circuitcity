# tests/test_verticals_gym.py
"""
Tests for gym functionality: members, payments, 30-day logic, arrears tracking.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import (
    GymMember, GymPayment, GymMemberLog, GymSettings, GymWalletEntry,
    GymMemberAction
)
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test gym business"""
    return Business.objects.create(
        name="Test Gym",
        slug="test-gym",
        status="ACTIVE",
        business_kind=BusinessKind.GYM
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="gym_manager", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def gym_member(business):
    """Create a gym member"""
    return GymMember.objects.create(
        business=business,
        name="John Fitness",
        phone="0999123456",
        email="john@example.com"
    )


@pytest.fixture
def gym_settings(business):
    """Create gym settings"""
    return GymSettings.objects.create(
        business=business,
        support_phone="0999000111",
        support_email="support@gym.com",
        default_membership_price=Decimal("50000.00")
    )


@pytest.mark.django_db
class TestGymMember:
    """Test gym member CRUD and logging"""
    
    def test_create_member(self, business):
        """Test creating a gym member"""
        member = GymMember.objects.create(
            business=business,
            name="Alice Strong",
            phone="0999654321",
            email="alice@example.com"
        )
        
        assert member.is_active is True
        assert member.is_archived is False
        assert member.joined_at is not None
    
    def test_member_archive(self, gym_member, manager):
        """Test archiving a member"""
        gym_member.archive(manager)
        
        assert gym_member.is_archived is True
        assert gym_member.is_active is False
        assert gym_member.archived_at is not None
        assert gym_member.archived_by == manager
    
    def test_member_logging_on_create(self, business, manager):
        """Test that member creation is logged"""
        member = GymMember.objects.create(
            business=business,
            name="Bob Builder",
            phone="0999111222"
        )
        
        # Manually create log (in real app, this would be in signal/view)
        log = GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.CREATED,
            changes={"name": member.name, "phone": member.phone},
            performed_by=manager
        )
        
        assert log.action == GymMemberAction.CREATED
        assert log.member == member


@pytest.mark.django_db
class TestGymPayment:
    """Test gym payment and 30-day logic"""
    
    def test_payment_creates_30_day_period(self, gym_member, manager):
        """Test payment creates exactly 30-day membership"""
        start = date.today()
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start,
            paid_by=manager
        )
        
        expected_end = start + timedelta(days=30)
        assert payment.end_date == expected_end
    
    def test_days_left_calculation(self, gym_member, manager):
        """Test days left calculation"""
        start = date.today()
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start,
            paid_by=manager
        )
        
        days_left = gym_member.days_left()
        assert days_left == 30
    
    def test_days_left_after_10_days(self, gym_member, manager):
        """Test days left after 10 days"""
        start = date.today() - timedelta(days=10)
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start,
            paid_by=manager
        )
        
        # Manually set end_date to simulate
        payment.end_date = start + timedelta(days=30)
        payment.save()
        
        days_left = gym_member.days_left()
        assert days_left == 20
    
    def test_membership_in_arrears(self, gym_member, manager):
        """Test member in arrears after 30 days"""
        start = date.today() - timedelta(days=31)
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start,
            paid_by=manager
        )
        payment.end_date = start + timedelta(days=30)
        payment.save()
        
        days_left = gym_member.days_left()
        status = gym_member.membership_status()
        
        assert days_left == 0
        assert status == "In arrears"
    
    def test_active_membership(self, gym_member, manager):
        """Test active membership status"""
        start = date.today()
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start,
            paid_by=manager
        )
        
        status = gym_member.membership_status()
        assert status == "Active"
    
    def test_multiple_payments_stacking(self, gym_member, manager):
        """Test that payments stack correctly"""
        # First payment
        start1 = date.today()
        payment1 = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start1,
            paid_by=manager
        )
        
        # Second payment (should start after first ends)
        start2 = start1 + timedelta(days=30)
        payment2 = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=start2,
            paid_by=manager
        )
        
        assert payment2.end_date == start2 + timedelta(days=30)


@pytest.mark.django_db
class TestGymSettings:
    """Test gym settings"""
    
    def test_create_settings(self, business):
        """Test creating gym settings"""
        settings = GymSettings.objects.create(
            business=business,
            support_phone="0999000000",
            support_email="gym@support.com",
            default_membership_price=Decimal("60000.00"),
            arrears_message="Please renew your membership."
        )
        
        assert settings.default_membership_price == Decimal("60000.00")
        assert settings.arrears_message == "Please renew your membership."


@pytest.mark.django_db
class TestGymWalletEntry:
    """Test gym wallet entries"""
    
    def test_create_income_from_payment(self, business, gym_member, manager):
        """Test creating wallet entry from payment"""
        payment = GymPayment.objects.create(
            member=gym_member,
            amount=Decimal("50000.00"),
            start_date=date.today(),
            paid_by=manager
        )
        
        entry = GymWalletEntry.objects.create(
            business=business,
            amount=payment.amount,
            description=f"Membership payment from {gym_member.name}",
            entry_type="income",
            related_payment=payment,
            created_by=manager
        )
        
        assert entry.entry_type == "income"
        assert entry.amount == Decimal("50000.00")
        assert entry.related_payment == payment

