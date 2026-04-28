# hq/tests/test_hq_analytics.py
"""
Tests for HQ Analytics service and endpoints.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from tenants.models import Business
from sales.models import Sale
from inventory.models import InventoryItem, Location
from hq.services.hq_analytics import get_hq_analytics_data

User = get_user_model()


class HQAnalyticsTestCase(TestCase):
    """Test HQ analytics service and API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Create staff user
        self.staff_user = User.objects.create_user(
            username="hq_admin", email="admin@test.com", password="testpass123", is_staff=True, is_superuser=True
        )

        # Create business
        self.business = Business.objects.create(name="Test Business", business_kind="phones")

        # Create location
        self.location = Location.objects.create(business=self.business, name="Test Location")

        # Create agent
        self.agent = User.objects.create_user(username="test_agent", email="agent@test.com", password="testpass123")

        # Create inventory item
        self.item = InventoryItem.objects.create(
            business=self.business,
            name="Test Phone",
            price=Decimal("100000.00"),
            cost=Decimal("80000.00"),
            status="AVAILABLE",
        )

        # Create sale
        self.sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            sold_at=timezone.now().date(),
            price=Decimal("100000.00"),
            payment_method="CASH",
        )

        self.client = Client()
        self.client.force_login(self.staff_user)

    def test_analytics_service_basic(self):
        """Test basic analytics service functionality."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        data = get_hq_analytics_data(start_date=start_date, end_date=end_date)

        # Check structure
        self.assertIn("kpis", data)
        self.assertIn("series", data)
        self.assertIn("breakdowns", data)
        self.assertIn("top_lists", data)

        # Check KPIs
        self.assertIn("revenue", data["kpis"])
        self.assertIn("sales_count", data["kpis"])
        self.assertGreaterEqual(data["kpis"]["revenue"], 0)
        self.assertGreaterEqual(data["kpis"]["sales_count"], 0)

    def test_analytics_service_with_filters(self):
        """Test analytics service with filters."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        # Filter by business
        data = get_hq_analytics_data(start_date=start_date, end_date=end_date, business_id=self.business.id)

        self.assertIn("kpis", data)
        self.assertGreaterEqual(data["kpis"]["sales_count"], 0)

        # Filter by vertical
        data = get_hq_analytics_data(start_date=start_date, end_date=end_date, vertical="phones")

        self.assertIn("kpis", data)

    def test_analytics_api_endpoint(self):
        """Test analytics API endpoint."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        response = self.client.get(
            "/hq/api/analytics/data.json", {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpis", data)
        self.assertIn("series", data)

    def test_analytics_api_with_filters(self):
        """Test analytics API with various filters."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        # Test with business filter
        response = self.client.get(
            "/hq/api/analytics/data.json",
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "business_id": self.business.id},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpis", data)

        # Test with vertical filter
        response = self.client.get(
            "/hq/api/analytics/data.json",
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "vertical": "phones"},
        )

        self.assertEqual(response.status_code, 200)

    def test_analytics_api_unauthorized(self):
        """Test that unauthorized users cannot access analytics API."""
        # Create non-staff user
        regular_user = User.objects.create_user(
            username="regular_user", email="regular@test.com", password="testpass123"
        )

        client = Client()
        client.force_login(regular_user)

        response = client.get("/hq/api/analytics/data.json")
        self.assertEqual(response.status_code, 403)  # Should be forbidden

    def test_analytics_empty_data(self):
        """Test analytics with no data (empty result set)."""
        # Use date range with no sales
        future_date = timezone.now().date() + timedelta(days=365)

        data = get_hq_analytics_data(start_date=future_date, end_date=future_date + timedelta(days=1))

        # Should return empty but valid structure
        self.assertIn("kpis", data)
        self.assertEqual(data["kpis"]["sales_count"], 0)
        self.assertEqual(data["kpis"]["revenue"], 0.0)


