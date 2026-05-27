"""
Tests for HQ layout consistency and notifications API endpoint.
Ensures all HQ pages use the same base template and sidebar structure.
"""
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class HQLayoutConsistencyTest(TestCase):
    """Test that all HQ pages use consistent layout structure."""

    def setUp(self):
        """Set up test data."""
        # Create superuser for HQ access
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

    def test_hq_home_has_sidebar_and_layout(self):
        """Test /hq/home/ has data-layout=hq, hqSidebar, and hq-layout."""
        response = self.client.get(reverse("hq:home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-layout="hq"', content)
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-layout"', content)

    def test_hq_agents_has_sidebar_and_layout(self):
        """Test /hq/agents/ has data-layout=hq, hqSidebar, and hq-layout."""
        response = self.client.get(reverse("hq:agents"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-layout="hq"', content)
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-layout"', content)

    def test_hq_businesses_has_sidebar_and_layout(self):
        """Test /hq/businesses/ has data-layout=hq, hqSidebar, and hq-layout."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-layout="hq"', content)
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-layout"', content)

    def test_hq_onboarding_has_sidebar_and_layout(self):
        """Test /landing/onboarding/hq/ has data-layout=hq, hqSidebar, and hq-layout."""
        from staticpages.views import onboarding_hq

        # The view requires login and staff, which we have
        response = self.client.get("/landing/onboarding/hq/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-layout="hq"', content)
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-layout"', content)


class HQNotificationsAPITest(TestCase):
    """Test HQ notifications API endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create superuser for HQ access
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

    def test_notifications_api_without_slash(self):
        """Test /hq/api/notifications returns 200 JSON."""
        response = self.client.get("/hq/api/notifications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        # Check response structure
        self.assertIn("since", data)
        self.assertIn("unread_count", data)
        self.assertIn("items", data)
        self.assertEqual(data["unread_count"], 0)
        self.assertIsInstance(data["items"], list)

    def test_notifications_api_with_slash(self):
        """Test /hq/api/notifications/ returns 200 JSON."""
        response = self.client.get("/hq/api/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIn("since", data)
        self.assertIn("unread_count", data)
        self.assertIn("items", data)

    def test_notifications_api_with_since_parameter(self):
        """Test /hq/api/notifications?since= returns 200 JSON with since value."""
        response = self.client.get("/hq/api/notifications/", {"since": "2025-01-01T00:00:00Z"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("since", data)
        # since should be returned in response
        self.assertIsNotNone(data["since"])


class HQSidebarAlwaysVisibleTest(TestCase):
    """Regression: sidebar must be present on every HQ page (never disappears)."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="hqadmin_sidebar", email="sidebar@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin_sidebar", password="adminpass123")

    # --- helper ---------------------------------------------------------- #
    def _assert_sidebar(self, url_name, **kwargs):
        """GET the named URL and assert sidebar, layout wrapper, and CSS are present."""
        url = reverse(url_name, **kwargs)
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('data-layout="hq"', content,
                       f"<body data-layout=\"hq\"> missing on {url}")
        self.assertIn('id="hqSidebar"', content,
                       f"Sidebar element (id=hqSidebar) missing on {url}")
        self.assertIn("hq-layout", content,
                       f"Layout wrapper (hq-layout) missing on {url}")
        self.assertIn("hq_layout.css", content,
                       f"Authoritative layout CSS (hq_layout.css) missing on {url}")

    # --- per-page checks ------------------------------------------------- #
    def test_sidebar_on_hq_dashboard(self):
        """HQ Dashboard must contain the locked sidebar."""
        self._assert_sidebar("hq:home")

    def test_sidebar_on_subscriptions(self):
        """Subscriptions page must contain the locked sidebar."""
        self._assert_sidebar("hq:subscriptions")

    def test_sidebar_on_businesses(self):
        """Businesses page must contain the locked sidebar."""
        self._assert_sidebar("hq:business_directory")

    def test_sidebar_on_agents(self):
        """Agents page must contain the locked sidebar."""
        self._assert_sidebar("hq:agents")

    def test_sidebar_on_contracts(self):
        """Contracts page must contain the locked sidebar."""
        self._assert_sidebar("hq:contracts_list")


class HQ404Test(TestCase):
    """Test that HQ 404 pages don't crash."""

    def setUp(self):
        """Set up test data."""
        self.admin_user = User.objects.create_superuser(
            username="hqadmin", email="admin@hq.com", password="adminpass123"
        )
        self.client = Client()
        self.client.login(username="hqadmin", password="adminpass123")

    def test_hq_nonexistent_page_returns_404_not_500(self):
        """Test /hq/does-not-exist returns 404 (not 500)."""
        response = self.client.get("/hq/does-not-exist")
        # Should be 404, not 500
        self.assertEqual(response.status_code, 404)
        # Should not have error messages about URLResolver
        content = response.content.decode("utf-8")
        self.assertNotIn("URLResolver", content)
        self.assertNotIn("VariableDoesNotExist", content)


class HQSidebarFixedLockingTest(TestCase):
    """
    Regression suite: sidebar stays fixed while main content remains fully visible.

    Tests verify:
    - /hq/home/ and /hq/analytics/ return HTTP 200
    - Both pages contain sidebar HTML, main content wrapper, and layout CSS
    - The sidebar locking CSS file has the correct fixed-positioning rules
    - No blank-content conditions: hq-main always present with content wrapper
    - Analytics page renders expected content markers
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="hq_lock_tester",
            email="lock@hq.com",
            password="securepass99",
        )
        self.client = Client()
        self.client.login(username="hq_lock_tester", password="securepass99")

    # ------------------------------------------------------------------
    # /hq/home/ (maps to views.dashboard → dashboard.html)
    # ------------------------------------------------------------------

    def test_hq_home_returns_200(self):
        """GET /hq/home/ must return HTTP 200."""
        response = self.client.get(reverse("hq:home"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_hq_home_contains_dashboard_keyword(self):
        """hq/home/ must mention Dashboard (proves content rendered, not blank)."""
        response = self.client.get(reverse("hq:home"), follow=True)
        content = response.content.decode("utf-8")
        self.assertTrue(
            "Dashboard" in content or "HQ" in content,
            "Expected 'Dashboard' or 'HQ' in /hq/home/ — page appears blank.",
        )

    def test_hq_home_has_sidebar_element(self):
        """hq/home/ must include the #hqSidebar element."""
        response = self.client.get(reverse("hq:home"), follow=True)
        self.assertContains(response, 'id="hqSidebar"')

    def test_hq_home_has_main_content_wrapper(self):
        """hq/home/ must include hq-main (main content area must not be absent)."""
        response = self.client.get(reverse("hq:home"), follow=True)
        self.assertContains(response, "hq-main")

    def test_hq_home_has_layout_wrapper(self):
        """hq/home/ must include hq-layout wrapper."""
        response = self.client.get(reverse("hq:home"), follow=True)
        self.assertContains(response, "hq-layout")

    def test_hq_home_loads_layout_css(self):
        """hq/home/ must reference hq_layout.css (sidebar-locking stylesheet)."""
        response = self.client.get(reverse("hq:home"), follow=True)
        self.assertContains(response, "hq_layout.css")

    # ------------------------------------------------------------------
    # /hq/analytics/
    # ------------------------------------------------------------------

    def test_hq_analytics_returns_200(self):
        """GET /hq/analytics/ must return HTTP 200."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_hq_analytics_contains_expected_content(self):
        """hq/analytics/ must contain analytics heading (proves content rendered)."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        content = response.content.decode("utf-8")
        self.assertTrue(
            "Analytics" in content or "HQ" in content,
            "Expected 'Analytics' or 'HQ' in /hq/analytics/ — page appears blank.",
        )

    def test_hq_analytics_has_sidebar_element(self):
        """hq/analytics/ must include the #hqSidebar element."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        self.assertContains(response, 'id="hqSidebar"')

    def test_hq_analytics_has_main_content_wrapper(self):
        """hq/analytics/ must include hq-main wrapper."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        self.assertContains(response, "hq-main")

    def test_hq_analytics_has_layout_wrapper(self):
        """hq/analytics/ must include hq-layout wrapper."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        self.assertContains(response, "hq-layout")

    def test_hq_analytics_loads_layout_css(self):
        """hq/analytics/ must reference hq_layout.css."""
        response = self.client.get(reverse("hq:hq_analytics"), follow=True)
        self.assertContains(response, "hq_layout.css")

    # ------------------------------------------------------------------
    # CSS file integrity — sidebar locking rules must exist on disk
    # ------------------------------------------------------------------

    def test_hq_layout_css_has_fixed_sidebar_rule(self):
        """hq_layout.css must declare position:fixed for the sidebar on desktop."""
        css_path = os.path.join(
            settings.BASE_DIR, "static", "css", "hq_layout.css"
        )
        self.assertTrue(
            os.path.exists(css_path),
            f"hq_layout.css not found at {css_path}",
        )
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(
            "position: fixed",
            css,
            "hq_layout.css must contain 'position: fixed' for sidebar locking.",
        )

    def test_hq_layout_css_has_margin_left_for_main(self):
        """hq_layout.css must push .hq-main right via margin-left (prevents overlap)."""
        css_path = os.path.join(
            settings.BASE_DIR, "static", "css", "hq_layout.css"
        )
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(
            "margin-left: 260px",
            css,
            "hq_layout.css must set margin-left:260px on .hq-main so content "
            "is not hidden behind the fixed sidebar.",
        )

    def test_hq_layout_css_desktop_uses_block_not_grid(self):
        """hq_layout.css desktop rule must switch .hq-layout to display:block."""
        css_path = os.path.join(
            settings.BASE_DIR, "static", "css", "hq_layout.css"
        )
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(
            "display: block",
            css,
            "hq_layout.css must use 'display: block' on desktop to prevent "
            "the CSS Grid auto-placement bug that collapses .hq-main to 260px.",
        )
