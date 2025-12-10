"""
Tests for gym dashboard enhancements: payment mix, active session members, 
membership expiry metrics, and trainer earnings.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.models_verticals import (
    GymMember, GymPayment, GymTrainer, GymSettings, GymCheckIn,
    GymMemberStatus, PaymentMethod
)

User = get_user_model()


class TestGymDashboardEnhancements(TestCase):
    """Test gym dashboard payment mix and metrics"""
    
    def setUp(self):
        """Set up test data"""
        # Create gym business
        self.business = Business.objects.create(
            name="Test Gym",
            slug="test-gym",
            business_kind="gym",
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Gym"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@gym.com",
            email="manager@gym.com",
            password="testpass123"
        )
        
        # Create membership (managers don't have a location)
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create trainers
        self.trainer1 = GymTrainer.objects.create(
            business=self.business,
            name="Steve",
            is_active=True
        )
        self.trainer2 = GymTrainer.objects.create(
            business=self.business,
            name="Lesta",
            is_active=True
        )
        
        # Create gym settings
        self.settings = GymSettings.objects.create(
            business=self.business,
            default_membership_price=Decimal("50000.00"),
            default_trainer_fee=Decimal("30000.00")
        )
        
        # Create members
        self.member1 = GymMember.objects.create(
            business=self.business,
            name="John Doe",
            phone="0999123456",
            trainer=self.trainer1,
            has_trainer=True,
            membership_fee=Decimal("50000.00"),
            trainer_fee=Decimal("30000.00"),
            status=GymMemberStatus.ACTIVE,
            membership_start=date.today(),
            membership_end=date.today() + timedelta(days=30)
        )
        
        self.member2 = GymMember.objects.create(
            business=self.business,
            name="Jane Smith",
            phone="0999654321",
            trainer=self.trainer2,
            has_trainer=True,
            membership_fee=Decimal("50000.00"),
            trainer_fee=Decimal("30000.00"),
            status=GymMemberStatus.ACTIVE,
            membership_start=date.today(),
            membership_end=date.today() + timedelta(days=30)
        )
        
        # Create payments with different methods
        today_dt = timezone.now()
        self.payment1 = GymPayment.objects.create(
            member=self.member1,
            amount=Decimal("80000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=self.manager,
            paid_at=today_dt
        )
        
        self.payment2 = GymPayment.objects.create(
            member=self.member2,
            amount=Decimal("80000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            paid_by=self.manager,
            paid_at=today_dt
        )
        
        # Create check-ins
        self.checkin1 = GymCheckIn.objects.create(
            business=self.business,
            member=self.member1,
            checked_in_by=self.manager,
            timestamp=today_dt
        )
        
        self.client = Client()
    
    def test_payment_mix_aggregation(self):
        """Test that payment mix is correctly aggregated"""
        self.client.force_login(self.manager)
        
        # Request dashboard
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check payment mix in context
        payment_mix = response.context.get("payment_mix", [])
        self.assertIsNotNone(payment_mix)
        
        # Should have 2 payment methods
        self.assertEqual(len(payment_mix), 2)
        
        # Check that totals are correct
        total_revenue = response.context.get("total_revenue", Decimal("0.00"))
        self.assertEqual(total_revenue, Decimal("160000.00"))
        
        # Verify each payment method
        methods = {item["method"]: item for item in payment_mix}
        self.assertIn(PaymentMethod.CASH, methods)
        self.assertIn(PaymentMethod.MOBILE_MONEY, methods)
        
        self.assertEqual(methods[PaymentMethod.CASH]["count"], 1)
        self.assertEqual(methods[PaymentMethod.CASH]["total"], Decimal("80000.00"))
        
        self.assertEqual(methods[PaymentMethod.MOBILE_MONEY]["count"], 1)
        self.assertEqual(methods[PaymentMethod.MOBILE_MONEY]["total"], Decimal("80000.00"))
    
    def test_active_session_members(self):
        """Test active session members count"""
        self.client.force_login(self.manager)
        
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should have 1 active session member (member1 checked in today)
        active_session = response.context.get("active_session_members", 0)
        self.assertEqual(active_session, 1)
    
    def test_membership_expiry_metrics(self):
        """Test membership expiry metrics"""
        # Create a member expiring soon
        expiring_member = GymMember.objects.create(
            business=self.business,
            name="Expiring Member",
            phone="0999111222",
            status=GymMemberStatus.ACTIVE,
            membership_start=date.today() - timedelta(days=25),
            membership_end=date.today() + timedelta(days=5)
        )
        
        # Create an expired member
        expired_member = GymMember.objects.create(
            business=self.business,
            name="Expired Member",
            phone="0999333444",
            status=GymMemberStatus.BEHIND_SCHEDULE,
            membership_start=date.today() - timedelta(days=60),
            membership_end=date.today() - timedelta(days=30)
        )
        
        self.client.force_login(self.manager)
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check metrics
        expiring_soon = response.context.get("expiring_soon", 0)
        expired = response.context.get("expired", 0)
        
        self.assertGreaterEqual(expiring_soon, 1)
        self.assertGreaterEqual(expired, 1)
    
    def test_trainer_earnings(self):
        """Test trainer earnings calculation"""
        self.client.force_login(self.manager)
        
        url = reverse("verticals:gym_dashboard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check trainer stats
        trainer_stats = response.context.get("trainer_stats", [])
        self.assertIsNotNone(trainer_stats)
        self.assertEqual(len(trainer_stats), 2)
        
        # Find Steve's stats
        steve_stats = next((t for t in trainer_stats if t["trainer"].name == "Steve"), None)
        self.assertIsNotNone(steve_stats)
        
        # Steve should have revenue from member1's payment
        self.assertEqual(steve_stats["revenue"], Decimal("80000.00"))
        self.assertEqual(steve_stats["active_members"], 1)
        
        # Find Lesta's stats
        lesta_stats = next((t for t in trainer_stats if t["trainer"].name == "Lesta"), None)
        self.assertIsNotNone(lesta_stats)
        
        # Lesta should have revenue from member2's payment
        self.assertEqual(lesta_stats["revenue"], Decimal("80000.00"))
        self.assertEqual(lesta_stats["active_members"], 1)
    
    def test_date_range_filtering(self):
        """Test dashboard date range filtering"""
        self.client.force_login(self.manager)
        
        # Test today
        url = reverse("verticals:gym_dashboard") + "?range=today"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("period_label"), "Today")
        
        # Test last 7 days
        url = reverse("verticals:gym_dashboard") + "?range=7d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("period_label"), "Last 7 Days")
        
        # Test this month
        url = reverse("verticals:gym_dashboard") + "?range=month"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("period_label"), "This Month")


class TestGymSidebarRouting(TestCase):
    """Test gym sidebar routes to attendance check-in instead of time logs"""
    
    def setUp(self):
        """Set up test data"""
        # Create gym business
        self.business = Business.objects.create(
            name="Test Gym",
            slug="test-gym",
            business_kind="gym",
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Gym"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@gym.com",
            email="manager@gym.com",
            password="testpass123"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        self.client = Client()
    
    def test_gym_checkin_page_loads(self):
        """Test gym check-in page loads successfully"""
        self.client.force_login(self.manager)
        
        url = reverse("gym:checkin_page")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("member_data", response.context)


class TestActiveTabFixes(TestCase):
    """Test that active_tab context variable is always provided"""
    
    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        # Create membership (managers don't have a location)
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def test_time_logs_page_has_active_tab(self):
        """Test time logs page provides active_tab in context"""
        self.client.force_login(self.manager)
        
        url = reverse("inventory:time_logs")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should have active_tab in context
        self.assertIn("active_tab", response.context or {})

