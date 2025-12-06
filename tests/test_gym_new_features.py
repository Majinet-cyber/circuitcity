# tests/test_gym_new_features.py
"""
Tests for NEW gym features (GOAL 1-3):
- 30-day membership logic with set_paid method
- Payment status buckets (Pending, Active, Behind Schedule)
- Check-ins and conversion metrics
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import (
    GymMember, GymPayment, GymSettings, GymCheckIn, GymMemberStatus
)
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def business():
    """Create a test gym business"""
    return Business.objects.create(
        name="Test Fitness Center",
        slug="test-fitness",
        status="ACTIVE",
        business_kind=BusinessKind.GYM
    )


@pytest.fixture
def manager(business):
    """Create a manager user with membership"""
    user = User.objects.create_user(username="gym_manager", password="testpass123")
    user.is_staff = False
    user.save()
    
    # Create profile if necessary
    if hasattr(user, 'profile'):
        user.profile.is_manager = True
        user.profile.save()
    
    return user


@pytest.fixture
def gym_settings(business):
    """Create gym settings with fees"""
    return GymSettings.objects.create(
        business=business,
        support_phone="0999123456",
        support_email="support@testfitness.com",
        default_membership_price=Decimal("50000.00"),
        default_trainer_fee=Decimal("30000.00")
    )


@pytest.mark.django_db
class TestThirtyDayMembershipLogic:
    """GOAL 1: Test 30-day membership logic with trainer fees"""
    
    def test_set_paid_creates_30_day_period(self, business, manager, gym_settings):
        """Test set_paid method creates exactly 30-day membership"""
        # Create member not yet paid
        member = GymMember.objects.create(
            business=business,
            name="Alice Strong",
            phone="0999111222",
            has_trainer=False
        )
        
        # Initially should be pending payment
        assert member.status == GymMemberStatus.PENDING_PAYMENT
        assert member.membership_start is None
        assert member.membership_end is None
        
        # Set as paid
        payment_date = date.today()
        member.set_paid(
            payment_date=payment_date,
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Verify 30-day period
        assert member.status == GymMemberStatus.ACTIVE
        assert member.membership_start == payment_date
        assert member.membership_end == payment_date + timedelta(days=30)
        assert member.last_payment_date == payment_date
        
        # Verify payment record was created
        payment = GymPayment.objects.filter(member=member).first()
        assert payment is not None
        assert payment.amount == gym_settings.default_membership_price
        assert payment.start_date == payment_date
        assert payment.end_date == payment_date + timedelta(days=30)
    
    def test_set_paid_with_trainer_adds_trainer_fee(self, business, manager, gym_settings):
        """Test set_paid with trainer includes trainer fee"""
        member = GymMember.objects.create(
            business=business,
            name="Bob Lifter",
            phone="0999222333",
            has_trainer=True
        )
        
        # Set as paid with trainer
        member.set_paid(
            payment_date=None,  # Today
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=gym_settings.default_trainer_fee,
            paid_by=manager
        )
        
        # Verify total amount includes both fees
        payment = GymPayment.objects.filter(member=member).first()
        expected_total = gym_settings.default_membership_price + gym_settings.default_trainer_fee
        assert payment.amount == expected_total
        assert payment.notes.lower() == "with trainer"
    
    def test_set_paid_without_trainer(self, business, manager, gym_settings):
        """Test set_paid without trainer uses only membership fee"""
        member = GymMember.objects.create(
            business=business,
            name="Charlie Runner",
            phone="0999333444",
            has_trainer=False
        )
        
        member.set_paid(
            payment_date=None,
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        payment = GymPayment.objects.filter(member=member).first()
        assert payment.amount == gym_settings.default_membership_price
        assert "no trainer" in payment.notes.lower()
    
    def test_renewal_extends_from_payment_date(self, business, manager, gym_settings):
        """Test renewal extends membership for another 30 days"""
        member = GymMember.objects.create(
            business=business,
            name="Diana Athlete",
            phone="0999444555",
            has_trainer=False
        )
        
        # First payment
        first_payment_date = date.today() - timedelta(days=35)
        member.set_paid(
            payment_date=first_payment_date,
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Member should be expired
        assert member.membership_end < date.today()
        
        # Renew
        renewal_date = date.today()
        member.set_paid(
            payment_date=renewal_date,
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Should have new 30-day period from renewal date
        assert member.membership_start == renewal_date
        assert member.membership_end == renewal_date + timedelta(days=30)
        assert member.status == GymMemberStatus.ACTIVE
        
        # Should have 2 payment records
        assert GymPayment.objects.filter(member=member).count() == 2


@pytest.mark.django_db
class TestPaymentStatusBuckets:
    """GOAL 2: Test payment status buckets (Pending, Active, Behind Schedule)"""
    
    def test_new_member_starts_pending(self, business):
        """Test new member without payment is PENDING_PAYMENT"""
        member = GymMember.objects.create(
            business=business,
            name="Eve Newbie",
            phone="0999555666"
        )
        
        assert member.status == GymMemberStatus.PENDING_PAYMENT
        assert member.membership_start is None
        assert member.membership_end is None
    
    def test_paid_member_is_active(self, business, manager, gym_settings):
        """Test paid member within 30-day window is ACTIVE"""
        member = GymMember.objects.create(
            business=business,
            name="Frank Active",
            phone="0999666777"
        )
        
        member.set_paid(
            payment_date=date.today(),
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        assert member.status == GymMemberStatus.ACTIVE
        assert member.days_left() >= 30
    
    def test_expired_member_is_behind_schedule(self, business, manager, gym_settings):
        """Test member past membership_end is BEHIND_SCHEDULE"""
        member = GymMember.objects.create(
            business=business,
            name="Grace Expired",
            phone="0999777888"
        )
        
        # Set paid 35 days ago (past 30-day window)
        old_payment_date = date.today() - timedelta(days=35)
        member.set_paid(
            payment_date=old_payment_date,
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Manually update status (in real app, dashboard does this)
        member.update_status()
        
        assert member.status == GymMemberStatus.BEHIND_SCHEDULE
        assert member.days_left() == 0
    
    def test_dashboard_buckets_query(self, business, manager, gym_settings):
        """Test dashboard can query all three buckets correctly"""
        # Create pending member
        pending = GymMember.objects.create(
            business=business,
            name="Pending Member",
            phone="0999111111"
        )
        
        # Create active member
        active = GymMember.objects.create(
            business=business,
            name="Active Member",
            phone="0999222222"
        )
        active.set_paid(
            payment_date=date.today(),
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Create behind schedule member
        behind = GymMember.objects.create(
            business=business,
            name="Behind Member",
            phone="0999333333"
        )
        behind.set_paid(
            payment_date=date.today() - timedelta(days=35),
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        behind.update_status()
        
        # Query buckets
        all_members = GymMember.objects.filter(business=business, is_archived=False)
        pending_members = all_members.filter(status=GymMemberStatus.PENDING_PAYMENT)
        active_members = all_members.filter(status=GymMemberStatus.ACTIVE)
        behind_members = all_members.filter(status=GymMemberStatus.BEHIND_SCHEDULE)
        
        assert pending_members.count() == 1
        assert active_members.count() == 1
        assert behind_members.count() == 1
        assert all_members.count() == 3


@pytest.mark.django_db
class TestCheckInsAndConversion:
    """GOAL 3: Test check-ins and conversion metrics"""
    
    def test_create_checkin(self, business, manager, gym_settings):
        """Test creating a check-in record"""
        member = GymMember.objects.create(
            business=business,
            name="Henry Gym",
            phone="0999888999"
        )
        member.set_paid(
            payment_date=date.today(),
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Create check-in
        checkin = GymCheckIn.objects.create(
            business=business,
            member=member,
            checked_in_by=manager,
            notes="Regular morning workout"
        )
        
        assert checkin.member == member
        assert checkin.business == business
        assert checkin.checked_in_by == manager
        assert checkin.timestamp is not None
    
    def test_conversion_percentage_all_paid(self, business, manager, gym_settings):
        """Test conversion percentage when all check-ins are from paid members"""
        # Create 3 paid members
        for i in range(3):
            member = GymMember.objects.create(
                business=business,
                name=f"Member {i}",
                phone=f"099900{i}00{i}"
            )
            member.set_paid(
                payment_date=date.today(),
                membership_fee=gym_settings.default_membership_price,
                trainer_fee=Decimal("0.00"),
                paid_by=manager
            )
            
            # Check in each member
            GymCheckIn.objects.create(
                business=business,
                member=member,
                checked_in_by=manager
            )
        
        # Calculate conversion
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_checkins = GymCheckIn.objects.filter(
            business=business,
            timestamp__gte=today_start
        ).select_related("member")
        
        paid_checkins = sum(1 for c in today_checkins if c.member.status == GymMemberStatus.ACTIVE)
        total_checkins = today_checkins.count()
        
        assert total_checkins == 3
        assert paid_checkins == 3
        conversion_percentage = (paid_checkins / total_checkins) * 100
        assert conversion_percentage == 100.0
    
    def test_conversion_percentage_mixed(self, business, manager, gym_settings):
        """Test conversion percentage with mix of paid and unpaid members"""
        # Create 2 paid members
        for i in range(2):
            member = GymMember.objects.create(
                business=business,
                name=f"Paid Member {i}",
                phone=f"099911{i}11{i}"
            )
            member.set_paid(
                payment_date=date.today(),
                membership_fee=gym_settings.default_membership_price,
                trainer_fee=Decimal("0.00"),
                paid_by=manager
            )
            GymCheckIn.objects.create(
                business=business,
                member=member,
                checked_in_by=manager
            )
        
        # Create 1 unpaid member
        unpaid = GymMember.objects.create(
            business=business,
            name="Unpaid Member",
            phone="0999222222"
        )
        # unpaid.status is PENDING_PAYMENT by default
        GymCheckIn.objects.create(
            business=business,
            member=unpaid,
            checked_in_by=manager
        )
        
        # Calculate conversion
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_checkins = GymCheckIn.objects.filter(
            business=business,
            timestamp__gte=today_start
        ).select_related("member")
        
        paid_checkins = sum(1 for c in today_checkins if c.member.status == GymMemberStatus.ACTIVE)
        unpaid_checkins = sum(1 for c in today_checkins if c.member.status != GymMemberStatus.ACTIVE)
        total_checkins = today_checkins.count()
        
        assert total_checkins == 3
        assert paid_checkins == 2
        assert unpaid_checkins == 1
        
        conversion_percentage = (paid_checkins / total_checkins) * 100
        assert round(conversion_percentage, 1) == 66.7
    
    def test_no_checkins_zero_conversion(self, business):
        """Test conversion percentage is 0 when there are no check-ins"""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_checkins = GymCheckIn.objects.filter(
            business=business,
            timestamp__gte=today_start
        )
        
        total_checkins = today_checkins.count()
        assert total_checkins == 0
        
        # Handle divide by zero
        if total_checkins > 0:
            conversion_percentage = (0 / total_checkins) * 100
        else:
            conversion_percentage = 0
        
        assert conversion_percentage == 0


@pytest.mark.django_db
class TestDashboardIntegration:
    """Test dashboard view with new features"""
    
    def test_dashboard_shows_all_metrics(self, client, business, manager, gym_settings):
        """Test dashboard displays all payment buckets and check-in metrics"""
        # Create membership for manager
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )
        
        # Create members in different states
        pending = GymMember.objects.create(
            business=business,
            name="Pending Member",
            phone="0999111111"
        )
        
        active = GymMember.objects.create(
            business=business,
            name="Active Member",
            phone="0999222222"
        )
        active.set_paid(
            payment_date=date.today(),
            membership_fee=gym_settings.default_membership_price,
            trainer_fee=Decimal("0.00"),
            paid_by=manager
        )
        
        # Create check-in for active member
        GymCheckIn.objects.create(
            business=business,
            member=active,
            checked_in_by=manager
        )
        
        # Log in
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access dashboard
        response = client.get('/gym/')
        
        assert response.status_code == 200
        
        # Verify context variables
        assert 'total_members' in response.context
        assert 'pending_count' in response.context
        assert 'active_count' in response.context
        assert 'behind_schedule_count' in response.context
        assert 'total_checkins' in response.context
        assert 'paid_checkins' in response.context
        assert 'unpaid_checkins' in response.context
        assert 'conversion_percentage' in response.context
        
        # Verify values
        assert response.context['total_members'] == 2
        assert response.context['pending_count'] == 1
        assert response.context['active_count'] == 1
        assert response.context['behind_schedule_count'] == 0
        assert response.context['total_checkins'] == 1
        assert response.context['paid_checkins'] == 1
        assert response.context['unpaid_checkins'] == 0
        assert response.context['conversion_percentage'] == 100.0