class HQAnalyticsPageTests(TestCase):
    """Tests for the /hq/analytics/ page — premium redesign regression suite."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="hq_page_admin",
            email="hqpage@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.staff_user)

    def test_analytics_page_loads(self):
        """/hq/analytics/ returns HTTP 200 for an HQ admin user."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)

    def test_analytics_page_contains_kpi_cards(self):
        """Analytics page contains KPI card elements."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # KPI grid should be present
        self.assertIn("kpi-command-grid", content)
        # At least some KPI labels present
        self.assertIn("Total Revenue", content)
        self.assertIn("Total Sales", content)
        self.assertIn("MRR", content)

    def test_analytics_page_contains_chart_containers(self):
        """Analytics page contains Chart.js canvas elements."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Must have chart canvas ids
        self.assertIn("chartRevenueTrend", content)
        self.assertIn("chartVerticalMix", content)
        self.assertIn("chartPaymentMix", content)
        self.assertIn("chartProfitTrend", content)

    def test_analytics_page_does_not_render_raw_json_dump(self):
        """Analytics page must NOT contain raw pprint JSON dump of analytics_data."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # pprint dump removed — should not appear
        self.assertNotIn("analytics_data|pprint", content)
        # Also ensure raw dict-like dump patterns are absent
        self.assertNotIn("'kpis': {", content)
        self.assertNotIn("&quot;kpis&quot;", content)

    def test_analytics_page_has_smart_insights_section(self):
        """Analytics page contains the insights grid container."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("insightsGrid", content)

    def test_analytics_page_has_filter_presets(self):
        """Analytics filter bar contains all expected date presets."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("last_7d", content)
        self.assertIn("last_30d", content)
        self.assertIn("this_month", content)
        self.assertIn("last_month", content)
        self.assertIn("all_time", content)

    def test_analytics_page_preset_last_7d(self):
        """Analytics page works with last_7d preset."""
        response = self.client.get("/hq/analytics/?preset=last_7d")
        self.assertEqual(response.status_code, 200)

    def test_analytics_page_preset_this_month(self):
        """Analytics page works with this_month preset."""
        response = self.client.get("/hq/analytics/?preset=this_month")
        self.assertEqual(response.status_code, 200)

    def test_analytics_page_preset_all_time(self):
        """Analytics page works with all_time preset."""
        response = self.client.get("/hq/analytics/?preset=all_time")
        self.assertEqual(response.status_code, 200)

    def test_analytics_page_has_demo_fallback_logic(self):
        """Analytics page JS includes demo fallback data (DEMO_REVENUE_TREND)."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("DEMO_REVENUE_TREND", content)

    def test_analytics_page_has_top_tables(self):
        """Analytics page contains top businesses and top agents table sections."""
        response = self.client.get("/hq/analytics/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Top Performing Businesses", content)
        self.assertIn("Most Active Agents", content)

    def test_analytics_page_unauthenticated_redirects(self):
        """Unauthenticated request to /hq/analytics/ should redirect to login."""
        client = Client()
        response = client.get("/hq/analytics/")
        self.assertIn(response.status_code, [302, 403])


class HQRouteRegressionTests(TestCase):
    """Ensure core HQ routes still load after analytics redesign."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="hq_regression",
            email="regression@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.staff_user)

    def test_hq_dashboard_still_loads(self):
        """HQ dashboard loads after analytics changes."""
        response = self.client.get("/hq/dashboard/")
        self.assertIn(response.status_code, [200, 302])

    def test_hq_home_still_loads(self):
        """HQ home route still resolves."""
        response = self.client.get("/hq/home/")
        self.assertIn(response.status_code, [200, 302])

    def test_hq_bug_monitor_still_loads(self):
        """HQ bug monitor still loads (no regression)."""
        response = self.client.get("/hq/bugs/")
        self.assertIn(response.status_code, [200, 302])

    def test_hq_analytics_api_still_works(self):
        """HQ analytics JSON API still returns 200."""
        response = self.client.get("/hq/api/analytics/data.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpis", data)

    def test_hq_analytics_page_no_500(self):
        """HQ analytics page never returns 500 (hardened view)."""
        response = self.client.get("/hq/analytics/?preset=invalid_preset&business_id=99999999")
        self.assertNotEqual(response.status_code, 500)
