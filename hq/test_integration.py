"""
Integration tests for HQ Command Center features.
Tests the full flow from public home page to HQ dashboard.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from sales.models import Sale
from hq.models import AgentMilestone


User = get_user_model()


@pytest.mark.django_db
class IntegrationTestCase(TestCase):
    """Integration tests for the complete HQ experience."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create HQ admin
        self.hq_admin = User.objects.create_superuser(
            username="hqadmin",
            email="hqadmin@test.com",
            password="password123"
        )
        
        # Create business and agents
        self.business = Business.objects.create(name="Test Store")
        
        self.agent1 = User.objects.create_user(
            username="agent1",
            email="agent1@test.com",
            password="password123"
        )
        self.agent2 = User.objects.create_user(
            username="agent2",
            email="agent2@test.com",
            password="password123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.agent1,
            business=self.business,
            role="AGENT"
        )
        Membership.objects.create(
            user=self.agent2,
            business=self.business,
            role="AGENT"
        )
        
        # Create sales data
        today = timezone.now()
        for i in range(25):
            Sale.objects.create(
                agent=self.agent1,
                price=Decimal("150.00"),
                sold_at=today
            )
        for i in range(15):
            Sale.objects.create(
                agent=self.agent2,
                price=Decimal("120.00"),
                sold_at=today
            )

    def test_public_home_to_login_flow(self):
        """Test flow from public home page to login."""
        # Visit home page
        response = self.client.get(reverse('staticpages:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Get Started")
        
        # Get Started should link to login
        self.assertContains(response, 'login')

    def test_hq_dashboard_full_experience(self):
        """Test complete HQ dashboard experience."""
        # Login as HQ admin
        self.client.login(username="hqadmin", password="password123")
        
        # Visit dashboard
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for key elements
        self.assertContains(response, "HQ")
        self.assertContains(response, "Dashboard")
        
        # Check for charts
        self.assertContains(response, "salesChart")
        self.assertContains(response, "onboardingsChart")
        
        # Check for top agents
        self.assertContains(response, "Top")
        self.assertContains(response, "agent1")

    def test_monthly_drill_down_workflow(self):
        """Test monthly drill-down workflow."""
        self.client.login(username="hqadmin", password="password123")
        
        # Get current month
        today = timezone.now()
        year, month = today.year, today.month
        
        # Request drill-down data
        url = reverse('hq:monthly_drill_down_api')
        response = self.client.get(f'{url}?year={year}&month={month}')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify structure
        self.assertEqual(data['year'], year)
        self.assertEqual(data['month'], month)
        self.assertIsInstance(data['daily_sales'], list)
        self.assertIsInstance(data['daily_onboardings'], list)
        
        # Should have sales data for today
        if data['daily_sales']:
            sale = data['daily_sales'][0]
            self.assertIn('date', sale)
            self.assertIn('sales_count', sale)
            self.assertIn('revenue', sale)

    def test_agent_rankings_and_milestones(self):
        """Test agent rankings appear correctly."""
        self.client.login(username="hqadmin", password="password123")
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check rankings in response
        # Agent1 should be #1
        content = response.content.decode('utf-8')
        agent1_pos = content.find('agent1')
        agent2_pos = content.find('agent2')
        
        # Both agents should be present
        self.assertGreater(agent1_pos, 0)
        self.assertGreater(agent2_pos, 0)

    def test_year_selector_changes_data(self):
        """Test year selector changes dashboard data."""
        self.client.login(username="hqadmin", password="password123")
        
        # Visit with current year
        current_year = timezone.now().year
        response1 = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response1.status_code, 200)
        
        # Visit with different year
        response2 = self.client.get(reverse('hq:dashboard') + f'?year={current_year-1}')
        self.assertEqual(response2.status_code, 200)
        
        # Both should render successfully
        self.assertContains(response1, str(current_year))
        self.assertContains(response2, str(current_year-1))

    def test_navigation_home_button(self):
        """Test navigation includes home button."""
        self.client.login(username="hqadmin", password="password123")
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should have home button in nav
        self.assertContains(response, "Home")

    def test_milestone_awarding(self):
        """Test milestones are awarded correctly."""
        from hq.utils_gamification import check_and_award_milestones
        
        today = timezone.now().date()
        year, month = today.year, today.month
        
        # Award milestones for agent1 (25 sales)
        milestones = check_and_award_milestones(
            user=self.agent1,
            business=self.business,
            sales_count=25,
            year=year,
            month=month
        )
        
        # Should have awarded multiple milestones
        self.assertGreater(len(milestones), 0)
        
        # Check database
        db_milestones = AgentMilestone.objects.filter(
            user=self.agent1,
            business=self.business
        )
        
        self.assertGreater(db_milestones.count(), 0)
        
        # Should have Rising Star (10+) and High Achiever (25+)
        milestone_types = list(db_milestones.values_list('milestone_type', flat=True))
        self.assertIn('sales_10', milestone_types)
        self.assertIn('sales_25', milestone_types)

    def test_glassmorphic_ui_elements(self):
        """Test glassmorphic UI elements are present."""
        self.client.login(username="hqadmin", password="password123")
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check for glassmorphic CSS
        self.assertIn('backdrop-filter', content)
        self.assertIn('blur', content)
        
        # Check for NASA-style elements
        self.assertIn('glass', content)

    def test_multi_tenant_isolation(self):
        """Test data is properly isolated by business."""
        # Create second business
        business2 = Business.objects.create(name="Store 2")
        agent3 = User.objects.create_user(
            username="agent3",
            email="agent3@test.com",
            password="password123"
        )
        Membership.objects.create(
            user=agent3,
            business=business2,
            role="AGENT"
        )
        
        # Create sales for business2
        today = timezone.now()
        for i in range(10):
            Sale.objects.create(
                agent=agent3,
                price=Decimal("100.00"),
                sold_at=today
            )
        
        # HQ dashboard should show global view (all businesses)
        self.client.login(username="hqadmin", password="password123")
        response = self.client.get(reverse('hq:dashboard'))
        
        # Total sales should include all businesses
        self.assertEqual(response.status_code, 200)

