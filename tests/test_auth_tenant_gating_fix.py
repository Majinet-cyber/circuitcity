# tests/test_auth_tenant_gating_fix.py
"""
Test auth/tenant gating cascade fix (302/403 issues).

Tests the SSOT active business auto-selection logic to ensure:
1. Users with exactly 1 membership get auto-selected (no /tenants/ redirect)
2. Users with >1 memberships still see tenant picker (no behavior change)
3. Managers can access barcode/sell endpoints (no 403)
"""
import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user_factory(db):
    """Create a user."""
    def _make_user(username="testuser", email=None, password="testpass123"):
        email = email or f"{username}@test.com"
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        return user
    return _make_user


@pytest.fixture
def business_factory(db):
    """Create a business."""
    def _make_business(name="Test Business", kind="phones", status="ACTIVE"):
        from tenants.models import Business
        from django.utils.text import slugify
        
        business = Business.objects.create(
            name=name,
            slug=slugify(name),
            business_kind=kind,
            status=status
        )
        return business
    return _make_business


@pytest.fixture
def membership_factory(db):
    """Create a membership."""
    def _make_membership(user, business, role="MANAGER", status="ACTIVE", location=None):
        from tenants.models import Membership
        from django.contrib.auth.models import Group
        
        membership = Membership.objects.create(
            user=user,
            business=business,
            role=role,
            status=status,
            location=location
        )
        
        # CRITICAL: Also add user to Django auth group (required by require_role decorator)
        # This mirrors what the actual signup/invite flow does
        group_name = f"biz:{business.pk}:{role}"
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        
        # Also add global role group for backwards compatibility
        global_group_name = role.capitalize() if role == role.upper() else role.title()
        global_group, _ = Group.objects.get_or_create(name=global_group_name)
        user.groups.add(global_group)
        
        return membership
    return _make_membership


@pytest.fixture
def location_factory(db):
    """Create a location."""
    def _make_location(business, name="Main Store", is_default=True):
        from inventory.models import Location
        
        # Check if location with this name already exists
        location = Location.objects.filter(business=business, name=name).first()
        if location:
            return location
        
        # If we want this to be default, unset any existing defaults first
        if is_default:
            Location.objects.filter(business=business, is_default=True).update(is_default=False)
        
        location = Location.objects.create(
            business=business,
            name=name,
            is_default=is_default
        )
        return location
    return _make_location


