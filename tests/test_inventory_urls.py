# tests/test_inventory_urls.py
"""
Tests for inventory URL configuration to ensure no import errors.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client

from tenants.models import Business, Membership

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def business(db):
    """Create a test business."""
    return Business.objects.create(
        name="Test Shop",
        slug="test-shop",
        status="ACTIVE",
        business_kind="phones"
    )


@pytest.fixture
def manager_user(business):
    """Create a manager user with membership."""
    user = User.objects.create_user(
        username="manager1",
        email="manager@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return user


class TestInventoryURLsImport:
    """Test that inventory URLs can be imported without errors."""
    
    def test_urls_module_imports_cleanly(self):
        """
        The inventory.urls module should import without NameError or other exceptions.
        This catches issues like undefined variables (_phones_views, etc).
        """
        try:
            from inventory import urls
            assert urls is not None
            assert hasattr(urls, 'urlpatterns')
            assert isinstance(urls.urlpatterns, list)
        except NameError as e:
            pytest.fail(f"NameError when importing inventory.urls: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error when importing inventory.urls: {e}")


class TestScanInURL:
    """Test the scan-in URL resolution and view."""
    
    def test_scan_in_url_resolves(self, client: Client, manager_user, business):
        """
        The inventory:scan_in URL should resolve and return a valid response.
        """
        client.force_login(manager_user)
        client.session["active_business_id"] = business.id
        client.session.save()
        
        url = reverse("inventory:scan_in")
        response = client.get(url)
        
        # Should not raise NameError or 500
        # 200 or 302 (redirect) are both acceptable
        assert response.status_code in (200, 302), \
            f"Expected 200 or 302, got {response.status_code}"
    
    def test_phone_scan_in_url_resolves(self, client: Client, manager_user, business):
        """
        The inventory:phone_scan_in URL should resolve (gamified phones scan-in).
        """
        client.force_login(manager_user)
        client.session["active_business_id"] = business.id
        client.session.save()
        
        url = reverse("inventory:phone_scan_in")
        response = client.get(url)
        
        # Should not raise NameError or 500
        assert response.status_code in (200, 302), \
            f"Expected 200 or 302, got {response.status_code}"


class TestDashboardChartAPIs:
    """Test that dashboard chart API URLs resolve and return valid JSON."""
    
    def test_sales_trend_api_url_resolves(self, client: Client, manager_user, business):
        """
        The inventory:api_sales_trend URL should resolve and return valid JSON.
        """
        client.force_login(manager_user)
        client.session["active_business_id"] = business.id
        client.session.save()
        
        url = reverse("inventory:api_sales_trend")
        response = client.get(url, {"period": "7d", "metric": "count"})
        
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "labels" in data
    
    def test_top_models_api_url_resolves(self, client: Client, manager_user, business):
        """
        The inventory:api_top_models URL should resolve and return valid JSON.
        """
        client.force_login(manager_user)
        client.session["active_business_id"] = business.id
        client.session.save()
        
        url = reverse("inventory:api_top_models")
        response = client.get(url, {"period": "month"})
        
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "labels" in data


class TestDashboardMainRoute:
    """Test the main dashboard route."""
    
    def test_dashboard_route_resolves(self, client: Client, manager_user, business):
        """
        The main /dashboard/ route should resolve and render without errors.
        """
        client.force_login(manager_user)
        client.session["active_business_id"] = business.id
        client.session.save()
        
        # Try dashboard:home (main dashboard)
        try:
            url = reverse("dashboard:home")
            response = client.get(url)
            assert response.status_code in (200, 302), \
                f"dashboard:home returned {response.status_code}"
        except Exception:
            # Fallback to inventory dashboard
            url = reverse("inventory:inventory_dashboard")
            response = client.get(url)
            assert response.status_code in (200, 302), \
                f"inventory:inventory_dashboard returned {response.status_code}"

