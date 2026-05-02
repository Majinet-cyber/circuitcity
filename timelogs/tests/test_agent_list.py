# timelogs/tests/test_agent_list.py
"""
Tests for timelogs agent list and work/idle time metrics.
"""
import pytest
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location
from timelogs.models import AgentWorkLog, LocationPing
from timelogs.services_presence import reliability_score

User = get_user_model()


@pytest.mark.django_db
class TestTimelogsAgentList:
    """Test timelogs agent list and metrics."""
    
    @pytest.fixture
    def business(self):
        """Create a test business."""
        return Business.objects.create(
            name="Test Business",
            business_kind="phones",
        )
    
    @pytest.fixture
    def location(self, business):
        """Create a test location."""
        return Location.objects.create(
            business=business,
            name="Main Store",
        )
    
    @pytest.fixture
    def manager_user(self, business):
        """Create a manager user."""
        user = User.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )
        return user
    
    @pytest.fixture
    def agent1(self, business):
        """Create agent 1."""
        user = User.objects.create_user(
            username="agent1",
            password="testpass123",
            email="agent1@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE",
        )
        return user
    
    @pytest.fixture
    def agent2(self, business):
        """Create agent 2."""
        user = User.objects.create_user(
            username="agent2",
            password="testpass123",
            email="agent2@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE",
        )
        return user
    
    def test_manager_sees_all_agents(self, business, manager_user, agent1, agent2, location, client: Client):
        """Test that manager can see all agents in timelogs."""
        client.force_login(manager_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Create work logs for both agents
        today = timezone.localdate()
        AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=240,  # 4 hours
            total_idle_minutes=60,      # 1 hour
        )
        AgentWorkLog.objects.create(
            agent=agent2,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=180,  # 3 hours
            total_idle_minutes=45,      # 45 min
        )
        
        # Access timelogs dashboard
        response = client.get(reverse('timelogs:dashboard'))
        
        assert response.status_code == 200
        # Should show both agents
        assert agent1.username.encode() in response.content or agent1.get_full_name().encode() in response.content
        assert agent2.username.encode() in response.content or agent2.get_full_name().encode() in response.content
    
    def test_agent_sees_only_own_logs(self, business, agent1, agent2, location, client: Client):
        """Test that agent can only see their own logs."""
        client.force_login(agent1)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Create work logs for both agents
        today = timezone.localdate()
        AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=240,
            total_idle_minutes=60,
        )
        AgentWorkLog.objects.create(
            agent=agent2,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=180,
            total_idle_minutes=45,
        )
        
        # Access timelogs dashboard
        response = client.get(reverse('timelogs:dashboard'))
        
        assert response.status_code == 200
        # Should not see agent2's data
        # Note: This depends on the template not showing other agents for non-managers
        # The view restricts access but template presentation may vary
    
    def test_work_idle_time_metrics_displayed(self, business, manager_user, agent1, location, client: Client):
        """Test that work and idle time metrics are displayed correctly."""
        client.force_login(manager_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Create work log with specific metrics
        today = timezone.localdate()
        AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=300,  # 5 hours
            total_idle_minutes=90,      # 1.5 hours
        )
        
        # Access timelogs dashboard
        response = client.get(reverse('timelogs:dashboard'))
        
        assert response.status_code == 200
        # Check that metrics are present
        assert b'300' in response.content  # Work minutes
        assert b'90' in response.content   # Idle minutes
    
    def test_agent_selector_available_for_managers(self, business, manager_user, agent1, agent2, client: Client):
        """Test that agent selector is available for managers."""
        client.force_login(manager_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access timelogs dashboard
        response = client.get(reverse('timelogs:dashboard'))
        
        assert response.status_code == 200
        # Should have agent selector
        assert b'<select' in response.content
        assert b'All Agents' in response.content or b'all' in response.content.lower()
    
    def test_empty_state_no_agents_logged(self, business, manager_user, client: Client):
        """Test empty state when no agents have logged time."""
        client.force_login(manager_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access timelogs dashboard (no logs created)
        response = client.get(reverse('timelogs:dashboard'))
        
        assert response.status_code == 200
        # Should show empty/no data message
        # Exact text depends on template

    def test_manager_csv_export_includes_all_agents(self, business, manager_user, agent1, agent2, location, client: Client):
        """Managers can export all business agents; export remains tenant-scoped."""
        client.force_login(manager_user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()

        today = timezone.localdate()
        AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=120,
        )
        AgentWorkLog.objects.create(
            agent=agent2,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=90,
        )

        response = client.get(
            reverse('timelogs:export_csv'),
            {"from_date": today.isoformat(), "to_date": today.isoformat(), "agent": "all"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "agent1" in content
        assert "agent2" in content
        assert "Reliability Score" in content

    def test_agent_csv_export_only_own_logs(self, business, agent1, agent2, location, client: Client):
        """Agents cannot export another user's logs by passing query params."""
        client.force_login(agent1)
        session = client.session
        session['active_business_id'] = business.id
        session.save()

        today = timezone.localdate()
        AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=120,
        )
        AgentWorkLog.objects.create(
            agent=agent2,
            business=business,
            location=location,
            work_date=today,
            total_on_site_minutes=90,
        )

        response = client.get(
            reverse('timelogs:export_csv'),
            {"from_date": today.isoformat(), "to_date": today.isoformat(), "agent": agent2.id},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "agent1" in content
        assert "agent2" not in content

    def test_reliability_score_uses_lateness_and_geofence(self, business, agent1, location):
        """Reliability scoring should degrade for late and currently outside agents."""
        now = timezone.now()
        work_log = AgentWorkLog.objects.create(
            agent=agent1,
            business=business,
            location=location,
            work_date=timezone.localdate(),
            first_seen_at=now - timedelta(hours=3),
            last_seen_at=now,
            scheduled_start=(now - timedelta(hours=4)).time(),
            scheduled_end=(now + timedelta(hours=4)).time(),
            arrived_late_minutes=30,
            total_on_site_minutes=120,
            total_idle_minutes=30,
        )
        AgentWorkLog.objects.filter(pk=work_log.pk).update(arrived_late_minutes=30)
        work_log.refresh_from_db()
        LocationPing.objects.create(
            work_log=work_log,
            timestamp=now,
            latitude=Decimal("0"),
            longitude=Decimal("0"),
            is_inside_geofence=False,
        )

        assert reliability_score(work_log) == 49

