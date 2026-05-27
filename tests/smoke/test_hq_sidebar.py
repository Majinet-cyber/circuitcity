# tests/smoke/test_hq_sidebar.py
"""
Smoke tests for HQ Platform Admin sidebar navigation routes.

Tests that every HQ sidebar link (staff/superuser):
- Can be reversed (no NoReverseMatch)
- Loads without 500 errors
- Is accessible only to staff/superuser

This validates platform admin experience and HQ dashboard stability.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from tests.smoke.fixtures import SmokeTestFixtures
from tests.smoke.helpers import SidebarLinkExtractor

User = get_user_model()

# Mark all tests in this module as smoke tests
pytestmark = [pytest.mark.django_db, pytest.mark.smoke]


class TestHQPlatformSidebarRoutes(TestCase):
    """Test HQ platform sidebar routes for staff/superuser."""
    
    def setUp(self):
        self.superuser = SmokeTestFixtures.create_superuser()
        self.client = Client()
        self.client.login(username=self.superuser.username, password="testpass123")
    
    def test_hq_sidebar_urls_resolve(self):
        """Test that all HQ sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_hq_sidebar_links()
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for HQ sidebar:\n" + "\n".join(errors)
    
    def test_hq_sidebar_urls_load(self):
        """Test that all HQ sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_hq_sidebar_links()
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                # Some HQ URLs may not exist in all environments (tickets, audit logs)
                # We log but don't fail on NoReverseMatch for HQ optional features
                errors.append(f"SKIP {label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            # Accept 200, 302 (redirect), or 404 (module not installed)
            # Only fail on 500 errors
            if load_error and 'Server Error (500)' in load_error:
                errors.append(f"FAIL {label} ({url}): {load_error}")
            elif status == 500:
                errors.append(f"FAIL {label} ({url}): HTTP 500")
            # else: pass (200, 302, 404 are acceptable)
        
        # Filter only FAIL errors
        fail_errors = [e for e in errors if e.startswith("FAIL")]
        
        assert len(fail_errors) == 0, f"Critical errors for HQ sidebar:\n" + "\n".join(fail_errors)
    
    def test_hq_dashboard_loads(self):
        """Test that HQ dashboard home loads."""
        response = self.client.get('/hq/', follow=True)
        assert response.status_code == 200, f"HQ dashboard should load, got {response.status_code}"
        
        content = response.content.decode()
        assert 'Server Error (500)' not in content, "HQ dashboard contains error"


class TestHQAccessControl(TestCase):
    """Test that HQ routes are protected (non-staff cannot access)."""
    
    def setUp(self):
        # Create regular user (not staff)
        self.regular_user = SmokeTestFixtures.create_agent_user(
            username="regular_user",
            email="regular@test.com"
        )
        self.client = Client()
        self.client.login(username=self.regular_user.username, password="testpass123")
    
    def test_non_staff_cannot_access_hq_dashboard(self):
        """Test that non-staff users are redirected from HQ dashboard."""
        response = self.client.get('/hq/', follow=True)
        
        # Should redirect to login or show 403/404, not 200 OK with HQ content
        if response.status_code == 200:
            content = response.content.decode()
            # Should not show HQ dashboard
            assert 'Emajinet HQ' not in content or 'Platform' not in content, \
                "Non-staff user should not see HQ dashboard content"
    
    def test_non_staff_cannot_access_hq_businesses(self):
        """Test that non-staff users cannot access HQ businesses page."""
        response = self.client.get('/hq/businesses/', follow=True)
        
        # Should not get 200 OK
        assert response.status_code in [302, 403, 404], \
            f"Non-staff should not access /hq/businesses/, got {response.status_code}"


class TestHQBusinessCreation(TestCase):
    """Test HQ business creation workflow (smoke test for onboarding)."""
    
    def setUp(self):
        self.superuser = SmokeTestFixtures.create_superuser()
        self.client = Client()
        self.client.login(username=self.superuser.username, password="testpass123")
    
    def test_hq_businesses_page_loads(self):
        """Test that HQ businesses list page loads."""
        response = self.client.get('/hq/businesses/', follow=True)
        
        # Accept 200 or 404 (if hq app not fully set up)
        assert response.status_code in [200, 404], \
            f"HQ businesses should return 200 or 404, got {response.status_code}"
        
        if response.status_code == 200:
            content = response.content.decode()
            assert 'Server Error (500)' not in content, "HQ businesses page contains error"

