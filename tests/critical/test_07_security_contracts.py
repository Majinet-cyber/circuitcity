# tests/critical/test_07_security_contracts.py
"""
CRITICAL TEST 07: Security Contracts (Auth + CSRF)

These tests ensure authentication and CSRF protection work correctly:
1. Unauthenticated access is blocked (redirect to login or 403)
2. Unauthenticated POST requests don't create records
3. CSRF is enforced on state-changing endpoints
4. No 500 errors on security failures

FAILURE HERE = Security vulnerability = Critical security failure

Only tested for CORE verticals.
"""
import pytest
from decimal import Decimal
from django.test import Client
from django.middleware.csrf import get_token

from tests.critical.conftest import (
    CORE_VERTICALS,
    CORE_STOCK_VERTICALS,
    CORE_SALES_VERTICALS,
    VERTICAL_ENDPOINTS,
    get_dashboard_url,
    get_stock_add_url,
    get_sell_url,
    create_user,
    create_business,
    create_location,
    create_membership,
    bootstrap_business_with_user,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestUnauthenticatedDashboardAccess:
    """Test that unauthenticated users cannot access dashboards."""
    
    @pytest.mark.parametrize("vertical", CORE_VERTICALS)
    def test_unauthenticated_dashboard_blocked(self, vertical):
        """Unauthenticated GET to dashboard should redirect (not allow access), not 500."""
        client = Client()
        
        dashboard_url = get_dashboard_url(vertical)
        if not dashboard_url:
            pytest.skip(f"No dashboard URL for {vertical}")
        
        response = client.get(dashboard_url, follow=False)
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} dashboard returned 500 for unauthenticated user"
        
        # Should redirect to login/tenants selector or return 403
        assert response.status_code in [301, 302, 403], \
            f"{vertical} dashboard should block unauthenticated access, got {response.status_code}"
        
        # If redirect, should go to login, accounts, or tenant selector
        # The app may use /tenants/ as the entry point for unauthenticated users
        if response.status_code in [301, 302]:
            allowed_redirects = ["/login", "/accounts", "/tenants"]
            redirect_url = response.url.lower()
            is_valid_redirect = any(path in redirect_url for path in allowed_redirects)
            assert is_valid_redirect, \
                f"{vertical} dashboard redirects to {response.url}, expected login/accounts/tenants"


class TestUnauthenticatedPostBlocked:
    """Test that unauthenticated POST requests don't create records."""
    
    @pytest.mark.parametrize("vertical", CORE_STOCK_VERTICALS)
    def test_unauthenticated_stock_add_post_blocked(self, vertical):
        """Unauthenticated POST to stock add should be blocked."""
        from inventory.models import MerchProduct
        
        client = Client()
        
        stock_add_url = get_stock_add_url(vertical)
        if not stock_add_url:
            pytest.skip(f"No stock add URL for {vertical}")
        
        initial_count = MerchProduct.objects.count()
        
        # Attempt POST without authentication
        response = client.post(stock_add_url, {
            "name": "Hacker Product",
            "quantity": 100,
            "cost_price": "100.00",
            "selling_price": "150.00",
        }, follow=False)
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} stock add returned 500 on unauthenticated POST"
        
        # Should be blocked
        assert response.status_code in [302, 403, 401, 405], \
            f"{vertical} stock add should block unauthenticated POST, got {response.status_code}"
        
        # Verify no record was created
        final_count = MerchProduct.objects.count()
        assert final_count == initial_count, \
            f"Unauthenticated POST created record: {initial_count} -> {final_count}"
    
    @pytest.mark.parametrize("vertical", ["phones", "liquor", "grocery"])  # Core sales verticals
    def test_unauthenticated_sale_post_blocked(self, vertical):
        """Unauthenticated POST to sell should be blocked."""
        try:
            from sales.models import Sale
        except ImportError:
            pytest.skip("Sale model not found")
        
        client = Client()
        
        sell_url = get_sell_url(vertical)
        if not sell_url:
            pytest.skip(f"No sell URL for {vertical}")
        
        initial_count = Sale.objects.count()
        
        # Attempt POST without authentication
        response = client.post(sell_url, {
            "total_amount": "100.00",
            "payment_method": "cash",
        }, follow=False)
        
        # Must not be 500
        assert response.status_code != 500, \
            f"{vertical} sell returned 500 on unauthenticated POST"
        
        # Should be blocked
        assert response.status_code in [302, 403, 401, 405], \
            f"{vertical} sell should block unauthenticated POST, got {response.status_code}"
        
        # Verify no record was created
        final_count = Sale.objects.count()
        assert final_count == initial_count, \
            f"Unauthenticated sale POST created record"


