"""
Integration test for Farm Dashboard with real DB (migrations applied).

Run with: python manage.py test tests.test_farm_dashboard_integration
         python -m pytest tests/test_farm_dashboard_integration.py -v
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.utils_verticals import get_vertical_sidebar_items

User = get_user_model()


class FarmDashboardIntegrationTest(TestCase):
    """Test farm dashboard with real database (migrations applied)."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_farm_dashboard_returns_200(self):
        """
        CRITICAL: Farm dashboard should return 200 OK with migrations applied.
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(
            response.status_code,
            200,
            f"Farm dashboard should return 200, got {response.status_code}"
        )
    
    def test_farm_dashboard_renders_with_no_data(self):
        """
        CRITICAL: Farm dashboard should render even with zero ledger entries.
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Just check it renders without error
        # Template content validation is not critical for this test
    
    def test_farm_dashboard_with_ledger_entry(self):
        """Test that dashboard works when ledger entries exist."""
        from inventory.models_farm import FarmLedgerEntry, FarmEntryType
        from django.utils import timezone
        
        # Create a test ledger entry
        FarmLedgerEntry.objects.create(
            business=self.business,
            date=timezone.now().date(),
            entry_type=FarmEntryType.SALE,
            amount_mwk=Decimal("50000.00"),
            description="Test Sale",
            created_by=self.user,
        )
        
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Snapshot should have data
        snapshot = response.context.get("snapshot")
        self.assertIsNotNone(snapshot, "Dashboard should have snapshot")


class FarmUrlPatternTest(TestCase):
    """Test farm URL patterns exist and resolve correctly."""

    def test_farm_add_season_url_resolves(self):
        """
        CRITICAL: The farm_add_season URL should resolve without error.
        This URL is used by the dashboard quick actions.
        """
        try:
            url = reverse("verticals:farm_add_season")
            self.assertEqual(url, "/verticals/farm/crops/add-season/")
        except NoReverseMatch:
            self.fail("URL 'verticals:farm_add_season' does not exist - add it to verticals/urls.py")

    def test_farm_dashboard_url_resolves(self):
        """Farm dashboard URL should resolve."""
        url = reverse("verticals:farm_dashboard")
        self.assertEqual(url, "/verticals/farm/dashboard/")

    def test_farm_ledger_list_url_resolves(self):
        """Farm ledger list URL should resolve."""
        url = reverse("verticals:farm_ledger_list")
        self.assertEqual(url, "/verticals/farm/ledger/")

    def test_farm_add_expense_url_resolves(self):
        """Farm add expense URL should resolve."""
        url = reverse("verticals:farm_add_expense")
        self.assertEqual(url, "/verticals/farm/ledger/add-expense/")

    def test_farm_add_sale_url_resolves(self):
        """Farm add sale URL should resolve."""
        url = reverse("verticals:farm_add_sale")
        self.assertEqual(url, "/verticals/farm/ledger/add-sale/")

    def test_farm_livestock_list_url_resolves(self):
        """Farm livestock list URL should resolve."""
        url = reverse("verticals:farm_livestock_list")
        self.assertEqual(url, "/verticals/farm/livestock/")

    def test_farm_crops_list_url_resolves(self):
        """Farm crops list URL should resolve."""
        url = reverse("verticals:farm_crops_list")
        self.assertEqual(url, "/verticals/farm/crops/")

    def test_farm_livestock_add_batch_url_resolves(self):
        """Farm livestock add-batch URL should resolve."""
        url = reverse("verticals:farm_livestock_add_batch")
        self.assertEqual(url, "/verticals/farm/livestock/add-batch/")

    def test_farm_reports_url_resolves(self):
        """Farm reports URL should resolve."""
        url = reverse("verticals:farm_reports")
        self.assertEqual(url, "/verticals/farm/reports/")


class FarmAddSeasonViewTest(TestCase):
    """Test the add-season view returns 200 for authorized users."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_season_test@test.com",
            email="farm_season_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Season Test Farm",
            slug="season-test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_add_season_returns_200(self):
        """
        CRITICAL: /verticals/farm/crops/add-season/ should return 200 for
        logged-in farm manager.
        """
        self.client.login(username="farm_season_test@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/crops/add-season/")
        
        self.assertEqual(
            response.status_code,
            200,
            f"Add season page should return 200, got {response.status_code}"
        )


class FarmSidebarIntegrityTest(TestCase):
    """Test that farm sidebar contains required items including Subscription links."""

    def test_farm_sidebar_has_dashboard(self):
        """Farm sidebar should have Dashboard link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("dashboard", keys, "Farm sidebar must include 'dashboard'")

    def test_farm_sidebar_has_ledger(self):
        """Farm sidebar should have Ledger link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("ledger", keys, "Farm sidebar must include 'ledger'")

    def test_farm_sidebar_has_livestock(self):
        """Farm sidebar should have Livestock link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("livestock", keys, "Farm sidebar must include 'livestock'")

    def test_farm_sidebar_has_crops(self):
        """Farm sidebar should have Crops link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("crops", keys, "Farm sidebar must include 'crops'")

    def test_farm_sidebar_has_billing(self):
        """
        CRITICAL: Farm sidebar should have Billing/Choose Plan link (shared app button).
        """
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("billing", keys, "Farm sidebar must include 'billing' for Subscription")

    def test_farm_sidebar_has_settings(self):
        """
        CRITICAL: Farm sidebar should have Business Settings link (shared app button).
        """
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("settings", keys, "Farm sidebar must include 'settings'")

    def test_farm_sidebar_has_reports(self):
        """Farm sidebar should have Reports link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("reports", keys, "Farm sidebar must include 'reports'")

    def test_farm_sidebar_has_locations(self):
        """Farm sidebar should have Locations link (shared app button)."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertIn("locations", keys, "Farm sidebar must include 'locations'")


class FarmDashboardTemplateRobustnessTest(TestCase):
    """Test that farm dashboard template renders without errors."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_template_test@test.com",
            email="farm_template_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Template Test Farm",
            slug="template-test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_dashboard_no_variable_does_not_exist(self):
        """
        CRITICAL: Dashboard should render without VariableDoesNotExist errors.
        This catches the urlpattern.name crash bug.
        """
        self.client.login(username="farm_template_test@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # This should not raise any template errors
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Check for common template error indicators in the response
        content = response.content.decode("utf-8")
        self.assertNotIn("VariableDoesNotExist", content)
        self.assertNotIn("Failed lookup for key", content)

    def test_dashboard_context_has_url_add_expense(self):
        """Dashboard context should have url_add_expense."""
        self.client.login(username="farm_template_test@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertIn("url_add_expense", response.context)

    def test_dashboard_context_has_url_add_sale(self):
        """Dashboard context should have url_add_sale."""
        self.client.login(username="farm_template_test@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertIn("url_add_sale", response.context)

    def test_dashboard_context_has_url_season_create(self):
        """Dashboard context should have url_season_create."""
        self.client.login(username="farm_template_test@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertIn("url_season_create", response.context)