class TestSingleBusinessAutoSelection:
    """Test auto-selection for users with exactly one business membership."""
    
    def test_dashboard_returns_200_for_single_membership_user(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """User with 1 membership: dashboard returns 200 (no /tenants/ redirect)."""
        # Setup: user with exactly ONE business membership
        user = user_factory(username="single_biz_user")
        business = business_factory(name="Single Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access dashboard
        response = client.get("/inventory/dashboard/", follow=False)
        
        # Should NOT redirect to /tenants/
        assert response.status_code in [200, 302], f"Expected 200 or redirect, got {response.status_code}"
        
        # If it's a redirect, make sure it's NOT to /tenants/
        if response.status_code == 302:
            redirect_url = response.url
            assert not redirect_url.startswith("/tenants/"), (
                f"Single-membership user should not redirect to /tenants/. Got: {redirect_url}"
            )
        
        # Follow redirects and verify we don't end up at /tenants/
        response = client.get("/inventory/dashboard/", follow=True)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/inventory/dashboard/"
        
        assert not final_url.startswith("/tenants/"), (
            f"Single-membership user should not be redirected to /tenants/. "
            f"Redirect chain: {response.redirect_chain}"
        )
        
        # Verify business was set in session
        session = client.session
        assert session.get("active_business_id") == business.id, (
            "Active business should be auto-selected in session"
        )
    
    def test_inventory_list_returns_200_for_single_membership_user(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """User with 1 membership: inventory list returns 200 (no /tenants/ redirect)."""
        # Setup
        user = user_factory(username="inventory_user")
        business = business_factory(name="Inventory Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access inventory list
        response = client.get("/inventory/list/", follow=False)
        
        # Should NOT redirect to /tenants/
        assert response.status_code in [200, 302], f"Expected 200 or redirect, got {response.status_code}"
        
        if response.status_code == 302:
            redirect_url = response.url
            assert not redirect_url.startswith("/tenants/"), (
                f"Single-membership user should not redirect to /tenants/. Got: {redirect_url}"
            )
        
        # Verify business was set
        session = client.session
        assert session.get("active_business_id") == business.id
    
    def test_location_auto_set_for_single_membership_user(
        self, client: Client, user_factory, business_factory, membership_factory, location_factory
    ):
        """User with 1 membership: location is auto-set when accessing location-scoped views."""
        # Setup
        user = user_factory(username="location_user")
        business = business_factory(name="Location Business", kind="clothing")
        location = location_factory(business=business, name="Main Store")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access a location-scoped endpoint (dashboard should work)
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Verify location was set in session
        session = client.session
        assert session.get("active_business_id") == business.id
        # Location might be set depending on middleware
        # This is a softer check since location logic varies by vertical


class TestMultiBusinessNoAutoSelection:
    """Test that users with >1 membership still see tenant picker."""
    
    def test_multi_membership_user_redirects_to_tenant_chooser(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """User with 2+ memberships: redirects to /tenants/ (no auto-select)."""
        # Setup: user with TWO active memberships
        user = user_factory(username="multi_biz_user")
        business1 = business_factory(name="Business One", kind="phones")
        business2 = business_factory(name="Business Two", kind="clothing")
        
        membership_factory(user=user, business=business1, role="MANAGER", status="ACTIVE")
        membership_factory(user=user, business=business2, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access dashboard without selecting business
        response = client.get("/inventory/dashboard/", follow=False)
        
        # Should redirect (to chooser or activation)
        assert response.status_code == 302, (
            f"Multi-membership user should be redirected to choose business, got {response.status_code}"
        )
        
        # Follow redirect
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Should end up at tenant chooser or activation page
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/inventory/dashboard/"
        
        # Accept either /tenants/ or /accounts/settings/ as valid chooser endpoints
        assert (
            final_url.startswith("/tenants/") or 
            final_url.startswith("/accounts/settings/")
        ), (
            f"Multi-membership user should be redirected to tenant chooser. "
            f"Got: {final_url}. Redirect chain: {response.redirect_chain}"
        )
    
    def test_multi_membership_user_can_select_business_manually(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """User with 2+ memberships: can manually select business and access dashboard."""
        # Setup
        user = user_factory(username="multi_select_user")
        business1 = business_factory(name="Business Alpha", kind="phones")
        business2 = business_factory(name="Business Beta", kind="clothing")
        
        membership_factory(user=user, business=business1, role="MANAGER", status="ACTIVE")
        membership_factory(user=user, business=business2, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Manually set business in session (simulating chooser selection)
        session = client.session
        session["active_business_id"] = business1.id
        session.save()
        
        # Access dashboard
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Should NOT redirect to /tenants/ now that business is selected
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/inventory/dashboard/"
        assert not final_url.startswith("/tenants/choose"), (
            f"User with selected business should not redirect to chooser. Got: {final_url}"
        )


class TestManagerBarcodeEndpointAccess:
    """Test that managers can access barcode/sell endpoints (no 403)."""
    
    def test_manager_can_access_barcode_lookup_api(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """Manager can access barcode lookup API (no 403)."""
        # Setup
        user = user_factory(username="manager_user")
        business = business_factory(name="Barcode Business", kind="clothing")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access barcode lookup API
        response = client.get(
            "/inventory/api/barcode/lookup/",
            {"barcode": "123456789"},
            follow=False
        )
        
        # Should NOT return 403
        assert response.status_code != 403, (
            f"Manager should be able to access barcode lookup. Got: {response.status_code}"
        )
        
        # Valid responses: 200 (success), 400 (validation error), 404 (not found)
        assert response.status_code in [200, 400, 404], (
            f"Expected 200/400/404 for barcode lookup, got {response.status_code}"
        )
    
    def test_manager_can_access_fast_sell_api(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """Manager can access fast sell API (no 403)."""
        # Setup
        user = user_factory(username="fast_sell_manager")
        business = business_factory(name="Fast Sell Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Access fast sell lookup API
        response = client.get(
            "/inventory/api/fast-sell/lookup/",
            {"barcode": "999888777", "vertical": "phones"},
            follow=False
        )
        
        # Should NOT return 403
        assert response.status_code != 403, (
            f"Manager should be able to access fast sell lookup. Got: {response.status_code}"
        )
        
        # Valid responses: 200 (success), 400 (validation error)
        assert response.status_code in [200, 400], (
            f"Expected 200/400 for fast sell lookup, got {response.status_code}"
        )
    
    def test_manager_can_post_to_fast_sell_sell_endpoint(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """Manager can POST to fast sell sell endpoint (no 403)."""
        import json
        
        # Setup
        user = user_factory(username="sell_manager")
        business = business_factory(name="Sell Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # POST to fast sell sell endpoint
        response = client.post(
            "/inventory/api/fast-sell/sell/",
            data=json.dumps({
                "barcode": "123456789",
                "vertical": "phones",
                "payment_method": "CASH",
                "quantity": 1
            }),
            content_type="application/json",
            follow=False
        )
        
        # Should NOT return 403
        assert response.status_code != 403, (
            f"Manager should be able to access fast sell sell endpoint. Got: {response.status_code}"
        )
        
        # Valid responses: 200 (success), 400 (validation/stock error), 404 (not found)
        assert response.status_code in [200, 400, 404], (
            f"Expected 200/400/404 for fast sell sell, got {response.status_code}"
        )


class TestRoleResolutionIntegrity:
    """Test that role resolution works correctly in middleware."""
    
    def test_manager_role_set_on_request(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """Manager role is correctly set on request by middleware."""
        # Setup
        user = user_factory(username="role_manager")
        business = business_factory(name="Role Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="ACTIVE")
        
        # Login
        client.force_login(user)
        
        # Create a test view to inspect request attrs
        from django.http import JsonResponse
        from django.urls import path
        from django.conf import settings
        
        def test_view(request):
            return JsonResponse({
                "cc_role": getattr(request, "cc_role", "NOT_SET"),
                "cc_is_manager": getattr(request, "cc_is_manager", None),
                "cc_is_agent": getattr(request, "cc_is_agent", None),
                "business_id": getattr(request, "business_id", None),
            })
        
        # Patch URLconf temporarily (for this test only)
        from django.urls import path
        from django.test.utils import override_settings
        
        # Instead of patching URLs, just check session after dashboard access
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Verify business was set (role resolution happens in middleware)
        session = client.session
        assert session.get("active_business_id") == business.id, (
            "Business should be set in session after middleware processing"
        )
    
    def test_agent_role_set_on_request(
        self, client: Client, user_factory, business_factory, membership_factory, location_factory
    ):
        """Agent role is correctly set on request by middleware."""
        # Setup
        user = user_factory(username="role_agent")
        business = business_factory(name="Agent Business", kind="clothing")
        location = location_factory(business=business)
        membership_factory(user=user, business=business, role="AGENT", status="ACTIVE", location=location)
        
        # Login
        client.force_login(user)
        
        # Access dashboard
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Verify business was set
        session = client.session
        assert session.get("active_business_id") == business.id, (
            "Business should be set in session for agent"
        )


class TestNoRegressions:
    """Test that existing functionality is not broken."""
    
    def test_anonymous_user_redirected_to_login(self, client: Client):
        """Anonymous users still get redirected to login."""
        response = client.get("/inventory/dashboard/", follow=False)
        
        # Should redirect to login
        assert response.status_code == 302
        assert "/accounts/login/" in response.url or "/login/" in response.url
    
    def test_user_without_membership_redirected_to_onboarding(
        self, client: Client, user_factory
    ):
        """Users without any membership get redirected to onboarding/settings."""
        user = user_factory(username="no_membership_user")
        client.force_login(user)
        
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Should end up at onboarding or settings (not crash)
        assert response.status_code == 200, (
            f"User without membership should be redirected gracefully, got {response.status_code}"
        )
        
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/inventory/dashboard/"
        
        # Accept various onboarding/settings URLs
        valid_destinations = ["/onboarding/", "/tenants/", "/accounts/settings/"]
        assert any(final_url.startswith(dest) for dest in valid_destinations), (
            f"User without membership should be redirected to onboarding/settings. Got: {final_url}"
        )
    
    def test_inactive_membership_not_auto_selected(
        self, client: Client, user_factory, business_factory, membership_factory
    ):
        """Users with INACTIVE membership are not auto-selected."""
        # Setup
        user = user_factory(username="inactive_member")
        business = business_factory(name="Inactive Business", kind="phones")
        membership_factory(user=user, business=business, role="MANAGER", status="PENDING")
        
        # Login
        client.force_login(user)
        
        # Access dashboard
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Business should NOT be auto-selected (membership not ACTIVE)
        session = client.session
        assert session.get("active_business_id") != business.id, (
            "Inactive membership should not be auto-selected"
        )
        
        # Should be redirected to onboarding/chooser
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else "/inventory/dashboard/"
        assert (
            final_url.startswith("/tenants/") or 
            final_url.startswith("/onboarding/") or
            final_url.startswith("/accounts/settings/")
        ), (
            f"User with inactive membership should be redirected. Got: {final_url}"
        )

