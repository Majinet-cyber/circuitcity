"""
Tests for HQ layout consistency and notifications API endpoint.
Ensures all HQ pages use the same base template and sidebar structure.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
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

    def test_hq_home_has_sidebar_and_shell(self):
        """Test /hq/home/ has hqSidebar and hq-shell."""
        response = self.client.get(reverse("hq:home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        # Check for sidebar ID
        self.assertIn('id="hqSidebar"', content)
        # Check for shell class (dashboard uses "layout hq-shell", others use "hq-shell")
        self.assertTrue(
            "hq-shell" in content and ('class="hq-shell"' in content or 'class="layout hq-shell"' in content)
        )

    def test_hq_agents_has_sidebar_and_shell(self):
        """Test /hq/agents/ has hqSidebar and hq-shell."""
        response = self.client.get(reverse("hq:agents"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-shell"', content)

    def test_hq_businesses_has_sidebar_and_shell(self):
        """Test /hq/businesses/ has hqSidebar and hq-shell."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-shell"', content)

    def test_hq_onboarding_has_sidebar_and_shell(self):
        """Test /landing/onboarding/hq/ has hqSidebar and hq-shell."""
        from staticpages.views import onboarding_hq

        # The view requires login and staff, which we have
        response = self.client.get("/landing/onboarding/hq/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('id="hqSidebar"', content)
        self.assertIn('class="hq-shell"', content)


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
