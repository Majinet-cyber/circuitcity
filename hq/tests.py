"""
Tests for HQ app - Dashboard, Gamification, and Date Helpers.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from hq.utils_dates import get_month_range, get_period_from_request, get_year_from_request
from hq.utils_gamification import (
    get_agent_rankings,
    get_agent_rank_for_user,
    get_gamification_message,
    get_current_milestone,
    get_next_milestone,
    check_and_award_milestones,
)
from hq.models import AgentMilestone
from tenants.models import Business, Membership
from sales.models import Sale


User = get_user_model()


# ============================================================================
# Date Helper Tests
# ============================================================================
class DateHelpersTestCase(TestCase):
    """Test date filtering utilities."""

    def test_get_month_range_january(self):
        """Test month range for January."""
        start, end = get_month_range(2025, 1)
        self.assertEqual(start, date(2025, 1, 1))
        self.assertEqual(end, date(2025, 2, 1))

    def test_get_month_range_december(self):
        """Test month range for December (year boundary)."""
        start, end = get_month_range(2025, 12)
        self.assertEqual(start, date(2025, 12, 1))
        self.assertEqual(end, date(2026, 1, 1))

    def test_get_month_range_february(self):
        """Test month range for February."""
        start, end = get_month_range(2025, 2)
        self.assertEqual(start, date(2025, 2, 1))
        self.assertEqual(end, date(2025, 3, 1))

    def test_get_period_from_request_month_year(self):
        """Test period extraction from request with month and year."""
        factory = RequestFactory()
        request = factory.get('/', {'month': '6', 'year': '2025'})
        
        start, end, period_type = get_period_from_request(request, default_to_current_month=False)
        
        self.assertEqual(start, date(2025, 6, 1))
        self.assertEqual(end, date(2025, 7, 1))
        self.assertEqual(period_type, "month")

    def test_get_period_from_request_7d(self):
        """Test period extraction for 7 days range."""
        factory = RequestFactory()
        request = factory.get('/', {'range': '7d'})
        
        start, end, period_type = get_period_from_request(request, default_to_current_month=False)
        
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(period_type, "7d")
        self.assertEqual((end - start).days, 7)

    def test_get_period_from_request_default_current_month(self):
        """Test default to current month."""
        factory = RequestFactory()
        request = factory.get('/', {})
        
        start, end, period_type = get_period_from_request(request, default_to_current_month=True)
        
        today = timezone.now().date()
        expected_start = date(today.year, today.month, 1)
        if today.month == 12:
            expected_end = date(today.year + 1, 1, 1)
        else:
            expected_end = date(today.year, today.month + 1, 1)
        
        self.assertEqual(start, expected_start)
        self.assertEqual(end, expected_end)
        self.assertEqual(period_type, "month")

    def test_get_year_from_request(self):
        """Test year extraction from request."""
        factory = RequestFactory()
        request = factory.get('/', {'year': '2024'})
        
        year = get_year_from_request(request)
        self.assertEqual(year, 2024)

    def test_get_year_from_request_default(self):
        """Test year extraction defaults to current year."""
        factory = RequestFactory()
        request = factory.get('/', {})
        
        year = get_year_from_request(request)
        self.assertEqual(year, timezone.now().year)


# ============================================================================
# Gamification Tests
# ============================================================================
@pytest.mark.django_db
class GamificationTestCase(TestCase):
    """Test gamification utilities."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(name="Test Business")
        
        # Create agents
        self.agent1 = User.objects.create_user(username="agent1", email="agent1@test.com")
        self.agent2 = User.objects.create_user(username="agent2", email="agent2@test.com")
        self.agent3 = User.objects.create_user(username="agent3", email="agent3@test.com")
        
        # Create memberships
        self.membership1 = Membership.objects.create(
            user=self.agent1,
            business=self.business,
            role="AGENT"
        )
        self.membership2 = Membership.objects.create(
            user=self.agent2,
            business=self.business,
            role="AGENT"
        )
        self.membership3 = Membership.objects.create(
            user=self.agent3,
            business=self.business,
            role="AGENT"
        )
        
        # Create sales
        today = timezone.now()
        for i in range(15):
            Sale.objects.create(
                agent=self.agent1,
                price=Decimal("100.00"),
                sold_at=today
            )
        for i in range(10):
            Sale.objects.create(
                agent=self.agent2,
                price=Decimal("100.00"),
                sold_at=today
            )
        for i in range(5):
            Sale.objects.create(
                agent=self.agent3,
                price=Decimal("100.00"),
                sold_at=today
            )

    def test_get_agent_rankings(self):
        """Test agent rankings calculation."""
        rankings = get_agent_rankings(
            business=self.business,
            location=None,
            start_date=None,
            end_date=None,
            limit=10
        )
        
        self.assertEqual(len(rankings), 3)
        
        # Check order (agent1 should be #1)
        self.assertEqual(rankings[0].user_id, self.agent1.id)
        self.assertEqual(rankings[0].rank, 1)
        self.assertEqual(rankings[0].sales_count, 15)
        
        # Check agent2 is #2
        self.assertEqual(rankings[1].user_id, self.agent2.id)
        self.assertEqual(rankings[1].rank, 2)
        self.assertEqual(rankings[1].sales_count, 10)
        self.assertEqual(rankings[1].behind_count, 5)  # 5 sales behind #1

    def test_get_agent_rank_for_user(self):
        """Test getting specific user's rank."""
        rank = get_agent_rank_for_user(
            user_id=self.agent2.id,
            business=self.business,
            location=None,
            start_date=None,
            end_date=None
        )
        
        self.assertIsNotNone(rank)
        self.assertEqual(rank.rank, 2)
        self.assertEqual(rank.sales_count, 10)
        self.assertEqual(rank.behind_count, 5)

    def test_get_gamification_message_first_place(self):
        """Test gamification message for #1 agent."""
        rank = get_agent_rank_for_user(
            user_id=self.agent1.id,
            business=self.business,
            location=None,
            start_date=None,
            end_date=None
        )
        
        message = get_gamification_message(rank)
        self.assertIn("#1", message)
        self.assertIn("don't let anyone catch you", message.lower())

    def test_get_gamification_message_second_place(self):
        """Test gamification message for #2 agent."""
        rank = get_agent_rank_for_user(
            user_id=self.agent2.id,
            business=self.business,
            location=None,
            start_date=None,
            end_date=None
        )
        
        message = get_gamification_message(rank)
        self.assertIn("#2", message)
        self.assertIn("behind", message.lower())

    def test_get_current_milestone(self):
        """Test milestone detection."""
        # No milestone
        milestone = get_current_milestone(5)
        self.assertIsNone(milestone)
        
        # Rising Star (10 sales)
        milestone = get_current_milestone(12)
        self.assertIsNotNone(milestone)
        threshold, name, emoji = milestone
        self.assertEqual(threshold, 10)
        self.assertEqual(name, "Rising Star")
        
        # High Achiever (25 sales)
        milestone = get_current_milestone(30)
        self.assertIsNotNone(milestone)
        threshold, name, emoji = milestone
        self.assertEqual(threshold, 25)
        self.assertEqual(name, "High Achiever")

    def test_get_next_milestone(self):
        """Test next milestone calculation."""
        # Next is Rising Star
        next_ms = get_next_milestone(5)
        self.assertIsNotNone(next_ms)
        threshold, name, emoji, sales_needed = next_ms
        self.assertEqual(threshold, 10)
        self.assertEqual(name, "Rising Star")
        self.assertEqual(sales_needed, 5)
        
        # Next is High Achiever
        next_ms = get_next_milestone(12)
        self.assertIsNotNone(next_ms)
        threshold, name, emoji, sales_needed = next_ms
        self.assertEqual(threshold, 25)
        self.assertEqual(name, "High Achiever")
        self.assertEqual(sales_needed, 13)

    def test_check_and_award_milestones(self):
        """Test milestone awarding."""
        today = timezone.now().date()
        year, month = today.year, today.month
        
        # Award milestone for 10 sales
        milestones = check_and_award_milestones(
            user=self.agent1,
            business=self.business,
            sales_count=15,
            year=year,
            month=month
        )
        
        # Should award Rising Star (10+)
        self.assertGreater(len(milestones), 0)
        self.assertTrue(any(m.milestone_type == "sales_10" for m in milestones))
        
        # Check milestone was saved
        saved_milestone = AgentMilestone.objects.filter(
            user=self.agent1,
            business=self.business,
            milestone_type="sales_10"
        ).first()
        
        self.assertIsNotNone(saved_milestone)
        self.assertEqual(saved_milestone.milestone_name, "Rising Star")


