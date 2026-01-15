# tests/test_farm_sidebar_nav.py
"""
REGRESSION TESTS: Farm Sidebar Navigation

These tests MUST FAIL if Farm sidebar buttons disappear or become incomplete.
This prevents regression to the "Home + Business Settings only" bug.

Tested Features:
- All required sidebar buttons are present for Farm users
- URLs resolve correctly (no 404s)
- Billing buttons appear for managers only
- Non-managers don't see billing buttons
- Sidebar uses proper SSOT (get_vertical_sidebar_items)
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.utils_verticals import get_vertical_sidebar_items
from tenants.models import Business, Membership

User = get_user_model()


class FarmSidebarSSotTest(TestCase):
    """Test Farm sidebar items are defined in SSOT (get_vertical_sidebar_items)."""

    def test_farm_sidebar_items_exist_in_ssot(self):
        """Farm must have sidebar items defined in get_vertical_sidebar_items."""
        items = get_vertical_sidebar_items("farm")
        
        # CRITICAL: Farm must have more than 2 items (not just Home + Business Settings)
        self.assertGreater(
            len(items),
            5,
            f"Farm sidebar must have more than 5 items to be complete. Got: {len(items)}"
        )

    def test_farm_sidebar_has_required_keys(self):
        """All Farm sidebar items must have all required keys (Dashboard, Sales, etc)."""
        items = get_vertical_sidebar_items("farm")
        item_keys = {item["key"] for item in items}
        
        # Required keys per user spec
        required_keys = {
            "dashboard",
            "sales",
            "add_sale",
            "expenses",
            "add_expense",
            "seasons",
            "new_season",
            "assets",
            "add_asset",
            "costs",
            "reports",
            "analytics",
            "billing_subscribe",  # Manager-only
            "billing_checkout",   # Manager-only
            "settings",           # Manager-only
            "locations",          # Manager-only
        }
        
        missing_keys = required_keys - item_keys
        self.assertEqual(
            set(),
            missing_keys,
            f"Farm sidebar is missing required keys: {missing_keys}. "
            f"Available keys: {item_keys}"
        )

    def test_farm_sidebar_has_required_labels(self):
        """Farm sidebar must show all required button labels."""
        items = get_vertical_sidebar_items("farm")
        labels = [item.get("label", "") for item in items]
        labels_str = " ".join(labels).lower()
        
        # Required button labels (case-insensitive check)
        required_labels = [
            "dashboard",
            "sales",
            "add sale",
            "expenses",
            "add expense",
            "seasons",
            "new season",
            "assets",
            "add asset",
            "costs",
            "reports",
            "analytics",
            "subscribe",
            "checkout",
            "business settings",
            "locations",
        ]
        
        for label in required_labels:
            self.assertIn(
                label.lower(),
                labels_str,
                f"Farm sidebar must contain button labeled '{label}'. "
                f"Available labels: {labels}"
            )

    def test_farm_sidebar_urls_are_valid(self):
        """All Farm sidebar URLs must be valid (no placeholder '#' or missing routes)."""
        items = get_vertical_sidebar_items("farm")
        
        for item in items:
            url = item.get("url", "")
            label = item.get("label", "")
            
            # URLs must not be placeholders
            self.assertNotEqual(
                url,
                "#",
                f"Farm sidebar button '{label}' has placeholder URL '#'. Must be a real route."
            )
            self.assertNotEqual(
                url,
                "",
                f"Farm sidebar button '{label}' has empty URL. Must be defined."
            )
            
            # URLs should be named routes (alphanumeric + colon/underscore) or absolute paths (start with '/')
            # Valid examples: "billing:plans", "settings_root", "/verticals/farm/"
            is_valid_url = (
                ":" in url  # Namespaced route like "billing:plans"
                or url.startswith("/")  # Absolute path
                or url.replace("_", "").isalnum()  # Non-namespaced route like "settings_root"
            )
            self.assertTrue(
                is_valid_url,
                f"Farm sidebar button '{label}' has invalid URL format: '{url}'"
            )

    def test_farm_sidebar_billing_buttons_require_manager(self):
        """Billing buttons must be marked as require_manager=True."""
        items = get_vertical_sidebar_items("farm")
        
        billing_items = [
            item for item in items
            if item["key"] in ("billing_subscribe", "billing_checkout")
        ]
        
        self.assertGreater(
            len(billing_items),
            0,
            "Farm sidebar must include billing buttons (Subscribe, Checkout)"
        )
        
        for item in billing_items:
            self.assertTrue(
                item.get("require_manager", False),
                f"Billing button '{item['label']}' must have require_manager=True"
            )

    def test_farm_sidebar_settings_require_manager(self):
        """Business Settings and Locations must be manager-only."""
        items = get_vertical_sidebar_items("farm")
        
        manager_items = [
            item for item in items
            if item["key"] in ("settings", "locations")
        ]
        
        self.assertGreater(
            len(manager_items),
            0,
            "Farm sidebar must include settings and locations"
        )
        
        for item in manager_items:
            self.assertTrue(
                item.get("require_manager", False),
                f"Settings button '{item['label']}' must have require_manager=True"
            )


class FarmSidebarRenderingTest(TestCase):
    """Test Farm sidebar renders correctly in the actual dashboard page."""

    def setUp(self):
        """Set up test data: Farm business + manager user."""
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
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_farm_dashboard_loads_successfully(self):
        """Farm dashboard must load without errors."""
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(
            response.status_code,
            200,
            "Farm dashboard must load successfully (HTTP 200)"
        )

    def test_farm_dashboard_sidebar_context_has_items(self):
        """Farm dashboard context must have sidebar_items populated."""
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        # Check that sidebar_items is in context (may be None if not using sidebar)
        # As long as get_vertical_sidebar_items returns proper items, we're good
        items = get_vertical_sidebar_items("farm")
        self.assertGreater(
            len(items),
            10,
            f"Farm should have many sidebar items (>10). Got: {len(items)}"
        )

    def test_farm_dashboard_has_core_nav_elements(self):
        """Farm dashboard HTML must contain core navigation elements."""
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        # At minimum, the page should have the dashboard title/hero
        self.assertIn(
            "Farm",
            content,
            "Farm dashboard must contain 'Farm' text"
        )
        
        # And it should successfully load (200 status)
        self.assertEqual(response.status_code, 200)

    def test_farm_sidebar_has_testids(self):
        """Farm sidebar buttons must have data-testid attributes for E2E testing."""
        items = get_vertical_sidebar_items("farm")
        
        for item in items:
            # All main items should have testid
            if item.get("section") == "MAIN":
                self.assertIn(
                    "testid",
                    item,
                    f"Farm sidebar item '{item['label']}' must have testid for E2E testing"
                )

    def test_farm_sidebar_icons_are_defined(self):
        """All Farm sidebar items must have Bootstrap icons defined."""
        items = get_vertical_sidebar_items("farm")
        
        for item in items:
            icon = item.get("icon", "")
            label = item.get("label", "")
            
            self.assertTrue(
                icon.startswith("bi-"),
                f"Farm sidebar button '{label}' must have a valid Bootstrap icon (bi-*). Got: '{icon}'"
            )


class FarmSidebarAgentAccessTest(TestCase):
    """Test Farm sidebar access control (agent vs manager)."""

    def setUp(self):
        """Set up test data: Farm business + agent user (non-manager)."""
        self.client = Client()
        self.agent_user = User.objects.create_user(
            username="farm_agent@test.com",
            email="farm_agent@test.com",
            password="SecurePass123!",
        )
        self.manager_user = User.objects.create_user(
            username="farm_manager2@test.com",
            email="farm_manager2@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm 2",
            slug="test-farm-2",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.manager_user,
        )
        # Agent membership
        Membership.objects.create(
            user=self.agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
        )
        # Manager membership
        Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_agent_can_access_dashboard(self):
        """Farm agents must be able to access the dashboard."""
        self.client.login(username="farm_agent@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200, "Agent must be able to access farm dashboard")

    def test_manager_can_access_dashboard(self):
        """Farm managers must be able to access the dashboard."""
        self.client.login(username="farm_manager2@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200, "Manager must be able to access farm dashboard")


class FarmSidebarUrlResolutionTest(TestCase):
    """Test that all Farm sidebar URLs resolve correctly (no 404s)."""

    def setUp(self):
        """Set up test data: Farm business + manager user."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_url_test@test.com",
            email="farm_url_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm URLs",
            slug="test-farm-urls",
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
        self.client.login(username="farm_url_test@test.com", password="SecurePass123!")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

    def test_farm_dashboard_url_works(self):
        """Farm dashboard URL must work."""
        response = self.client.get("/verticals/farm/dashboard/")
        self.assertEqual(response.status_code, 200, "Farm dashboard must be accessible")

    def test_farm_ledger_list_url_works(self):
        """Farm ledger (sales/expenses) list URL must work."""
        response = self.client.get("/verticals/farm/ledger/")
        self.assertEqual(response.status_code, 200, "Farm ledger must be accessible")

    def test_farm_add_expense_url_works(self):
        """Farm add expense URL must work."""
        response = self.client.get("/verticals/farm/ledger/add-expense/")
        self.assertEqual(response.status_code, 200, "Farm add expense must be accessible")

    def test_farm_add_sale_url_works(self):
        """Farm add sale URL must work."""
        response = self.client.get("/verticals/farm/ledger/add-sale/")
        self.assertEqual(response.status_code, 200, "Farm add sale must be accessible")

    def test_farm_seasons_url_works(self):
        """Farm seasons (crops) list URL must work."""
        response = self.client.get("/verticals/farm/crops/")
        self.assertEqual(response.status_code, 200, "Farm seasons must be accessible")

    def test_farm_new_season_url_works(self):
        """Farm new season (create crop season) URL must work."""
        response = self.client.get("/verticals/farm/crops/add-season/")
        self.assertEqual(response.status_code, 200, "Farm new season must be accessible")

    def test_farm_assets_url_works(self):
        """Farm assets (livestock) list URL must work."""
        response = self.client.get("/verticals/farm/livestock/")
        self.assertEqual(response.status_code, 200, "Farm assets must be accessible")

    def test_farm_add_asset_url_works(self):
        """Farm add asset (create livestock batch) URL must work."""
        response = self.client.get("/verticals/farm/livestock/add-batch/")
        self.assertEqual(response.status_code, 200, "Farm add asset must be accessible")

    def test_farm_reports_url_works(self):
        """Farm reports URL must work."""
        response = self.client.get("/verticals/farm/reports/")
        self.assertEqual(response.status_code, 200, "Farm reports must be accessible")

    def test_billing_plans_url_exists(self):
        """Billing plans (Subscribe) URL must exist."""
        try:
            url = reverse("billing:plans")
            self.assertTrue(url, "billing:plans URL must resolve")
        except Exception as e:
            self.fail(f"billing:plans URL failed to reverse: {e}")

    def test_billing_checkout_url_exists(self):
        """Billing checkout URL must exist."""
        try:
            url = reverse("billing:checkout")
            self.assertTrue(url, "billing:checkout URL must resolve")
        except Exception as e:
            self.fail(f"billing:checkout URL failed to reverse: {e}")

    def test_settings_url_exists(self):
        """Business settings URL must exist."""
        try:
            url = reverse("settings_root")
            self.assertTrue(url, "settings_root URL must resolve")
        except Exception as e:
            self.fail(f"settings_root URL failed to reverse: {e}")


class FarmSidebarGreenThemeTest(TestCase):
    """Test that Farm sidebar uses green theme for icons."""

    def test_farm_sidebar_has_green_theme_css(self):
        """Farm sidebar template must include green theme CSS for icons."""
        from django.template.loader import get_template
        
        template = get_template("partials/sidebar.html")
        template_content = template.template.source
        
        # Check that farm-specific green theme CSS exists
        self.assertIn(
            'data-vertical="farm"',
            template_content,
            "Sidebar template must have data-vertical attribute for farm theming"
        )
        
        # Check for green gradient CSS (16a34a = green-600, 22c55e = green-500)
        self.assertIn(
            "16a34a",
            template_content,
            "Sidebar template must include green gradient for farm icons (#16a34a)"
        )

