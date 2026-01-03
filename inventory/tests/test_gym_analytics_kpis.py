# inventory/tests/test_gym_analytics_kpis.py
"""
Tests for gym analytics KPIs and charts.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from circuitcity.accounts.models import User
from inventory.analytics.adapters.gym import GymAdapter
from inventory.models_verticals import GymCheckIn, GymMember, GymMemberStatus, GymPayment, GymTrainer, PaymentMethod
from tenants.models import Business


class GymAnalyticsKPIsTestCase(TestCase):
    """Test gym analytics KPIs"""

    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            vertical="gym",
        )

        # Create user
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Create trainer
        self.trainer = GymTrainer.objects.create(
            business=self.business,
            name="Test Trainer",
            phone="0999123456",
        )

        # Create adapter
        self.adapter = GymAdapter()

        # Set up dates
        self.today = timezone.now().date()
        self.week_ago = self.today - timedelta(days=7)
        self.two_days_ago = self.today - timedelta(days=2)

    def test_active_members_count(self):
        """Test active members KPI"""
        # Create active member
        member1 = GymMember.objects.create(
            business=self.business,
            name="Active Member",
            phone="0999111111",
            email="active@example.com",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Create expired member
        member2 = GymMember.objects.create(
            business=self.business,
            name="Expired Member",
            phone="0999222222",
            membership_start=self.today - timedelta(days=40),
            membership_end=self.today - timedelta(days=10),
            status=GymMemberStatus.EXPIRED,
        )

        # Get KPIs
        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        # Should only count active member
        self.assertEqual(kpis["active_members"], 1)
        self.assertEqual(kpis["total_members"], 2)

    def test_expiring_soon_count(self):
        """Test expiring soon KPI (<=7 days)"""
        # Create member expiring in 5 days
        member1 = GymMember.objects.create(
            business=self.business,
            name="Expiring Soon",
            phone="0999111111",
            membership_start=self.today - timedelta(days=25),
            membership_end=self.today + timedelta(days=5),
            status=GymMemberStatus.ACTIVE,
        )

        # Create member expiring in 10 days (should not count)
        member2 = GymMember.objects.create(
            business=self.business,
            name="Not Expiring Soon",
            phone="0999222222",
            membership_start=self.today - timedelta(days=20),
            membership_end=self.today + timedelta(days=10),
            status=GymMemberStatus.ACTIVE,
        )

        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        self.assertEqual(kpis["expiring_soon"], 1)

    def test_checkins_today(self):
        """Test check-ins today KPI"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999111111",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Create check-in today
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=today_start + timedelta(hours=10),
            checked_in_by=self.user,
        )

        # Create check-in yesterday (should not count)
        yesterday = today_start - timedelta(days=1)
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=yesterday + timedelta(hours=10),
            checked_in_by=self.user,
        )

        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        self.assertEqual(kpis["checkins_today"], 1)

    def test_attendance_rate(self):
        """Test attendance rate calculation"""
        # Create 2 active members
        member1 = GymMember.objects.create(
            business=self.business,
            name="Member 1",
            phone="0999111111",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        member2 = GymMember.objects.create(
            business=self.business,
            name="Member 2",
            phone="0999222222",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        # Create check-ins for last 7 days
        # Member 1: 7 check-ins (perfect attendance)
        # Member 2: 3 check-ins
        # Total: 10 check-ins out of 14 possible (2 members * 7 days) = 71.4%

        week_start_dt = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=7)

        for i in range(7):
            GymCheckIn.objects.create(
                business=self.business,
                member=member1,
                timestamp=week_start_dt + timedelta(days=i),
                checked_in_by=self.user,
            )

        for i in [0, 2, 4]:  # 3 check-ins
            GymCheckIn.objects.create(
                business=self.business,
                member=member2,
                timestamp=week_start_dt + timedelta(days=i),
                checked_in_by=self.user,
            )

        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        # 10 check-ins / (2 active members * 7 days) = 71.4%
        self.assertAlmostEqual(kpis["attendance_rate"], 71.4, places=1)

    def test_missed_2_days(self):
        """Test missed 2+ days KPI"""
        # Member who checked in today (should not count)
        member1 = GymMember.objects.create(
            business=self.business,
            name="Active Today",
            phone="0999111111",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        today_start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        GymCheckIn.objects.create(
            business=self.business,
            member=member1,
            timestamp=today_start,
            checked_in_by=self.user,
        )

        # Member who checked in 3 days ago (should count)
        member2 = GymMember.objects.create(
            business=self.business,
            name="Missed 3 Days",
            phone="0999222222",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        three_days_ago = today_start - timedelta(days=3)
        GymCheckIn.objects.create(
            business=self.business,
            member=member2,
            timestamp=three_days_ago,
            checked_in_by=self.user,
        )

        # Member who never checked in (should count if membership age >= 2)
        member3 = GymMember.objects.create(
            business=self.business,
            name="Never Checked In",
            phone="0999333333",
            membership_start=self.today - timedelta(days=5),
            membership_end=self.today + timedelta(days=25),
            status=GymMemberStatus.ACTIVE,
        )

        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        # Should count member2 and member3
        self.assertEqual(kpis["missed_2_days"], 2)

    def test_membership_revenue_this_month(self):
        """Test membership revenue this month KPI"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999111111",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Create payment this month
        month_start = self.today.replace(day=1)
        month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))

        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("20000.00"),
            amount=Decimal("70000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            paid_by=self.user,
            paid_at=month_start_dt + timedelta(days=5),
        )

        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        # Should only count membership_amount, not trainer_fee
        self.assertEqual(kpis["membership_revenue_this_month"], Decimal("50000.00"))

    def test_tenant_isolation(self):
        """Test that KPIs are properly scoped to business"""
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            vertical="gym",
        )

        # Create member in our business
        member1 = GymMember.objects.create(
            business=self.business,
            name="Our Member",
            phone="0999111111",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Create member in other business
        member2 = GymMember.objects.create(
            business=other_business,
            name="Other Member",
            phone="0999222222",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Get KPIs for our business
        kpis = self.adapter.kpis(
            business=self.business,
            start_date=self.today,
            end_date=self.today,
        )

        # Should only count our member
        self.assertEqual(kpis["active_members"], 1)
        self.assertEqual(kpis["total_members"], 1)
