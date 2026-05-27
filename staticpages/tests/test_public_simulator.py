# staticpages/tests/test_public_simulator.py
"""
Tests for the public simulator on the home page and standalone page.
Ensures anonymous users can access the simulator without login or business context.
"""
import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestPublicSimulator:
    """Test suite for public simulator access."""

    def test_home_page_contains_simulator(self):
        """Home page should contain the embedded business simulator."""
        client = Client()
        response = client.get(reverse("staticpages:home"))

        assert response.status_code == 200
        content = response.content.decode("utf-8").lower()

        # Check for simulator section
        assert "business simulator" in content or "simulator" in content
        assert "revenue" in content
        assert "profit" in content
        assert "customers" in content or "units" in content

    def test_standalone_simulator_page_accessible(self):
        """Standalone simulator page should be accessible to anonymous users."""
        client = Client()
        response = client.get(reverse("staticpages:simulator"))

        assert response.status_code == 200
        content = response.content.decode("utf-8").lower()

        # Should contain simulator elements
        assert "business simulator" in content or "simulator" in content
        assert "revenue" in content
        assert "cost" in content
        assert "profit" in content

    def test_simulator_no_login_required(self):
        """Simulator should work without authentication."""
        client = Client()
        # Ensure we're not logged in
        assert "_auth_user_id" not in client.session

        response = client.get(reverse("staticpages:simulator"))

        # Should not redirect to login
        assert response.status_code == 200
        assert "login" not in response.url if hasattr(response, "url") else True

    def test_simulator_no_business_required(self):
        """Simulator should work without active business context."""
        client = Client()
        response = client.get(reverse("staticpages:simulator"))

        assert response.status_code == 200
        # Should not show business selection or activation prompts
        content = response.content.decode("utf-8").lower()
        assert "activate" not in content or "business simulator" in content

    def test_simulator_has_interactive_elements(self):
        """Simulator page should have interactive controls."""
        client = Client()
        response = client.get(reverse("staticpages:simulator"))

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Check for slider inputs (common in simulator)
        assert "slider" in content.lower() or "input" in content.lower()
        # Check for JavaScript (client-side simulator)
        assert "<script" in content

    def test_simulator_no_410_gone(self):
        """Simulator should not return 410 Gone (legacy block removed)."""
        client = Client()
        response = client.get(reverse("staticpages:simulator"))

        # Should be 200, not 410
        assert response.status_code == 200
        content = response.content.decode("utf-8").lower()

        # Should not contain "has moved" or "upgraded" messages
        assert "has moved" not in content
        assert "410 gone" not in content
        assert "upgraded" not in content or "business simulator" in content

    def test_home_page_simulator_section_visible(self):
        """Home page simulator section should be visible and functional."""
        client = Client()
        response = client.get(reverse("staticpages:home"))

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Look for simulator section ID or heading
        assert "business-simulator" in content or "Business Simulator" in content
        # Should have input controls
        assert "sim-customers" in content or "customers" in content.lower()