# ============================================================================
# HQ Dashboard View Tests
# ============================================================================
@pytest.mark.django_db
class HQDashboardTestCase(TestCase):
    """Test HQ dashboard views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@test.com",
            password="password123"
        )
        self.business = Business.objects.create(name="Test Business")

    def test_dashboard_requires_auth(self):
        """Test dashboard requires authentication."""
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_dashboard_loads_for_hq_admin(self):
        """Test dashboard loads for HQ admin."""
        self.client.login(username="admin", password="password123")
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_with_year_param(self):
        """Test dashboard with year parameter."""
        self.client.login(username="admin", password="password123")
        response = self.client.get(reverse('hq:dashboard') + '?year=2024')
        self.assertEqual(response.status_code, 200)

    def test_monthly_drill_down_api(self):
        """Test monthly drill-down API endpoint."""
        self.client.login(username="admin", password="password123")
        response = self.client.get(reverse('hq:monthly_drill_down_api') + '?year=2025&month=6')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data['year'], 2025)
        self.assertEqual(data['month'], 6)
        self.assertIn('daily_sales', data)
        self.assertIn('daily_onboardings', data)

    def test_monthly_drill_down_api_invalid_month(self):
        """Test monthly drill-down API with invalid month."""
        self.client.login(username="admin", password="password123")
        response = self.client.get(reverse('hq:monthly_drill_down_api') + '?year=2025&month=13')
        self.assertEqual(response.status_code, 400)


# ============================================================================
# Public Home Page Tests
# ============================================================================
class PublicHomePageTestCase(TestCase):
    """Test public home page."""

    def test_home_page_loads(self):
        """Test public home page loads without auth."""
        response = self.client.get(reverse('staticpages:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doing business")
        self.assertContains(response, "Get Started")

    def test_root_redirects_to_home_for_anonymous(self):
        """Test root URL redirects anonymous users to home."""
        response = self.client.get('/')
        # Should redirect to staticpages:home
        self.assertEqual(response.status_code, 302)

    def test_get_started_button_exists(self):
        """Test Get Started button exists on home page."""
        response = self.client.get(reverse('staticpages:home'))
        self.assertContains(response, 'href=')
        self.assertContains(response, 'Get Started')
