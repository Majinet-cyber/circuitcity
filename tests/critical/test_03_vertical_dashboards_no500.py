# tests/critical/test_03_vertical_dashboards_no500.py
"""
CRITICAL TEST 03: Vertical Dashboards - No 500 Policy

These tests ensure:
1. Every vertical dashboard loads without 500 errors (ALL 10 verticals)
2. Dashboards render for authenticated users with correct setup
3. Dashboards redirect unauthenticated users appropriately
4. No template errors or missing context

FAILURE HERE = Dashboard is broken = Users cannot use the app = Critical failure
"""
import pytest
from django.test import Client
from django.urls import reverse, NoReverseMatch

from tests.critical.conftest import (
    VERTICALS,
    VERTICAL_ENDPOINTS,
    get_dashboard_url,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestVerticalDashboardsNo500:
    """Test that ALL vertical dashboards load without 500 errors."""
    
    @pytest.mark.parametrize("vertical", VERTICALS)
    def test_dashboard_no_500_for_authenticated_user(self, vertical):
        """
        Dashboard must not return 500 for authenticated user.
        
        This is the PRIMARY no-500 gate test covering ALL 10 verticals:
        phones, liquor, grocery, pharmacy, clothing, gym, hardware, cement, farm, welding
        """
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        # Use reverse() for URL resolution
        dashboard_url = get_dashboard_url(vertical)
        
        if not dashboard_url:
            pytest.fail(f"No dashboard URL defined for {vertical} - must be added to VERTICAL_ENDPOINTS")
        
        response = client.get(dashboard_url, follow=True)
        
        # THE CRITICAL ASSERTION: No 500 errors
        assert response.status_code != 500, \
            f"CRITICAL: {vertical} dashboard returned 500 Server Error"
        
        # Must be accessible (200) or redirect appropriately (302)
        assert response.status_code in [200, 302], \
            f"{vertical} dashboard returned unexpected {response.status_code}"
        
        # Additional checks if we got a 200
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # No error messages in content
            error_indicators = [
                "Server Error (500)",
                "TemplateDoesNotExist",
                "NoReverseMatch",
                "TemplateSyntaxError",
            ]
            
            for indicator in error_indicators:
                assert indicator not in content, \
                    f"{vertical} dashboard contains error: {indicator}"
    
    @pytest.mark.parametrize("vertical", VERTICALS)
    def test_dashboard_unauthenticated_redirects(self, vertical):
        """Unauthenticated users should be redirected, not see 500."""
        dashboard_url = get_dashboard_url(vertical)
        
        if not dashboard_url:
            pytest.fail(f"No dashboard URL defined for {vertical}")
        
        client = Client()
        response = client.get(dashboard_url, follow=False)
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} dashboard returned 500 for unauthenticated user"
        
        # Should redirect to login
        assert response.status_code in [302, 301, 403], \
            f"{vertical} dashboard should redirect unauthenticated user, got {response.status_code}"


class TestDashboardURLResolution:
    """Test that dashboard URLs resolve correctly via reverse()."""
    
    @pytest.mark.parametrize("vertical", VERTICALS)
    def test_dashboard_url_name_resolves(self, vertical):
        """Dashboard URL name should resolve via reverse()."""
        endpoints = VERTICAL_ENDPOINTS.get(vertical, {})
        url_name = endpoints.get("dashboard")
        
        if not url_name:
            pytest.fail(f"No dashboard URL name defined for {vertical}")
        
        try:
            url = reverse(url_name)
            assert url is not None and len(url) > 0, \
                f"{vertical} dashboard URL resolved to empty string"
        except NoReverseMatch as e:
            # If reverse fails, the fallback path must exist
            fallback = endpoints.get("dashboard_path")
            assert fallback is not None, \
                f"{vertical} dashboard has neither working URL name nor fallback path: {e}"
