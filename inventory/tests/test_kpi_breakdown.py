"""
Tests for KPI Breakdown Views
Ensures the KPI breakdown module loads without import errors and views work correctly.
"""

import pytest
from django.urls import reverse


class TestKPIBreakdownModule:
    """Test that the KPI breakdown module can be imported without errors."""
    
    def test_module_imports_successfully(self):
        """Test that importing the KPI breakdown views module doesn't crash."""
        try:
            from inventory import views_kpi_breakdown
            # Verify the key functions exist
            assert hasattr(views_kpi_breakdown, 'revenue_breakdown')
            assert hasattr(views_kpi_breakdown, 'profit_breakdown')
            assert hasattr(views_kpi_breakdown, 'cogs_breakdown')
            assert hasattr(views_kpi_breakdown, 'stock_value_breakdown')
        except ImportError as e:
            pytest.fail(f"Failed to import views_kpi_breakdown: {e}")
    
    def test_urls_module_imports_successfully(self):
        """Test that the KPI breakdown URLs module imports without errors."""
        try:
            from inventory import urls_kpi_breakdown
            assert hasattr(urls_kpi_breakdown, 'urlpatterns')
            assert urls_kpi_breakdown.app_name == 'kpi_breakdown'
        except ImportError as e:
            pytest.fail(f"Failed to import urls_kpi_breakdown: {e}")
    
    def test_all_breakdown_urls_resolvable(self):
        """Test that all KPI breakdown URLs can be resolved."""
        urls_to_test = ['revenue', 'profit', 'cogs', 'stock_value']
        
        for url_name in urls_to_test:
            try:
                url = reverse(f'kpi_breakdown:{url_name}')
                assert url is not None
                assert isinstance(url, str)
                assert len(url) > 0
            except Exception as e:
                pytest.fail(f"Failed to resolve kpi_breakdown:{url_name} - {e}")


@pytest.mark.django_db
class TestKPIBreakdownViewsRequireLogin:
    """Test KPI breakdown views require authentication."""
    
    def test_revenue_breakdown_requires_login(self, client):
        """Test that revenue breakdown view requires authentication."""
        url = reverse('kpi_breakdown:revenue')
        response = client.get(url)
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url or 'login' in response.url.lower()
    
    def test_profit_breakdown_requires_login(self, client):
        """Test that profit breakdown view requires authentication."""
        url = reverse('kpi_breakdown:profit')
        response = client.get(url)
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url or 'login' in response.url.lower()
    
    def test_cogs_breakdown_requires_login(self, client):
        """Test that COGS breakdown view requires authentication."""
        url = reverse('kpi_breakdown:cogs')
        response = client.get(url)
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url or 'login' in response.url.lower()
    
    def test_stock_value_breakdown_requires_login(self, client):
        """Test that stock value breakdown view requires authentication."""
        url = reverse('kpi_breakdown:stock_value')
        response = client.get(url)
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.url or 'login' in response.url.lower()

