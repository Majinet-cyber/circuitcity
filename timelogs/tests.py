# timelogs/tests.py
"""
Tests for timelog models and summary calculations.
"""
from datetime import time, datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from timelogs.models import AgentWorkLog, LocationPing, WorkingHours
from tenants.models import Business

User = get_user_model()


class AgentWorkLogTest(TestCase):
    """Tests for AgentWorkLog model and calculations."""
    
    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="agent1",
            email="agent1@test.com",
            password="test123",
        )
        
        self.business = Business.objects.create(
            name="Test Business",
            business_kind="phones",
        )
        
        # Create working hours: 8:00 AM - 5:00 PM
        WorkingHours.objects.create(
            business=self.business,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        self.today = timezone.localdate()
    
    def test_work_log_creation(self):
        """Test creating a work log."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        self.assertIsNotNone(work_log)
        self.assertEqual(work_log.agent, self.user)
        self.assertEqual(work_log.business, self.business)
        self.assertEqual(work_log.total_on_site_minutes, 0)
        self.assertEqual(work_log.total_idle_minutes, 0)
    
    def test_scheduled_hours_populated(self):
        """Test that scheduled hours are populated from WorkingHours."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        self.assertEqual(work_log.scheduled_start, time(8, 0))
        self.assertEqual(work_log.scheduled_end, time(17, 0))
    
    def test_early_arrival_calculation(self):
        """Test early arrival bonus calculation."""
        # Create work log with early arrival
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        # Set first seen at 7:00 AM (1 hour = 60 minutes early)
        work_log.first_seen_at = timezone.make_aware(
            datetime.combine(self.today, time(7, 0))
        )
        work_log.save()
        
        self.assertEqual(work_log.arrived_early_minutes, 60)
        self.assertEqual(work_log.arrived_late_minutes, 0)
        self.assertEqual(work_log.early_bonus_blocks, 2)  # 60 min / 30 = 2 blocks
    
    def test_late_arrival_calculation(self):
        """Test late arrival penalty calculation."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        # Set first seen at 9:00 AM (1 hour = 60 minutes late)
        work_log.first_seen_at = timezone.make_aware(
            datetime.combine(self.today, time(9, 0))
        )
        work_log.save()
        
        self.assertEqual(work_log.arrived_early_minutes, 0)
        self.assertEqual(work_log.arrived_late_minutes, 60)
        self.assertEqual(work_log.late_penalty_blocks, 2)  # 60 min / 30 = 2 blocks
    
    def test_ping_on_site_tracking(self):
        """Test that pings correctly track on-site time."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        base_time = timezone.make_aware(
            datetime.combine(self.today, time(8, 0))
        )
        
        # Create a series of inside pings over 30 minutes
        for i in range(7):  # 0, 5, 10, 15, 20, 25, 30 minutes
            LocationPing.objects.create(
                work_log=work_log,
                timestamp=base_time + timedelta(minutes=i * 5),
                latitude=Decimal("-15.123456"),
                longitude=Decimal("35.123456"),
                is_inside_geofence=True,
            )
        
        # Recompute totals
        from timelogs.views import _recompute_work_log_totals
        _recompute_work_log_totals(work_log)
        
        # Should have tracked ~30 minutes on-site
        self.assertGreaterEqual(work_log.total_on_site_minutes, 25)
        self.assertLessEqual(work_log.total_on_site_minutes, 35)
        self.assertEqual(work_log.total_idle_minutes, 0)
    
    def test_ping_idle_tracking(self):
        """Test that outside pings correctly track idle time."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        base_time = timezone.make_aware(
            datetime.combine(self.today, time(10, 0))  # During working hours
        )
        
        # Create a series of outside pings over 20 minutes
        for i in range(5):  # 0, 5, 10, 15, 20 minutes
            LocationPing.objects.create(
                work_log=work_log,
                timestamp=base_time + timedelta(minutes=i * 5),
                latitude=Decimal("-15.999999"),
                longitude=Decimal("35.999999"),
                is_inside_geofence=False,
            )
        
        # Recompute totals
        from timelogs.views import _recompute_work_log_totals
        _recompute_work_log_totals(work_log)
        
        # Should have tracked ~20 minutes idle
        self.assertGreaterEqual(work_log.total_idle_minutes, 15)
        self.assertLessEqual(work_log.total_idle_minutes, 25)
        self.assertEqual(work_log.total_on_site_minutes, 0)
    
    def test_mixed_ping_tracking(self):
        """Test alternating inside/outside pings."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        base_time = timezone.make_aware(
            datetime.combine(self.today, time(9, 0))
        )
        
        # Alternate between inside and outside
        patterns = [True, True, False, False, True, True, False, True]
        for i, is_inside in enumerate(patterns):
            LocationPing.objects.create(
                work_log=work_log,
                timestamp=base_time + timedelta(minutes=i * 5),
                latitude=Decimal("-15.123456"),
                longitude=Decimal("35.123456"),
                is_inside_geofence=is_inside,
            )
        
        # Recompute totals
        from timelogs.views import _recompute_work_log_totals
        _recompute_work_log_totals(work_log)
        
        # Should have some time in both categories
        self.assertGreater(work_log.total_on_site_minutes, 0)
        self.assertGreater(work_log.total_idle_minutes, 0)
    
    def test_effective_work_minutes(self):
        """Test effective work minutes calculation."""
        work_log = AgentWorkLog.objects.create(
            agent=self.user,
            business=self.business,
            work_date=self.today,
        )
        
        # Set time range
        work_log.first_seen_at = timezone.make_aware(
            datetime.combine(self.today, time(8, 0))
        )
        work_log.last_seen_at = timezone.make_aware(
            datetime.combine(self.today, time(12, 0))
        )
        
        # 240 minutes total, 30 minutes idle
        work_log.total_idle_minutes = 30
        work_log.save()
        
        # Effective work = 240 - 30 = 210 minutes
        self.assertEqual(work_log.effective_work_minutes, 210)


class WorkingHoursTest(TestCase):
    """Tests for WorkingHours model."""
    
    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Business",
            business_kind="phones",
        )
    
    def test_get_for_date_all_days(self):
        """Test getting working hours for any day."""
        wh = WorkingHours.objects.create(
            business=self.business,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        today = timezone.localdate()
        result = WorkingHours.get_for_date(self.business, date=today)
        
        self.assertEqual(result, wh)
        self.assertEqual(result.scheduled_start, time(8, 0))
        self.assertEqual(result.scheduled_end, time(17, 0))
    
    def test_get_for_date_specific_day(self):
        """Test getting working hours for a specific day of week."""
        # Create weekday hours
        weekday_wh = WorkingHours.objects.create(
            business=self.business,
            day_of_week=0,  # Monday
            scheduled_start=time(9, 0),
            scheduled_end=time(18, 0),
        )
        
        # Create default hours
        default_wh = WorkingHours.objects.create(
            business=self.business,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        # Find a Monday
        today = timezone.localdate()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)
        
        result = WorkingHours.get_for_date(self.business, date=next_monday)
        
        # Should get the Monday-specific hours
        self.assertEqual(result.day_of_week, 0)
        self.assertEqual(result.scheduled_start, time(9, 0))

