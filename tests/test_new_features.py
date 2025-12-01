# tests/test_new_features.py
"""
Tests for the new features implemented:
- Task 1: Single-business manager experience
- Task 2: Agent work logs / presence tracking
- Task 3: Agent invites with temp password
- Task 4: Commissions, bonuses & penalties
- Task 5: Notifications
- Task 6: Trial enforcement
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

User = get_user_model()

pytestmark = [pytest.mark.django_db]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def business():
    """Create a test business."""
    from tenants.models import Business
    return Business.objects.create(
        name=f"Test Business {uuid.uuid4().hex[:6]}",
        slug=f"test-biz-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind="phones",
    )


@pytest.fixture
def location(business):
    """Create a test location for the business."""
    from inventory.models import Location
    return Location.objects.create(
        business=business,
        name="Test Store",
        city="Test City",
        latitude=Decimal("-13.9626"),
        longitude=Decimal("33.7741"),
        geofence_radius_m=150,
        is_default=True,
    )


@pytest.fixture
def manager_user(business):
    """Create a manager user bound to the business."""
    from tenants.models import Membership
    
    user = User.objects.create_user(
        username=f"manager_{uuid.uuid4().hex[:6]}",
        password="testpass123",
        email="manager@test.com",
    )
    
    # Add to Manager group
    group, _ = Group.objects.get_or_create(name="Manager")
    user.groups.add(group)
    
    # Create membership
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE",
    )
    
    return user


@pytest.fixture
def agent_user(business, location):
    """Create an agent user bound to a location."""
    from tenants.models import Membership
    
    user = User.objects.create_user(
        username=f"agent_{uuid.uuid4().hex[:6]}",
        password="testpass123",
        email="agent@test.com",
    )
    
    # Add to Agent group
    group, _ = Group.objects.get_or_create(name="Agent")
    user.groups.add(group)
    
    # Create membership with location
    Membership.objects.create(
        user=user,
        business=business,
        location=location,
        role="AGENT",
        status="ACTIVE",
    )
    
    return user


@pytest.fixture
def product():
    """Create a test product."""
    from inventory.models import Product
    return Product.objects.create(
        code=f"PHONE-{uuid.uuid4().hex[:6]}",
        brand="Test",
        model="Phone X",
        cost_price=Decimal("100000"),
        sale_price=Decimal("150000"),
    )


# ============================================================================
# Task 1: Single-business manager experience
# ============================================================================

class TestManagerBinding:
    """Test that managers are bound to a single business."""
    
    def test_manager_bound_to_business(self, business, manager_user):
        """Verify manager has membership in exactly one business."""
        from tenants.models import Membership
        
        memberships = Membership.objects.filter(user=manager_user, role="MANAGER")
        assert memberships.count() == 1
        assert memberships.first().business == business
    
    def test_manager_cannot_join_second_business(self, business, manager_user):
        """Verify manager cannot join a second business as manager."""
        from tenants.models import Business, Membership
        from django.core.exceptions import ValidationError
        
        second_business = Business.objects.create(
            name="Second Business",
            slug=f"second-{uuid.uuid4().hex[:6]}",
            status="ACTIVE",
        )
        
        with pytest.raises(ValidationError):
            Membership.objects.create(
                user=manager_user,
                business=second_business,
                role="MANAGER",
                status="ACTIVE",
            )
    
    def test_get_manager_bound_business(self, business, manager_user):
        """Verify the bound business can be retrieved."""
        from tenants.utils import get_manager_bound_business
        
        bound = get_manager_bound_business(manager_user)
        assert bound == business


# ============================================================================
# Task 2: Agent Work Logs
# ============================================================================

class TestAgentWorkLogs:
    """Test agent presence tracking."""
    
    def test_work_log_creation(self, business, location, agent_user):
        """Test creating an AgentWorkLog."""
        from timelogs.models import AgentWorkLog
        
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=timezone.localdate(),
        )
        
        assert work_log.agent == agent_user
        assert work_log.business == business
        assert work_log.total_on_site_minutes == 0
        assert work_log.total_idle_minutes == 0
    
    def test_working_hours_config(self, business, location):
        """Test WorkingHours configuration."""
        from timelogs.models import WorkingHours
        from datetime import time
        
        wh = WorkingHours.objects.create(
            business=business,
            location=location,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        # Get for today
        result = WorkingHours.get_for_date(business, location)
        assert result == wh
    
    def test_early_late_calculation(self, business, location, agent_user):
        """Test early/late arrival calculation."""
        from timelogs.models import AgentWorkLog, WorkingHours
        from datetime import time
        
        # Set up working hours
        WorkingHours.objects.create(
            business=business,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        # Create work log with early arrival
        today = timezone.localdate()
        work_log = AgentWorkLog.objects.create(
            agent=agent_user,
            business=business,
            location=location,
            work_date=today,
        )
        
        # Simulate arriving 30 minutes early (7:30 AM)
        early_time = timezone.make_aware(
            timezone.datetime.combine(today, time(7, 30))
        )
        work_log.first_seen_at = early_time
        work_log.save()
        
        # Check early calculation
        assert work_log.arrived_early_minutes == 30
        assert work_log.early_bonus_blocks == 1


# ============================================================================
# Task 3: Agent Invites with Temp Password
# ============================================================================

class TestAgentInvites:
    """Test agent invite functionality with temp passwords."""
    
    def test_invite_creation_with_temp_password(self, business, location, manager_user):
        """Test creating an invite generates a temp password."""
        from tenants.services.invites import create_agent_invite
        
        invite, temp_password = create_agent_invite(
            tenant=business,
            created_by=manager_user,
            invited_name="New Agent",
            email="newagent@test.com",
            location=location,
            generate_temp_password=True,
        )
        
        assert invite is not None
        assert temp_password is not None
        assert len(temp_password) >= 8
        assert invite.temp_password_hash != ""
        assert invite.check_temp_password(temp_password)
    
    def test_invite_temp_password_verification(self, business, manager_user):
        """Test that temp password can be verified."""
        from tenants.models import AgentInvite
        
        invite = AgentInvite.objects.create(
            business=business,
            created_by=manager_user,
            invited_name="Test Agent",
            email="test@test.com",
            token=uuid.uuid4().hex,
        )
        
        # Generate and set password
        raw_password = invite.create_and_set_temp_password()
        invite.save()
        
        # Verify correct password works
        assert invite.check_temp_password(raw_password)
        
        # Verify wrong password fails
        assert not invite.check_temp_password("wrongpassword")
    
    def test_invite_acceptance_creates_membership(self, business, location, manager_user):
        """Test that accepting an invite creates a membership."""
        from tenants.models import AgentInvite, Membership
        from tenants.services.invites import accept_invite_by_token
        
        # Create invite
        invite = AgentInvite.objects.create(
            business=business,
            created_by=manager_user,
            location=location,
            email="newagent@test.com",
            token=uuid.uuid4().hex,
            status="SENT",
            expires_at=timezone.now() + timedelta(days=7),
        )
        
        # Create new user to accept
        new_user = User.objects.create_user(
            username=f"newagent_{uuid.uuid4().hex[:6]}",
            password="temppass123",
        )
        
        # Accept invite
        returned_invite, membership = accept_invite_by_token(
            token=invite.token,
            user=new_user,
            role="AGENT",
        )
        
        assert membership.user == new_user
        assert membership.business == business
        assert membership.role == "AGENT"
        assert membership.status == "ACTIVE"
        assert returned_invite.status == "JOINED"


# ============================================================================
# Task 4: Commissions
# ============================================================================

class TestCommissions:
    """Test commission calculation."""
    
    def test_commission_config_creation(self, business):
        """Test creating commission configuration."""
        from sales.models import CommissionConfig
        
        config = CommissionConfig.objects.create(
            business=business,
            base_commission_pct=Decimal("2.50"),
            early_bonus_per_30min=Decimal("5000"),
            late_penalty_per_30min=Decimal("7000"),
            lateness_penalties_enabled=True,
            early_bonus_enabled=True,
        )
        
        assert config.base_commission_pct == Decimal("2.50")
        assert CommissionConfig.get_active(business) == config
    
    def test_sale_commission_calculation(self, business, location, agent_user, product):
        """Test commission is calculated correctly on sale."""
        from inventory.models import InventoryItem
        from sales.models import Sale, CommissionConfig, SaleCommission
        
        # Create commission config
        CommissionConfig.objects.create(
            business=business,
            base_commission_pct=Decimal("5.00"),
            is_active=True,
        )
        
        # Create inventory item
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
        )
        
        # Create sale
        sale = Sale.objects.create(
            item=item,
            agent=agent_user,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("150000"),
            commission_pct=Decimal("5.00"),
        )
        
        # Create commission record
        commission = SaleCommission.create_for_sale(sale)
        
        # 5% of 150,000 = 7,500
        assert commission.base_commission == Decimal("7500.00")
        assert commission.agent == agent_user


# ============================================================================
# Task 5: Notifications
# ============================================================================

class TestNotifications:
    """Test notification creation."""
    
    def test_notification_created_on_sale(self, business, location, agent_user, product):
        """Test that a notification is created when a sale happens."""
        from inventory.models import InventoryItem
        from sales.models import Sale
        from notifications.models import Notification
        
        # Count existing notifications
        initial_count = Notification.objects.count()
        
        # Create inventory item
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
        )
        
        # Create sale (should trigger notification signal)
        Sale.objects.create(
            item=item,
            agent=agent_user,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("150000"),
        )
        
        # Check notification was created
        new_count = Notification.objects.count()
        assert new_count > initial_count
    
    def test_notification_created_on_membership(self, business, location):
        """Test notification when agent joins."""
        from tenants.models import Membership
        from notifications.models import Notification
        
        initial_count = Notification.objects.count()
        
        # Create new agent user
        agent = User.objects.create_user(
            username=f"testagent_{uuid.uuid4().hex[:6]}",
            password="test123",
        )
        
        # Create active membership (should trigger notification)
        Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Check notification was created
        new_count = Notification.objects.count()
        assert new_count > initial_count


# ============================================================================
# Task 6: Trial Enforcement
# ============================================================================

class TestTrialEnforcement:
    """Test trial/subscription enforcement."""
    
    def test_subscription_trial_status(self, business):
        """Test trial subscription status."""
        from billing.models import BusinessSubscription, SubscriptionPlan
        
        # Create a plan
        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000"),
        )
        
        # Start trial
        sub = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )
        
        assert sub.status == BusinessSubscription.Status.TRIAL
        assert sub.is_trial
        assert sub.days_left_in_trial() > 0
        assert sub.is_active_now()
    
    def test_expired_trial_detection(self, business):
        """Test that expired trial is detected."""
        from billing.models import BusinessSubscription, SubscriptionPlan
        
        plan = SubscriptionPlan.objects.create(
            code="test-plan-exp",
            name="Test Plan Exp",
            amount=Decimal("10000"),
        )
        
        # Create subscription with trial in the past
        sub = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status=BusinessSubscription.Status.TRIAL,
            started_at=timezone.now() - timedelta(days=60),
            trial_end=timezone.now() - timedelta(days=30),
            current_period_end=timezone.now() - timedelta(days=30),
        )
        
        assert sub.is_expired()
        assert not sub.is_active_now()
    
    def test_extend_trial(self, business):
        """Test extending a trial."""
        from billing.models import BusinessSubscription, SubscriptionPlan
        
        plan = SubscriptionPlan.objects.create(
            code="test-plan-ext",
            name="Test Plan Ext",
            amount=Decimal("10000"),
        )
        
        sub = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=7,
        )
        
        original_end = sub.trial_end
        
        # Extend by 14 days
        sub.extend_trial(14, save=True)
        
        assert sub.trial_end > original_end
        assert sub.days_left_in_trial() > 7

