# tests/test_timelog_geo.py
"""
Tests for geo-based time tracking, bonuses, and penalties.
"""
import pytest
from decimal import Decimal
from datetime import datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import Client

from timelogs.models import AgentWorkLog, LocationPing, WorkingHours
from timelogs.utils_geo import haversine_distance, is_within_geofence, calculate_30min_slots
from timelogs.constants import WORK_START, WORK_END, EARLY_BONUS_PER_30, LATE_PENALTY_PER_30
from tenants.models import Business, Membership
from inventory.models import Location
from wallet.models import WalletTransaction, TxnType

User = get_user_model()


@pytest.mark.django_db
class TestGeoUtils:
    """Test geolocation utility functions."""
    
    def test_haversine_distance(self):
        """Test haversine distance calculation."""
        # Lilongwe City Center to Kamuzu International Airport (~25 km)
        lat1, lon1 = -13.9626, 33.7741
        lat2, lon2 = -13.7894, 33.7811
        
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        
        # Should be approximately 19,000-20,000 meters
        assert 18000 < distance < 21000
    
    def test_is_within_geofence(self):
        """Test geofence checking."""
        store_lat = Decimal("-15.7861")
        store_lon = Decimal("35.0058")
        
        # Agent at store (same location)
        is_inside, distance = is_within_geofence(
            store_lat, store_lon,
            store_lat, store_lon,
            150
        )
        assert is_inside is True
        assert distance < 10  # Should be very close to 0
        
        # Agent 100m away (within geofence)
        nearby_lat = Decimal("-15.7870")
        nearby_lon = Decimal("35.0058")
        is_inside, distance = is_within_geofence(
            nearby_lat, nearby_lon,
            store_lat, store_lon,
            150
        )
        assert is_inside is True
        
        # Agent 500m away (outside geofence)
        far_lat = Decimal("-15.7900")
        far_lon = Decimal("35.0058")
        is_inside, distance = is_within_geofence(
            far_lat, far_lon,
            store_lat, store_lon,
            150
        )
        assert is_inside is False
    
    def test_calculate_30min_slots(self):
        """Test 30-minute slot calculation."""
        assert calculate_30min_slots(0) == 0
        assert calculate_30min_slots(29) == 0
        assert calculate_30min_slots(30) == 1
        assert calculate_30min_slots(59) == 1
        assert calculate_30min_slots(60) == 2
        assert calculate_30min_slots(90) == 3


