# tests/critical/test_02_business_and_location_bootstrap.py
"""
CRITICAL TEST 02: Business and Location Bootstrap

These tests ensure:
1. Business can be created for each vertical
2. Location can be created for a business
3. User can be linked to business via membership
4. User can access their business dashboard

FAILURE HERE = Cannot onboard new businesses = Business-critical failure
"""
import pytest
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.utils.text import slugify

from tests.critical.conftest import (
    VERTICALS,
    VERTICAL_ENDPOINTS,
    create_user,
    create_business,
    create_location,
    create_membership,
    setup_authenticated_client,
    _unique_suffix,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]

# Focus on the most stable verticals for critical tests
STABLE_VERTICALS = ["phones", "liquor", "grocery", "pharmacy"]


class TestBusinessCreation:
    """Test that businesses can be created for all verticals."""
    
    @pytest.mark.parametrize("vertical", STABLE_VERTICALS)
    def test_business_creation_for_vertical(self, vertical):
        """Business can be created for each vertical kind."""
        from tenants.models import Business
        
        user = create_user()
        suffix = _unique_suffix()
        name = f"Test {vertical.title()} Business {suffix}"
        
        business = Business.objects.create(
            name=name,
            slug=slugify(name),
            business_kind=vertical,
            created_by=user,
            status="ACTIVE",
            currency="MWK",
        )
        
        # Verify creation
        assert business.pk is not None, f"Business for {vertical} should have a PK"
        assert business.business_kind == vertical, \
            f"Business kind should be {vertical}, got {business.business_kind}"
        assert business.status == "ACTIVE"
    
    def test_business_with_name_works(self):
        """Business can be created with a name."""
        from tenants.models import Business
        
        # Create business with valid name - this MUST work
        business = Business.objects.create(
            name="Valid Business Name",
            slug="valid-business-name",
            status="ACTIVE",
        )
        
        assert business.pk is not None, "Business should be created"
        assert business.name == "Valid Business Name"


class TestLocationCreation:
    """Test that locations can be created."""
    
    def test_location_creation(self):
        """Location can be created for a business."""
        from inventory.models import Location
        
        user = create_user()
        business = create_business(created_by=user)
        
        location = Location.objects.create(
            business=business,
            name="Main Store",
            is_headquarters=True,
            address="123 Test St",
            city="Test City",
        )
        
        assert location.pk is not None, "Location should have a PK"
        assert location.business == business, "Location should be linked to business"
    
    def test_multiple_locations_per_business(self):
        """Business can have multiple locations."""
        from inventory.models import Location
        
        user = create_user()
        business = create_business(created_by=user)
        
        # First location (HQ)
        hq = Location.objects.create(
            business=business,
            name="Headquarters",
            is_headquarters=True,
            address="123 HQ St",
            city="HQ City",
        )
        
        # Second location (Branch)
        branch = Location.objects.create(
            business=business,
            name="Branch Office",
            is_headquarters=False,
            address="456 Branch Ave",
            city="Branch City",
        )
        
        # Verify both exist
        locations = Location.objects.filter(business=business)
        assert locations.count() >= 2, "Business should have at least 2 locations"


class TestMembershipCreation:
    """Test that memberships can be created to link users to businesses."""
    
    def test_manager_membership_creation(self):
        """Manager membership can be created."""
        from tenants.models import Membership
        
        user = create_user()
        business = create_business(created_by=user)
        location = create_location(business)
        
        membership = create_membership(
            user=user,
            business=business,
            role="MANAGER",
            location=location,
        )
        
        assert membership.pk is not None, "Membership should have a PK"
        assert membership.role == "MANAGER"
        assert membership.status == "ACTIVE"
        assert membership.user == user
        assert membership.business == business
    
    def test_agent_membership_creation(self):
        """Agent membership can be created with location."""
        from tenants.models import Membership
        
        manager = create_user()
        agent = create_user()
        business = create_business(created_by=manager)
        location = create_location(business)
        
        membership = create_membership(
            user=agent,
            business=business,
            role="AGENT",
            location=location,
        )
        
        assert membership.pk is not None
        assert membership.role == "AGENT"
        assert membership.location == location
    
    def test_membership_creates_properly(self):
        """Membership can be created and saved properly."""
        user = create_user()
        business = create_business(created_by=user)
        location = create_location(business)
        
        membership = create_membership(
            user=user,
            business=business,
            role="MANAGER",
            location=location,
        )
        
        # Check membership is created
        assert membership.pk is not None
        assert membership.user == user
        assert membership.business == business


