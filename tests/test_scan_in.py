# tests/test_scan_in.py
"""
Comprehensive tests for Scan IN functionality with duplicate IMEI prevention.

Tests cover:
- Valid phone unit creation
- Duplicate IMEI rejection (in stock and sold)
- Invalid IMEI format validation
- Location defaulting
- PhoneProductCatalog integration
- Dashboard stock count consistency
"""
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import InventoryItem, Location, Product
from inventory.models_phone_products import PhoneProductCatalog
from tenants.models import Business
from tenants.models import Business


# Helper to set active business in session
def set_active_business(client, business):
    """Set active business in client session."""
    session = client.session
    session["active_business_id"] = business.id
    session["business_id"] = business.id
    session.save()

User = get_user_model()


@pytest.fixture
def business():
    """Create a test phones business"""
    from conftest import unique_slug
    return Business.objects.create(
        name="Test Phone Store",
        slug=unique_slug("Test Phone Store"),
        status="ACTIVE",
        business_kind=BusinessKind.PHONES
    )


@pytest.fixture
def location(business):
    """Create a test location"""
    return Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True
    )


@pytest.fixture
def agent(business, location):
    """Create an agent user with profile"""
    user = User.objects.create_user(username="agent_test", password="pass123")
    user.is_staff = False
    user.save()
    
    # Create/update agent profile with location (idempotent)
    try:
        from inventory.models import AgentProfile
        agent_profile, _ = AgentProfile.objects.get_or_create(user=user)
        if agent_profile.location != location:
            agent_profile.location = location
            agent_profile.save(update_fields=["location"])
    except Exception:
        pass  # AgentProfile may not exist in all setups
    
    return user


@pytest.fixture
def phone_catalog(business):
    """Create a PhoneProductCatalog entry"""
    return PhoneProductCatalog.objects.create(
        business=business,
        brand="TECNO",
        model_name="Spark 40",
        ram_gb=4,
        rom_gb=128,
        variant_label="4+128",
        default_cost_price=Decimal("450000.00"),
        default_selling_price=Decimal("550000.00"),
        is_active=True
    )


@pytest.fixture
def generic_product(business):
    """Create a generic Product for non-catalog items"""
    return Product.objects.create(
        code="PHONE-GENERIC",
        name="Generic Phone",
        brand="Generic",
        model="Unknown",
        cost_price=Decimal("300000.00"),
        sale_price=Decimal("400000.00")
    )


@pytest.fixture
def client_with_business(client, business):
    """Client with active business set"""
    set_active_business(business)
    return client


@pytest.mark.django_db
class TestScanInCreatePhoneUnit:
    """Test successful phone unit creation via Scan IN"""
    
    def test_scan_in_creates_phone_unit(self, client, agent, business, location, phone_catalog):
        """Test creating a phone unit with valid IMEI and catalog product"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "123456789012345",
            "phone_catalog_id": phone_catalog.id,
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["ok"] is True
        assert json_data["created"] is True
        assert json_data["imei"] == "123456789012345"
        
        # Verify item was created
        item = InventoryItem.objects.get(business=business, imei="123456789012345")
        assert item.status == "IN_STOCK"
        assert item.is_active is True
        assert item.current_location == location
        assert item.order_price == Decimal("450000.00")  # From catalog default_cost_price
        assert item.received_at == date.today()
    
    def test_scan_in_with_explicit_order_price(self, client, agent, business, location, phone_catalog):
        """Test that explicit order_price overrides catalog default"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "111111111111111",
            "phone_catalog_id": phone_catalog.id,
            "location_id": location.id,
            "order_price": "500000.00",
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 200
        item = InventoryItem.objects.get(business=business, imei="111111111111111")
        assert item.order_price == Decimal("500000.00")  # Explicit price used
    
    def test_scan_in_with_generic_product(self, client, agent, business, location, generic_product):
        """Test scan in with generic Product (non-catalog)"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "222222222222222",
            "product_id": generic_product.id,
            "location_id": location.id,
            "order_price": "300000.00",
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 200
        item = InventoryItem.objects.get(business=business, imei="222222222222222")
        assert item.product == generic_product
        assert item.status == "IN_STOCK"


@pytest.mark.django_db
class TestScanInRejectsDuplicateIMEI:
    """Test duplicate IMEI rejection logic"""
    
    def test_scan_in_rejects_duplicate_imei_in_stock(self, client, agent, business, location, phone_catalog):
        """Test that scanning the same IMEI twice is rejected (both in stock)"""
        client.force_login(agent)
        set_active_business(client, business)
        
        # Create first item
        InventoryItem.objects.create(
            business=business,
            imei="999999999999999",
            product_id=None,
            order_price=Decimal("450000.00"),
            status="IN_STOCK",
            current_location=location,
            is_active=True
        )
        
        # Try to scan same IMEI again
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "999999999999999",
            "phone_catalog_id": phone_catalog.id,
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 400
        json_data = response.json()
        assert json_data["ok"] is False
        assert "already exists" in json_data["error"].lower()
        assert "never stock the same device twice" in json_data["error"].lower()
        
        # Verify no duplicate was created
        count = InventoryItem.objects.filter(business=business, imei="999999999999999").count()
        assert count == 1
    
    def test_scan_in_rejects_duplicate_imei_even_if_sold(self, client, agent, business, location, phone_catalog):
        """Test that duplicate IMEI is rejected even if original item was sold"""
        client.force_login(agent)
        set_active_business(client, business)
        
        # Create and sell an item
        from django.utils import timezone
        InventoryItem.objects.create(
            business=business,
            imei="888888888888888",
            product_id=None,
            order_price=Decimal("450000.00"),
            status="SOLD",
            current_location=location,
            is_active=True,
            sold_at=timezone.now()
        )
        
        # Try to scan same IMEI (even though original is sold)
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "888888888888888",
            "phone_catalog_id": phone_catalog.id,
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 400
        json_data = response.json()
        assert json_data["ok"] is False
        assert "already exists" in json_data["error"].lower()
        assert json_data["existing_status"] == "SOLD"
        
        # Verify no duplicate created
        count = InventoryItem.objects.filter(business=business, imei="888888888888888").count()
        assert count == 1


@pytest.mark.django_db
class TestScanInInvalidIMEI:
    """Test IMEI format validation"""
    
    def test_scan_in_rejects_short_imei(self, client, agent, business, location):
        """Test rejection of IMEI shorter than 15 digits"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "12345",  # Too short
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 400
        json_data = response.json()
        assert "15 digits" in json_data["error"].lower()
    
    def test_scan_in_rejects_long_imei(self, client, agent, business, location):
        """Test rejection of IMEI longer than 15 digits"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "1234567890123456",  # Too long
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 400
        json_data = response.json()
        assert "15 digits" in json_data["error"].lower()
    
    def test_scan_in_rejects_non_numeric_imei(self, client, agent, business, location):
        """Test rejection of IMEI containing non-numeric characters"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "12345678901234A",  # Contains letter
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 400
        json_data = response.json()
        assert "15 digits" in json_data["error"].lower()


