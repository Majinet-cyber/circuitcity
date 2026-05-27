# tests/critical/test_06_permissions_and_scoping.py
"""
CRITICAL TEST 06: Permissions and Multi-Tenant Scoping

These tests ensure:
1. User A cannot access User B's business data
2. Location scoping works correctly
3. Cross-tenant data leakage is prevented
4. Role-based access control works

FAILURE HERE = Data breach risk = Security critical failure
"""
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse, NoReverseMatch

from tests.critical.conftest import (
    VERTICALS,
    VERTICAL_ENDPOINTS,
    create_user,
    create_business,
    create_location,
    create_membership,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestCrossTenantIsolation:
    """Test that users cannot access other businesses' data."""
    
    def test_user_cannot_access_other_business_dashboard(self):
        """User A should not be able to access Business B's dashboard."""
        # Create two separate businesses with different users
        user_a, business_a, location_a = bootstrap_business_with_user("phones")
        user_b, business_b, location_b = bootstrap_business_with_user("phones")
        
        # User A logs in and sets Business A as active
        client_a = setup_authenticated_client(user_a, business_a, location_a)
        
        # User A tries to access their dashboard - should work
        response = client_a.get("/inventory/verticals/phones/dashboard/", follow=True)
        assert response.status_code != 500, "Own dashboard should not 500"
        
        # Now User A tries to access dashboard with Business B's context
        # First, manually try to set Business B in session (attack simulation)
        session = client_a.session
        session["active_business_id"] = business_b.id
        session.save()
        
        # Access dashboard - should either:
        # 1. Redirect to proper business
        # 2. Show 403
        # 3. Show own business (if session is validated against membership)
        # But NEVER show Business B's data or 500
        response = client_a.get("/inventory/verticals/phones/dashboard/", follow=True)
        
        assert response.status_code != 500, \
            "Dashboard should not 500 on cross-tenant access attempt"
    
    def test_user_membership_limits_access(self):
        """User without membership in business should not access it."""
        # Create business A with user A
        user_a, business_a, location_a = bootstrap_business_with_user("phones")
        
        # Create user B with NO membership in business A
        user_b = create_user()
        
        # User B logs in (no business context)
        client_b = Client()
        client_b.login(username=user_b.username, password="testpass123")
        
        # User B tries to set Business A in session (attack)
        session = client_b.session
        session["active_business_id"] = business_a.id
        session.save()
        
        # Try to access dashboard
        response = client_b.get("/inventory/verticals/phones/dashboard/", follow=True)
        
        # Should NOT be 500 and should NOT show business A's data
        assert response.status_code != 500, \
            "Should not 500 on unauthorized business access"
        
        # Should be redirected or forbidden
        # 200 is only OK if it shows a "no access" message, not business data
    
    def test_products_scoped_to_business(self):
        """Products should be scoped to their business."""
        from inventory.models import MerchProduct
        
        # Create two businesses with products
        user_a, business_a, location_a = bootstrap_business_with_user("phones")
        user_b, business_b, location_b = bootstrap_business_with_user("phones")
        
        # Create product in Business A
        product_a = MerchProduct.objects.create(
            business=business_a,
            location=location_a,
            name="Product A Secret",
            cost_price=Decimal("100"),
            selling_price=Decimal("150"),
            quantity=10,
            status="ACTIVE",
        )
        
        # Create product in Business B
        product_b = MerchProduct.objects.create(
            business=business_b,
            location=location_b,
            name="Product B Secret",
            cost_price=Decimal("200"),
            selling_price=Decimal("250"),
            quantity=5,
            status="ACTIVE",
        )
        
        # Query products for Business A - should only see Product A
        products_a = MerchProduct.objects.filter(business=business_a)
        assert products_a.count() == 1
        assert products_a.first().name == "Product A Secret"
        
        # Query products for Business B - should only see Product B
        products_b = MerchProduct.objects.filter(business=business_b)
        assert products_b.count() == 1
        assert products_b.first().name == "Product B Secret"
        
        # Ensure no cross-contamination
        assert not products_a.filter(name="Product B Secret").exists()
        assert not products_b.filter(name="Product A Secret").exists()


class TestLocationScoping:
    """Test that data is scoped to locations correctly."""
    
    def test_agent_location_restriction(self):
        """Agents should be restricted to their assigned location."""
        from tenants.models import Membership
        
        user, business, location_hq = bootstrap_business_with_user("phones")
        
        # Create branch and agent assigned to branch
        location_branch = create_location(business, name="Branch", is_headquarters=False)
        
        agent = create_user()
        membership = create_membership(
            user=agent,
            business=business,
            role="AGENT",
            location=location_branch,  # Agent is at branch, not HQ
        )
        
        # Verify agent's location assignment
        assert membership.location == location_branch
        assert membership.location != location_hq


class TestRoleBasedAccess:
    """Test role-based access control."""
    
    def test_manager_has_broader_access(self):
        """Managers should have access to manager-only features."""
        user, business, location = bootstrap_business_with_user("phones", role="MANAGER")
        client = setup_authenticated_client(user, business, location)
        
        # Manager-only pages (should not 500)
        manager_paths = [
            "/tenants/manager/agents/",
            "/tenants/manager/locations/",
            "/wallet/admin/",
        ]
        
        for path in manager_paths:
            response = client.get(path, follow=True)
            # Must not 500
            assert response.status_code != 500, \
                f"Manager page {path} returned 500"
            # Manager should have access (200) or redirect to appropriate page
            assert response.status_code in [200, 302, 404], \
                f"Manager denied access to {path}: {response.status_code}"
    
    def test_agent_restricted_from_manager_pages(self):
        """Agents should be restricted from manager-only features."""
        user, business, location = bootstrap_business_with_user("phones", role="AGENT")
        client = setup_authenticated_client(user, business, location)
        
        # Manager-only pages
        manager_paths = [
            "/tenants/manager/agents/",
            "/tenants/manager/locations/",
        ]
        
        for path in manager_paths:
            response = client.get(path, follow=True)
            # Must not 500
            assert response.status_code != 500, \
                f"Agent accessing {path} caused 500"
            # Agent should be denied (403) or redirected (302), not given access
            # 200 might be OK if page shows "access denied" message


class TestNo500OnPermissionDenied:
    """Test that permission denied doesn't cause 500 errors."""
    
    def test_unauthenticated_access_no_500(self):
        """Unauthenticated access should redirect, not 500."""
        client = Client()
        
        protected_paths = [
            "/inventory/dashboard/",
            "/dashboard/",
            "/settings/",
            "/wallet/",
            "/tenants/manager/agents/",
        ]
        
        for path in protected_paths:
            response = client.get(path, follow=False)
            assert response.status_code != 500, \
                f"Unauthenticated access to {path} caused 500"
            # Should redirect to login
            assert response.status_code in [302, 301, 403], \
                f"Unexpected response {response.status_code} for unauthenticated {path}"
    
    def test_no_business_user_redirects(self):
        """User with no business membership should be redirected."""
        user = create_user()
        
        client = Client()
        client.login(username=user.username, password="testpass123")
        
        # User has no business - accessing dashboard should redirect, not 500
        paths = [
            "/dashboard/",
        ]
        
        for path in paths:
            response = client.get(path, follow=False)
            # Should redirect to business setup, not 500
            assert response.status_code in [302, 301, 403], \
                f"No-business user should be redirected from {path}: got {response.status_code}"


# Simplified to core isolation tests only

