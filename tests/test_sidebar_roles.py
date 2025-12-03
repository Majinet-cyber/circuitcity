# tests/test_sidebar_roles.py
"""
Tests for sidebar visibility based on user roles.
Ensures managers see Locations & Admin Wallet, while agents do not.
"""
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import Location

User = get_user_model()


@pytest.fixture
def setup_business_with_roles(db):
    """Create a business with both a manager and an agent."""
    business = Business.objects.create(
        name="Test Sidebar Business",
        slug="test-sidebar-biz",
        status="ACTIVE",
        business_kind="phones",
    )
    
    # Create a location
    location = Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
    )
    
    # Create a manager user
    manager = User.objects.create_user(
        username="testmanager",
        email="manager@test.com",
        password="testpass123",
    )
    
    Membership.objects.create(
        user=manager,
        business=business,
        role="MANAGER",
        status="ACTIVE",
        location=None,  # Managers don't have a specific location
    )
    
    # Create an agent user
    agent = User.objects.create_user(
        username="testagent",
        email="agent@test.com",
        password="testpass123",
    )
    
    Membership.objects.create(
        user=agent,
        business=business,
        role="AGENT",
        status="ACTIVE",
        location=location,
    )
    
    return {
        "business": business,
        "location": location,
        "manager": manager,
        "agent": agent,
    }


@pytest.mark.django_db
class TestSidebarRoleVisibility:
    """Test that sidebar items are shown/hidden based on user role."""
    
    def test_manager_sees_locations_and_admin_wallet(self, setup_business_with_roles, client: Client):
        """Test that managers see Locations and Admin Wallet in the sidebar."""
        data = setup_business_with_roles
        manager = data["manager"]
        business = data["business"]
        
        # Log in as manager
        client.force_login(manager)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET a dashboard page that renders the sidebar
        url = reverse("dashboard:home")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check that the response contains the sidebar items
        content = response.content.decode("utf-8")
        
        # Assert "Locations" appears in the sidebar
        assert "Locations" in content, \
            "Expected 'Locations' to appear in sidebar for manager"
        
        # Assert "Admin Wallet" appears in the sidebar
        assert "Admin Wallet" in content, \
            "Expected 'Admin Wallet' to appear in sidebar for manager"
        
        # Assert "Agents" appears (manager-only)
        assert "Agents" in content, \
            "Expected 'Agents' to appear in sidebar for manager"
    
    def test_agent_does_not_see_locations_and_admin_wallet(self, setup_business_with_roles, client: Client):
        """Test that agents do NOT see Locations and Admin Wallet in the sidebar."""
        data = setup_business_with_roles
        agent = data["agent"]
        business = data["business"]
        
        # Log in as agent
        client.force_login(agent)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET a dashboard page that renders the sidebar
        url = reverse("dashboard:home")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check that the response does NOT contain manager-only items
        content = response.content.decode("utf-8")
        
        # Assert "Locations" does NOT appear in the sidebar
        # (We need to be careful - "Locations" might appear in other contexts)
        # Check for the specific sidebar link pattern
        assert 'href="/tenants/manager/locations/' not in content, \
            "Expected Locations link to NOT appear in sidebar for agent"
        
        # Assert "Admin Wallet" does NOT appear in the sidebar
        assert 'href="/wallet/admin/' not in content, \
            "Expected Admin Wallet link to NOT appear in sidebar for agent"
        
        # Assert "Agents" management does NOT appear
        assert 'href="/tenants/manager/agents/' not in content, \
            "Expected Agents management link to NOT appear in sidebar for agent"
    
    def test_context_processor_provides_is_manager_flag(self, setup_business_with_roles, client: Client):
        """Test that IS_MANAGER flag is correctly set in context."""
        data = setup_business_with_roles
        manager = data["manager"]
        agent = data["agent"]
        business = data["business"]
        
        # Test for manager
        client.force_login(manager)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        url = reverse("dashboard:home")
        response = client.get(url)
        
        assert response.status_code == 200
        assert "IS_MANAGER" in response.context, "IS_MANAGER should be in context"
        assert response.context["IS_MANAGER"] is True, \
            f"Expected IS_MANAGER=True for manager, got {response.context['IS_MANAGER']}"
        
        # Test for agent
        client.force_login(agent)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        response = client.get(url)
        
        assert response.status_code == 200
        assert "IS_MANAGER" in response.context, "IS_MANAGER should be in context"
        assert response.context["IS_MANAGER"] is False, \
            f"Expected IS_MANAGER=False for agent, got {response.context['IS_MANAGER']}"
    
    def test_sidebar_items_have_require_manager_flag(self, setup_business_with_roles, client: Client):
        """Test that sidebar_items in context have require_manager flag."""
        data = setup_business_with_roles
        manager = data["manager"]
        business = data["business"]
        
        # Log in as manager
        client.force_login(manager)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        url = reverse("dashboard:home")
        response = client.get(url)
        
        assert response.status_code == 200
        assert "sidebar_items" in response.context, "sidebar_items should be in context"
        
        sidebar_items = response.context["sidebar_items"]
        assert isinstance(sidebar_items, list), "sidebar_items should be a list"
        
        # Find manager-only items
        manager_items = [
            item for item in sidebar_items
            if item.get("require_manager", False)
        ]
        
        assert len(manager_items) > 0, \
            "Expected at least one item with require_manager=True"
        
        # Check that Locations and Admin Wallet are in manager_items
        manager_labels = [item.get("label") for item in manager_items]
        assert "Locations" in manager_labels, \
            f"Expected 'Locations' in manager items, got {manager_labels}"
        assert "Admin Wallet" in manager_labels, \
            f"Expected 'Admin Wallet' in manager items, got {manager_labels}"

