# tests/test_inventory_warranty_field.py
"""
Tests for warranty_expiration field on InventoryItem.
Ensures the DB schema matches the model definition (no column mismatch).
"""
import pytest
from datetime import date, timedelta
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Location, Product, InventoryItem

User = get_user_model()


@pytest.fixture
def setup_inventory_item(db):
    """Create a business, location, product, and inventory item."""
    business = Business.objects.create(
        name="Test Warranty Business",
        slug="test-warranty-biz",
        status="ACTIVE",
        business_kind="phones",
    )
    
    location = Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
    )
    
    product = Product.objects.create(
        code="TECNO001",
        name="Tecno Spark 10",
        brand="TECNO",
        model="Spark 10",
        variant="4+64",
        cost_price=100,
        sale_price=150,
    )
    
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    
    return {
        "business": business,
        "location": location,
        "product": product,
        "user": user,
    }


@pytest.mark.django_db
class TestWarrantyExpirationField:
    """Test that warranty_expiration field works correctly."""
    
    def test_warranty_expiration_field_exists(self, setup_inventory_item):
        """Test that warranty_expiration field can be set and retrieved."""
        data = setup_inventory_item
        
        # Create an inventory item with warranty_expiration set
        expiry_date = date.today() + timedelta(days=365)
        
        item = InventoryItem.objects.create(
            business=data["business"],
            product=data["product"],
            current_location=data["location"],
            imei="123456789012345",
            order_price=100,
            selling_price=150,
            warranty_status="in_warranty",
            warranty_expiration=expiry_date,
        )
        
        # Refresh from DB to ensure it was saved correctly
        item.refresh_from_db()
        
        # Assert the field is accessible and matches
        assert item.warranty_expiration == expiry_date, \
            f"Expected warranty_expiration={expiry_date}, got {item.warranty_expiration}"
        
        assert item.warranty_status == "in_warranty", \
            f"Expected warranty_status='in_warranty', got '{item.warranty_status}'"
    
    def test_warranty_expiration_nullable(self, setup_inventory_item):
        """Test that warranty_expiration can be null."""
        data = setup_inventory_item
        
        # Create an item without warranty_expiration
        item = InventoryItem.objects.create(
            business=data["business"],
            product=data["product"],
            current_location=data["location"],
            imei="987654321098765",
            order_price=100,
            selling_price=150,
            warranty_status="unknown",
            warranty_expiration=None,  # Explicitly null
        )
        
        # Refresh from DB
        item.refresh_from_db()
        
        # Assert it's None
        assert item.warranty_expiration is None, \
            f"Expected warranty_expiration=None, got {item.warranty_expiration}"
    
    def test_stock_list_with_warranty_expiration(self, setup_inventory_item, client):
        """Test that stock_list view can query items with warranty_expiration."""
        data = setup_inventory_item
        user = data["user"]
        business = data["business"]
        
        # Create items with and without warranty
        expiry_date = date.today() + timedelta(days=180)
        
        InventoryItem.objects.create(
            business=business,
            product=data["product"],
            current_location=data["location"],
            imei="111111111111111",
            order_price=100,
            selling_price=150,
            warranty_status="in_warranty",
            warranty_expiration=expiry_date,
        )
        
        InventoryItem.objects.create(
            business=business,
            product=data["product"],
            current_location=data["location"],
            imei="222222222222222",
            order_price=100,
            selling_price=150,
            warranty_status="no_warranty",
            warranty_expiration=None,
        )
        
        # Log in and set active business
        client.force_login(user)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        
        # GET stock list (this should NOT raise OperationalError about warranty_expiration)
        from django.urls import reverse
        url = reverse("inventory:stock_list")
        response = client.get(url)
        
        # Assert 200 OK (no DB error)
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}. " \
            f"If this fails with 'no such column: warranty_expiration', run migrations."
        
        # Assert items are in the response
        assert "items" in response.context or "rows" in response.context, \
            "Expected 'items' or 'rows' in context"
    
    def test_warranty_expiration_backward_compat_property(self, setup_inventory_item):
        """Test that warranty_expires_at property still works (backward compat)."""
        data = setup_inventory_item
        
        expiry_date = date.today() + timedelta(days=90)
        
        item = InventoryItem.objects.create(
            business=data["business"],
            product=data["product"],
            current_location=data["location"],
            imei="333333333333333",
            order_price=100,
            warranty_expiration=expiry_date,
        )
        
        # The model defines a @property warranty_expires_at that aliases warranty_expiration
        assert hasattr(item, "warranty_expires_at"), \
            "InventoryItem should have warranty_expires_at property for backward compat"
        
        assert item.warranty_expires_at == expiry_date, \
            f"Expected warranty_expires_at={expiry_date}, got {item.warranty_expires_at}"