@pytest.mark.django_db
class TestScanInLocationDefaults:
    """Test location defaulting behavior"""
    
    def test_scan_in_defaults_to_agent_location(self, client, agent, business, location):
        """Test that location defaults to agent's assigned store"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "777777777777777",
            "order_price": "400000.00",
            # No location_id provided
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 200
        item = InventoryItem.objects.get(business=business, imei="777777777777777")
        # Should default to the location (Main Store with is_default=True)
        assert item.current_location == location
    
    def test_scan_in_respects_explicit_location(self, client, agent, business, location):
        """Test that explicit location_id is respected"""
        # Create a second location
        location2 = Location.objects.create(
            business=business,
            name="Branch Store"
        )
        
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "666666666666666",
            "location_id": location2.id,
            "order_price": "400000.00",
        }
        
        response = client.post(url, data, content_type="application/json")
        
        assert response.status_code == 200
        item = InventoryItem.objects.get(business=business, imei="666666666666666")
        assert item.current_location == location2


@pytest.mark.django_db
class TestScanInDashboardConsistency:
    """Test that dashboard stock counts remain consistent"""
    
    def test_dashboard_stock_count_includes_scanned_phones(self, client, agent, business, location, phone_catalog):
        """Test that scanned phones appear in stock count"""
        client.force_login(agent)
        set_active_business(client, business)
        
        url = reverse("inventory:api_scan_in")
        
        # Scan in 3 phones
        for i in range(3):
            data = {
                "imei": f"55555555555555{i}",
                "phone_catalog_id": phone_catalog.id,
                "location_id": location.id,
            }
            response = client.post(url, data, content_type="application/json")
            assert response.status_code == 200
        
        # Verify stock count
        in_stock_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        
        assert in_stock_count == 3
    
    def test_stock_count_decreases_after_sale(self, client, agent, business, location):
        """Test that selling a phone reduces stock count"""
        client.force_login(agent)
        set_active_business(client, business)
        
        # Scan in a phone
        item = InventoryItem.objects.create(
            business=business,
            imei="444444444444444",
            product_id=None,
            order_price=Decimal("450000.00"),
            status="IN_STOCK",
            current_location=location,
            is_active=True
        )
        
        initial_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        assert initial_count == 1
        
        # Mark as sold (simulating Phone Sale Wizard behavior)
        from django.utils import timezone
        item.status = "SOLD"
        item.sold_at = timezone.now()
        item.save()
        
        # Verify stock count decreased
        remaining_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        assert remaining_count == 0
        
        # Verify sold count increased
        sold_count = InventoryItem.objects.filter(
            business=business,
            status="SOLD"
        ).count()
        assert sold_count == 1


@pytest.mark.django_db
class TestScanInIntegration:
    """Integration tests for complete Scan IN → Sale flow"""
    
    def test_complete_scan_and_sell_flow(self, client, agent, business, location, phone_catalog):
        """Test: Scan IN → Verify stock → Sell → Verify counts"""
        client.force_login(agent)
        set_active_business(client, business)
        
        # Step 1: Scan in a phone
        url = reverse("inventory:api_scan_in")
        data = {
            "imei": "333333333333333",
            "phone_catalog_id": phone_catalog.id,
            "location_id": location.id,
        }
        
        response = client.post(url, data, content_type="application/json")
        assert response.status_code == 200
        
        # Step 2: Verify it's in stock
        item = InventoryItem.objects.get(business=business, imei="333333333333333")
        assert item.status == "IN_STOCK"
        
        # Step 3: Sell it (simulating Phone Sale Wizard)
        from django.utils import timezone
        item.status = "SOLD"
        item.selling_price = Decimal("550000.00")
        item.sold_at = timezone.now()
        item.assigned_agent = agent
        item.save()
        
        # Step 4: Verify stock/sold counts
        assert InventoryItem.objects.filter(business=business, status="IN_STOCK").count() == 0
        assert InventoryItem.objects.filter(business=business, status="SOLD").count() == 1
        
        # Step 5: Try to scan the same IMEI again (should be rejected)
        response = client.post(url, data, content_type="application/json")
        assert response.status_code == 400
        assert "already exists" in response.json()["error"].lower()