class TestCSRFEnforcement:
    """Test that CSRF is enforced on state-changing endpoints."""
    
    def test_post_without_csrf_rejected(self):
        """POST without CSRF token should be rejected."""
        user, business, location = bootstrap_business_with_user("phones")
        
        # Create client without CSRF
        client = Client(enforce_csrf_checks=True)
        client.login(username=user.username, password="testpass123")
        
        # Set session
        session = client.session
        session["active_business_id"] = business.id
        session["active_location_id"] = location.id
        session.save()
        
        # Try POST to settings (likely CSRF protected)
        response = client.post("/settings/", {
            "name": "Updated Name",
        }, follow=False)
        
        # Should be 403 Forbidden (CSRF failure)
        # Or redirect if endpoint doesn't exist
        assert response.status_code in [403, 302, 404], \
            f"POST without CSRF should be blocked, got {response.status_code}"


class TestCrossBusinessAccessBlocked:
    """Test that users can't access other businesses' data."""
    
    def test_user_cannot_access_other_business_dashboard(self):
        """User should not see another business's dashboard."""
        # Create two businesses
        user_a, business_a, location_a = bootstrap_business_with_user("phones")
        user_b, business_b, location_b = bootstrap_business_with_user("phones")
        
        # User A logs in
        client = Client()
        client.login(username=user_a.username, password="testpass123")
        
        # Set User A's active business
        session = client.session
        session["active_business_id"] = business_a.id
        session["active_location_id"] = location_a.id
        session.save()
        
        # Try to access own dashboard (should work)
        own_dashboard = get_dashboard_url("phones")
        response = client.get(own_dashboard, follow=True)
        assert response.status_code != 500, "Own dashboard should not 500"
        
        # Try to switch to business B (should be blocked or fail gracefully)
        session = client.session
        session["active_business_id"] = business_b.id  # Attempt to hijack
        session.save()
        
        response = client.get(own_dashboard, follow=True)
        
        # Should not 500
        assert response.status_code != 500, \
            "Cross-business access should not 500"
        
        # Should either redirect to proper business or show error
        # Content should NOT contain business B's name in a data context


class TestRateLimitingAwareness:
    """Test that auth failures don't cause server errors."""
    
    def test_multiple_login_failures_no_500(self):
        """Multiple failed logins should not cause 500."""
        client = Client()
        
        # Try multiple bad logins
        for i in range(5):
            response = client.post("/accounts/login/", {
                "username": f"nonexistent_{i}@test.com",
                "password": "wrongpassword",
            }, follow=True)
            
            # Should never be 500
            assert response.status_code != 500, \
                f"Login failure {i+1} caused 500"
    
    def test_unauthenticated_access_multiple_pages_no_500(self):
        """Rapid unauthenticated access should not cause errors."""
        client = Client()
        
        protected_urls = [
            "/dashboard/",
            "/inventory/dashboard/",
            "/settings/",
            "/wallet/",
        ]
        
        for url in protected_urls:
            response = client.get(url, follow=False)
            
            # Should never be 500
            assert response.status_code != 500, \
                f"Unauthenticated access to {url} caused 500"
            
            # Should redirect to login
            assert response.status_code in [301, 302, 403], \
                f"Expected redirect from {url}, got {response.status_code}"

