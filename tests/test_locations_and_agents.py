# tests/test_locations_and_agents.py
"""
Tests for location-based scoping and agent management.
Ensures agents only see their location's data, and managers see all locations.
"""
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import Location, Product, InventoryItem

User = get_user_model()


@pytest.fixture
def setup_multi_location_business(db):
    """Create a business with multiple locations and agents."""
    business = Business.objects.create(
        name="Spears",
        slug="spears",
        status="ACTIVE",
        business_kind="phones",
    )
    
    # Create two locations
    location1 = Location.objects.create(
        business=business,
        name="Spears Main",
        is_default=True,
    )
    
    location2 = Location.objects.create(
        business=business,
        name="Spears Mchinji branch",
        is_default=False,
    )
    
    # Create a manager (no specific location)
    manager = User.objects.create_user(
        username="manager",
        email="manager@spears.com",
        password="testpass123",
    )
    
    Membership.objects.create(
        user=manager,
        business=business,
        role="MANAGER",
        status="ACTIVE",
        location=None,
    )
    
    # Create agent for location 1
    agent1 = User.objects.create_user(
        username="agent1",
        email="agent1@spears.com",
        password="testpass123",
    )
    
    Membership.objects.create(
        user=agent1,
        business=business,
        role="AGENT",
        status="ACTIVE",
        location=location1,
    )
    
    # Create agent for location 2
    agent2 = User.objects.create_user(
        username="agent2",
        email="agent2@spears.com",
        password="testpass123",
    )
    
    Membership.objects.create(
        user=agent2,
        business=business,
        role="AGENT",
        status="ACTIVE",
        location=location2,
    )
    
    # Create a product
    product = Product.objects.create(
        code="TEST001",
        name="Test Phone",
        brand="TestBrand",
        model="TestModel",
        variant="4+64",
        cost_price=100,
        sale_price=150,
    )
    
    return {
        "business": business,
        "location1": location1,
        "location2": location2,
        "manager": manager,
        "agent1": agent1,
        "agent2": agent2,
        "product": product,
    }


@pytest.mark.django_db
class TestLocationScoping:
    """Test that agents only see their location's stock."""
    
    def test_agent_sees_only_their_location_stock(self, setup_multi_location_business, client: Client):
        """Test that agent1 only sees stock from location1."""
        data = setup_multi_location_business
        agent1 = data["agent1"]
        business = data["business"]
        location1 = data["location1"]
        location2 = data["location2"]
        product = data["product"]
        
        # Create stock in both locations
        item_loc1 = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location1,
            imei="111111111111111",
            order_price=100,
            selling_price=150,
        )
        
        item_loc2 = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location2,
            imei="222222222222222",
            order_price=100,
            selling_price=150,
        )
        
        # Log in as agent1
        client.force_login(agent1)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET stock list
        url = reverse("inventory:stock_list")
        response = client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Get items from context
        items = response.context.get("items") or response.context.get("rows") or []
        
        # Agent1 should only see item from location1
        item_ids = [item.id for item in items]
        assert item_loc1.id in item_ids, \
            f"Expected agent1 to see item from location1 (ID {item_loc1.id})"
        assert item_loc2.id not in item_ids, \
            f"Expected agent1 to NOT see item from location2 (ID {item_loc2.id})"
    
    def test_manager_sees_all_locations_stock(self, setup_multi_location_business, client: Client):
        """Test that manager sees stock from all locations."""
        data = setup_multi_location_business
        manager = data["manager"]
        business = data["business"]
        location1 = data["location1"]
        location2 = data["location2"]
        product = data["product"]
        
        # Create stock in both locations
        item_loc1 = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location1,
            imei="111111111111111",
            order_price=100,
            selling_price=150,
        )
        
        item_loc2 = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location2,
            imei="222222222222222",
            order_price=100,
            selling_price=150,
        )
        
        # Log in as manager
        client.force_login(manager)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET stock list
        url = reverse("inventory:stock_list")
        response = client.get(url)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Get items from context
        items = response.context.get("items") or response.context.get("rows") or []
        
        # Manager should see items from both locations
        item_ids = [item.id for item in items]
        assert item_loc1.id in item_ids, \
            f"Expected manager to see item from location1 (ID {item_loc1.id})"
        assert item_loc2.id in item_ids, \
            f"Expected manager to see item from location2 (ID {item_loc2.id})"
    
    def test_location_display_name_format(self, setup_multi_location_business):
        """Test that location.display_name returns 'BusinessName · LocationName'."""
        data = setup_multi_location_business
        location1 = data["location1"]
        location2 = data["location2"]
        
        # Test display_name property
        assert hasattr(location1, "display_name"), \
            "Location should have display_name property"
        
        expected1 = "Spears · Spears Main"
        assert location1.display_name == expected1, \
            f"Expected display_name='{expected1}', got '{location1.display_name}'"
        
        expected2 = "Spears · Spears Mchinji branch"
        assert location2.display_name == expected2, \
            f"Expected display_name='{expected2}', got '{location2.display_name}'"
    
    def test_agent_membership_requires_location(self, setup_multi_location_business):
        """Test that creating an agent membership without a location raises ValidationError."""
        data = setup_multi_location_business
        business = data["business"]
        
        # Create a new user
        user = User.objects.create_user(
            username="newagent",
            email="newagent@test.com",
            password="testpass123",
        )
        
        # Try to create an agent membership without a location
        from django.core.exceptions import ValidationError
        
        membership = Membership(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE",
            location=None,  # Missing location
        )
        
        with pytest.raises(ValidationError) as exc_info:
            membership.full_clean()
        
        # Assert the error is about location
        assert "location" in exc_info.value.message_dict, \
            f"Expected ValidationError for 'location', got {exc_info.value.message_dict}"
    
    def test_manager_membership_does_not_require_location(self, setup_multi_location_business):
        """Test that managers can have membership without a specific location."""
        data = setup_multi_location_business
        business = data["business"]
        
        # Create a new manager user
        user = User.objects.create_user(
            username="newmanager",
            email="newmanager@test.com",
            password="testpass123",
        )
        
        # Create a manager membership without a location (should be valid)
        membership = Membership(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None,  # OK for managers
        )
        
        # Should not raise ValidationError
        membership.full_clean()
        membership.save()
        
        assert membership.id is not None, "Membership should be saved successfully"
        assert membership.location is None, "Manager membership should not have a location"


@pytest.mark.django_db
class TestManagerLocationViews:
    """Test manager location management views."""
    
    def test_manager_can_access_locations_list(self, setup_multi_location_business, client: Client):
        """Test that managers can access the locations list page."""
        data = setup_multi_location_business
        manager = data["manager"]
        business = data["business"]
        
        # Log in as manager
        client.force_login(manager)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET locations list
        url = reverse("tenants:manager_locations")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}"
        
        # Assert both locations are visible
        content = response.content.decode("utf-8")
        assert "Spears Main" in content, \
            "Expected 'Spears Main' to appear in locations list"
        assert "Spears Mchinji branch" in content, \
            "Expected 'Spears Mchinji branch' to appear in locations list"
    
    def test_agent_cannot_access_locations_list(self, setup_multi_location_business, client: Client):
        """Test that agents cannot access the manager locations page."""
        data = setup_multi_location_business
        agent1 = data["agent1"]
        business = data["business"]
        
        # Log in as agent
        client.force_login(agent1)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # Try to GET locations list
        url = reverse("tenants:manager_locations")
        response = client.get(url)
        
        # Assert redirect or 403 (not 200)
        assert response.status_code in [302, 403], \
            f"Expected 302 or 403 for agent accessing manager page, got {response.status_code}"

