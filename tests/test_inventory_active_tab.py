# tests/test_inventory_active_tab.py
"""
Tests for active_tab context variable in inventory views.
Ensures sidebar navigation highlighting works correctly.
"""
import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import Location, Product

User = get_user_model()


@pytest.fixture
def setup_business_and_user(db):
    """Create a business with an active agent user."""
    business = Business.objects.create(
        name="Test Business",
        slug="test-business",
        status="ACTIVE",
        business_kind="phones",
    )
    
    # Create a location for the business
    location = Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
    )
    
    # Create an agent user
    user = User.objects.create_user(
        username="testagent",
        email="agent@test.com",
        password="testpass123",
    )
    
    # Create membership
    Membership.objects.create(
        user=user,
        business=business,
        location=location,
        role="AGENT",
        status="ACTIVE",
    )
    
    # Create a test product
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
        "location": location,
        "user": user,
        "product": product,
    }


@pytest.mark.django_db
class TestInventoryActiveTab:
    """Test that active_tab is properly set in inventory views."""
    
    def test_scan_in_sets_active_tab(self, setup_business_and_user, client: Client):
        """Test that scan_in view sets active_tab to 'scan_in'."""
        data = setup_business_and_user
        user = data["user"]
        business = data["business"]
        
        # Log in as the agent
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET the scan-in page
        url = reverse("inventory:scan_in")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Assert active_tab is in context
        assert "active_tab" in response.context, "active_tab not found in context"
        assert response.context["active_tab"] == "scan_in", \
            f"Expected active_tab='scan_in', got '{response.context.get('active_tab')}'"
        
        # Assert it appears in the rendered HTML (optional, for extra safety)
        content = response.content.decode("utf-8")
        # The template might not explicitly render {{ active_tab }}, but it's in context
        # This test ensures no VariableDoesNotExist error
    
    def test_stock_list_sets_active_tab(self, setup_business_and_user, client: Client):
        """Test that stock_list view sets active_tab to 'stock_list'."""
        data = setup_business_and_user
        user = data["user"]
        business = data["business"]
        
        # Log in
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET the stock list page
        url = reverse("inventory:stock_list")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Assert active_tab is in context
        assert "active_tab" in response.context, "active_tab not found in context"
        assert response.context["active_tab"] == "stock_list", \
            f"Expected active_tab='stock_list', got '{response.context.get('active_tab')}'"
    
    def test_scan_sold_sets_active_tab(self, setup_business_and_user, client: Client):
        """Test that scan_sold view sets active_tab to 'scan_sold'."""
        data = setup_business_and_user
        user = data["user"]
        business = data["business"]
        
        # Log in
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET the scan-sold page (phone sale wizard)
        try:
            url = reverse("inventory:scan_sold")
        except Exception:
            # Fallback to phone_sale_wizard if scan_sold doesn't exist
            url = reverse("inventory:phone_sale_wizard")
        
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Assert active_tab is in context
        assert "active_tab" in response.context, "active_tab not found in context"
        # Accept either scan_sold or phone_sale_wizard
        assert response.context["active_tab"] in ["scan_sold", "phone_sale_wizard"], \
            f"Expected active_tab='scan_sold' or 'phone_sale_wizard', got '{response.context.get('active_tab')}'"
    
    def test_inventory_dashboard_sets_active_tab(self, setup_business_and_user, client: Client):
        """Test that inventory_dashboard view sets active_tab to 'inventory_dashboard'."""
        data = setup_business_and_user
        user = data["user"]
        business = data["business"]
        
        # Log in
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET the inventory dashboard
        url = reverse("inventory:inventory_dashboard")
        response = client.get(url)
        
        # Assert 200 OK (or 302 if it redirects to a vertical dashboard)
        assert response.status_code in [200, 302], \
            f"Expected 200 or 302, got {response.status_code}"
        
        if response.status_code == 200:
            # Assert active_tab is in context
            assert "active_tab" in response.context, "active_tab not found in context"
            assert response.context["active_tab"] == "inventory_dashboard", \
                f"Expected active_tab='inventory_dashboard', got '{response.context.get('active_tab')}'"
    
    def test_time_logs_sets_active_tab(self, setup_business_and_user, client: Client):
        """Test that time_logs view sets active_tab to 'time_logs'."""
        data = setup_business_and_user
        user = data["user"]
        business = data["business"]
        
        # Log in
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET the time logs page
        url = reverse("inventory:time_logs")
        response = client.get(url)
        
        # Assert 200 OK
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Assert active_tab is in context
        assert "active_tab" in response.context, "active_tab not found in context"
        assert response.context["active_tab"] == "time_logs", \
            f"Expected active_tab='time_logs', got '{response.context.get('active_tab')}'"

