"""
Tests for staticpages app (public pages).
"""
import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestStaticPages:
    """Test public static pages."""

    def test_home_page_loads(self):
        """Test that home page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:home"))
        assert response.status_code == 200
        assert b"Emajinet" in response.content

    def test_privacy_page_loads(self):
        """Test that privacy page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:privacy"))
        assert response.status_code == 200

    def test_terms_page_loads(self):
        """Test that terms page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:terms"))
        assert response.status_code == 200

    def test_data_deletion_page_loads(self):
        """Test that data deletion page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:data_deletion"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Data Deletion Policy" in content

    def test_simulator_page_loads(self):
        """Test that simulator page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:simulator"))
        assert response.status_code == 200
        assert b"Business Simulator" in response.content

    def test_about_page_loads(self):
        """Test that about page loads successfully."""
        client = Client()
        response = client.get(reverse("staticpages:about"))
        assert response.status_code == 200

    def test_about_page_content(self):
        """Test that about page contains expected content."""
        client = Client()
        response = client.get(reverse("staticpages:about"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # Check for the specific phrase from the requirements
        assert "pioneers determined to simplify business" in content.lower()
        assert "may they never lose" in content.lower()

    def test_about_link_in_home_footer(self):
        """Test that About link appears in home page footer."""
        client = Client()
        response = client.get(reverse("staticpages:home"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # Check for About link
        assert 'href="/home/about/"' in content or "staticpages:about" in content