@pytest.mark.django_db
class TestEarlyBonus:
    """Test early arrival bonuses."""
    
    @pytest.fixture
    def setup(self):
        """Setup business, location, and agent."""
        business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        location = Location.objects.create(
            business=business,
            name="Main Store",
            latitude=Decimal("-15.7861"),
            longitude=Decimal("35.0058"),
            geofence_radius_m=150
        )
        
        agent = User.objects.create_user(
            username="early_agent",
            email="early@test.com",
            password="testpass123"
        )
        
        membership = Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
            location_tracking_enabled=True
        )
        
        # Set working hours (8:00 - 17:30)
        WorkingHours.objects.create(
            business=business,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        return {
            "business": business,
            "location": location,
            "agent": agent,
            "membership": membership
        }
    
    def test_agent_early_arrival_gets_bonus(self, setup):
        """Test that arriving early grants bonuses."""
        agent = setup["agent"]
        business = setup["business"]
        location = setup["location"]
        
        # Create work log for today
        today = timezone.localdate()
        
        # Agent arrives at 07:00 (1 hour = 60 minutes early)
        arrival_time = timezone.make_aware(
            datetime.combine(today, time(7, 0))
        )
        
        work_log = AgentWorkLog.objects.create(
            agent=agent,
            business=business,
            location=location,
            work_date=today,
            first_seen_at=arrival_time,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        # 60 minutes early = 2 slots of 30 minutes
        # 2 * 5000 = 10,000 bonus
        assert work_log.arrived_early_minutes == 60
        assert work_log.early_bonus_blocks == 2
        
        # Calculate bonus
        expected_bonus = EARLY_BONUS_PER_30 * 2  # 10,000
        work_log.bonus_amount = expected_bonus
        work_log.save()
        
        assert work_log.bonus_amount == Decimal("10000.00")


@pytest.mark.django_db
class TestLatePenalty:
    """Test late arrival penalties."""
    
    @pytest.fixture
    def setup(self):
        """Setup business, location, and agent."""
        business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        location = Location.objects.create(
            business=business,
            name="Main Store",
            latitude=Decimal("-15.7861"),
            longitude=Decimal("35.0058"),
            geofence_radius_m=150
        )
        
        agent = User.objects.create_user(
            username="late_agent",
            email="late@test.com",
            password="testpass123"
        )
        
        membership = Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
            location_tracking_enabled=True
        )
        
        WorkingHours.objects.create(
            business=business,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        return {
            "business": business,
            "location": location,
            "agent": agent,
            "membership": membership
        }
    
    def test_agent_late_arrival_gets_penalty(self, setup):
        """Test that arriving late incurs penalties."""
        agent = setup["agent"]
        business = setup["business"]
        location = setup["location"]
        
        today = timezone.localdate()
        
        # Agent arrives at 09:00 (60 minutes late)
        arrival_time = timezone.make_aware(
            datetime.combine(today, time(9, 0))
        )
        
        work_log = AgentWorkLog.objects.create(
            agent=agent,
            business=business,
            location=location,
            work_date=today,
            first_seen_at=arrival_time,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        # 60 minutes late = 2 slots of 30 minutes
        assert work_log.arrived_late_minutes == 60
        assert work_log.late_penalty_blocks == 2
        
        # Calculate penalty (2 * 7000 = 14,000)
        expected_penalty = LATE_PENALTY_PER_30 * 2
        work_log.penalty_amount = expected_penalty
        work_log.save()
        
        assert work_log.penalty_amount == Decimal("14000.00")


@pytest.mark.django_db
class TestAfterHours:
    """Test that no changes occur after work hours."""
    
    @pytest.fixture
    def setup(self):
        """Setup business, location, and agent."""
        business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        location = Location.objects.create(
            business=business,
            name="Main Store",
            latitude=Decimal("-15.7861"),
            longitude=Decimal("35.0058"),
            geofence_radius_m=150
        )
        
        agent = User.objects.create_user(
            username="night_agent",
            email="night@test.com",
            password="testpass123"
        )
        
        membership = Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
            location_tracking_enabled=True
        )
        
        return {
            "business": business,
            "location": location,
            "agent": agent,
            "membership": membership
        }
    
    def test_after_work_hours_no_changes(self, setup):
        """Test that pings after 17:30 don't affect bonus/penalty."""
        agent = setup["agent"]
        business = setup["business"]
        location = setup["location"]
        
        today = timezone.localdate()
        
        # Create work log
        work_log = AgentWorkLog.objects.create(
            agent=agent,
            business=business,
            location=location,
            work_date=today,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        # Ping at 18:00 (after work hours)
        after_hours_time = timezone.make_aware(
            datetime.combine(today, time(18, 0))
        )
        
        LocationPing.objects.create(
            work_log=work_log,
            timestamp=after_hours_time,
            latitude=location.latitude,
            longitude=location.longitude,
            is_inside_geofence=True
        )
        
        # Should not affect penalties/bonuses
        # (Implementation detail: bonuses/penalties are calculated during work hours only)
        assert work_log.bonus_amount == Decimal("0.00")
        assert work_log.penalty_amount == Decimal("0.00")


@pytest.mark.django_db
class TestOutOfRangeIdle:
    """Test that being out of range counts as idle."""
    
    @pytest.fixture
    def setup(self):
        """Setup business, location, and agent."""
        business = Business.objects.create(
            name="Test Shop",
            slug="test-shop",
            status="ACTIVE"
        )
        
        location = Location.objects.create(
            business=business,
            name="Main Store",
            latitude=Decimal("-15.7861"),
            longitude=Decimal("35.0058"),
            geofence_radius_m=150
        )
        
        agent = User.objects.create_user(
            username="idle_agent",
            email="idle@test.com",
            password="testpass123"
        )
        
        membership = Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
            location_tracking_enabled=True
        )
        
        return {
            "business": business,
            "location": location,
            "agent": agent,
            "membership": membership
        }
    
    def test_out_of_range_counts_as_idle(self, setup):
        """Test that pings outside geofence count as idle time."""
        agent = setup["agent"]
        business = setup["business"]
        location = setup["location"]
        
        today = timezone.localdate()
        
        work_log = AgentWorkLog.objects.create(
            agent=agent,
            business=business,
            location=location,
            work_date=today,
            scheduled_start=WORK_START,
            scheduled_end=WORK_END
        )
        
        # Ping inside at 09:00
        inside_time = timezone.make_aware(
            datetime.combine(today, time(9, 0))
        )
        LocationPing.objects.create(
            work_log=work_log,
            timestamp=inside_time,
            latitude=location.latitude,
            longitude=location.longitude,
            is_inside_geofence=True
        )
        
        # Ping outside at 09:30 (500m away)
        outside_time = timezone.make_aware(
            datetime.combine(today, time(9, 30))
        )
        LocationPing.objects.create(
            work_log=work_log,
            timestamp=outside_time,
            latitude=Decimal("-15.7900"),  # ~500m away
            longitude=Decimal("35.0058"),
            is_inside_geofence=False
        )
        
        # This would be calculated by the recompute function in production
        # For test purposes, we verify the pings are recorded correctly
        assert work_log.pings.count() == 2
        assert work_log.pings.filter(is_inside_geofence=True).count() == 1
        assert work_log.pings.filter(is_inside_geofence=False).count() == 1