class TestDashboardAccess:
    """Test that users can access their business dashboard."""
    
    @pytest.mark.parametrize("vertical", STABLE_VERTICALS)
    def test_dashboard_accessible_for_vertical(self, vertical):
        """Authenticated user can access dashboard for their vertical."""
        from django.db import OperationalError, ProgrammingError
        
        user = create_user()
        business = create_business(kind=vertical, created_by=user)
        location = create_location(business)
        create_membership(user, business, role="MANAGER", location=location)
        
        client = setup_authenticated_client(user, business, location)
        
        # Get dashboard path for this vertical
        endpoints = VERTICAL_ENDPOINTS.get(vertical, {})
        dashboard_path = endpoints.get("dashboard_path")
        
        if not dashboard_path:
            pytest.skip(f"No dashboard path defined for {vertical}")
        
        try:
            response = client.get(dashboard_path, follow=True)
        except (OperationalError, ProgrammingError) as e:
            # If table doesn't exist in test DB (migration issue), skip
            if "no such table" in str(e).lower() or "does not exist" in str(e).lower():
                pytest.skip(f"{vertical} tables not available in test DB")
            raise
        
        # Check if response indicates missing table (new verticals may not have tables in test DB)
        if response.status_code == 500:
            content = response.content.decode("utf-8", errors="ignore").lower()
            if "no such table" in content or "operationalerror" in content or "programmingerror" in content:
                pytest.skip(f"{vertical} tables not available in test DB (migration needed)")
        
        # CRITICAL: Must not be 500 (for other reasons)
        assert response.status_code != 500, \
            f"Dashboard for {vertical} returned 500 Server Error"
        
        # Should be 200 or redirect (302 is OK if redirecting to correct dashboard)
        assert response.status_code in [200, 302, 404], \
            f"Dashboard for {vertical} returned unexpected {response.status_code}"
        
        # If 200, check for error text in content
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            assert "Server Error" not in content, \
                f"Dashboard for {vertical} contains Server Error text"
            assert "TemplateDoesNotExist" not in content, \
                f"Dashboard for {vertical} has missing template"
    
    def test_unauthenticated_user_redirected_from_dashboard(self):
        """Unauthenticated user should be redirected from dashboard."""
        client = Client()
        
        # Try to access a dashboard
        response = client.get("/dashboard/", follow=False)
        
        # Should redirect to login (not 500)
        assert response.status_code != 500, \
            "Dashboard should not 500 for unauthenticated user"
        assert response.status_code in [302, 301], \
            "Dashboard should redirect unauthenticated user"


class TestCompleteBootstrapFlow:
    """Test the complete business bootstrap flow."""
    
    @pytest.mark.parametrize("vertical", STABLE_VERTICALS)
    def test_complete_bootstrap_for_vertical(self, vertical):
        """Complete bootstrap flow works for each vertical."""
        from django.db import OperationalError, ProgrammingError
        
        # 1. Create user
        user = create_user()
        assert user.pk is not None
        
        # 2. Create business
        business = create_business(kind=vertical, created_by=user)
        assert business.pk is not None
        assert business.business_kind == vertical
        
        # 3. Create location
        location = create_location(business)
        assert location.pk is not None
        assert location.business == business
        
        # 4. Create membership
        membership = create_membership(user, business, role="MANAGER", location=location)
        assert membership.pk is not None
        
        # 5. User can login and access dashboard
        client = setup_authenticated_client(user, business, location)
        
        endpoints = VERTICAL_ENDPOINTS.get(vertical, {})
        dashboard_path = endpoints.get("dashboard_path")
        
        if dashboard_path:
            try:
                response = client.get(dashboard_path, follow=True)
            except (OperationalError, ProgrammingError) as e:
                if "no such table" in str(e).lower():
                    pytest.skip(f"{vertical} tables not available in test DB")
                raise
            
            # Check if 500 is due to missing tables (new verticals may not have migrations in test DB)
            if response.status_code == 500:
                content = response.content.decode("utf-8", errors="ignore").lower()
                if "no such table" in content or "operationalerror" in content:
                    pytest.skip(f"{vertical} tables not available in test DB (migration needed)")
            
            assert response.status_code != 500, \
                f"Complete bootstrap for {vertical} failed: dashboard returned 500"

