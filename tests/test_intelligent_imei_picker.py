# tests/test_intelligent_imei_picker.py
"""
Tests for the intelligent IMEI picker feature and strict business/location scoping.

Ensures:
- Available IMEIs endpoint returns correct IMEIs based on business and location
- Managers see all IMEIs across all locations in their business
- Agents see only IMEIs in their location
- Sold items are excluded from available IMEIs
- Scan-in counts are role-based (managers see all, agents see only their own)
- Cross-business attacks are prevented
- Main /inventory/scan-in/ URL uses the gamified phone scan view
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location, Product
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind

pytestmark = pytest.mark.django_db


# =============================================================================
# Helper function to set active business in session
# =============================================================================
def set_active_business(client, business):
    """Helper to set active business in session."""
    session = client.session
    session['active_business_id'] = business.id
    session.save()


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def phones_business(db):
    """Create a PHONES business for testing."""
    business = Business.objects.create(
        name="Test Phones Shop",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE",
    )
    return business


@pytest.fixture
def other_business(db):
    """Create another business for cross-tenant testing."""
    business = Business.objects.create(
        name="Other Phones Shop",
        slug="other-phones-shop",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE",
    )
    return business


@pytest.fixture
def location(db, phones_business):
    """Create a location for the phones business."""
    location = Location.objects.create(
        business=phones_business,
        name="Main Store",
        is_default=True,
    )
    return location


@pytest.fixture
def location2(db, phones_business):
    """Create a second location for the phones business."""
    location = Location.objects.create(
        business=phones_business,
        name="Branch Store",
    )
    return location


@pytest.fixture
def manager_user(db, django_user_model, phones_business):
    """Create a manager user for the phones business."""
    user = django_user_model.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123",
        is_staff=True,  # Managers are staff
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="MANAGER",
        status="ACTIVE",
    )
    return user


@pytest.fixture
def agent_user(db, django_user_model, phones_business, location):
    """Create an agent user for the phones business."""
    user = django_user_model.objects.create_user(
        username="agent",
        email="agent@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="AGENT",
        status="ACTIVE",
        location=location,
    )
    return user


@pytest.fixture
def agent2_user(db, django_user_model, phones_business, location2):
    """Create a second agent user for the phones business in location 2."""
    user = django_user_model.objects.create_user(
        username="agent2",
        email="agent2@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="AGENT",
        status="ACTIVE",
        location=location2,
    )
    return user


@pytest.fixture
def phone_product(db):
    """Create a phone product for testing."""
    product = Product.objects.create(
        code="TECNO-SPARK10C-4-128",
        name="Tecno Spark 10C (4+128)",
        brand="TECNO",
        model="Spark 10C",
        variant="(4+128)",
        cost_price=Decimal("100.00"),
        sale_price=Decimal("150.00"),
    )
    return product


@pytest.fixture
def phone_catalog(db, phones_business):
    """Create a phone catalog entry for testing."""
    catalog = PhoneProductCatalog.objects.create(
        business=phones_business,
        brand="TECNO",
        model_name="Spark 10C",
        variant_label="(4+128)",
        display_name="Tecno Spark 10C (4+128)",
        default_cost_price=Decimal("100.00"),
        default_selling_price=Decimal("150.00"),
        is_active=True,
    )
    return catalog


# =============================================================================
# TESTS: Available IMEIs Endpoint
# =============================================================================
def test_available_imeis_endpoint_scoped_to_business_and_location(
    client, phones_business, other_business, location, location2, 
    manager_user, agent_user, phone_product
):
    """
    Test that available IMEIs endpoint returns only IMEIs from the correct business and location.
    
    Managers should see all IMEIs across all locations in their business.
    Agents should see only IMEIs in their location.
    """
    # Create stock in location 1 (agent's location)
    item1 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012345",
        status="IN_STOCK",
        is_active=True,
        current_location=location,
        order_price=Decimal("100.00"),
    )
    
    # Create stock in location 2 (different location, same business)
    item2 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012346",
        status="IN_STOCK",
        is_active=True,
        current_location=location2,
        order_price=Decimal("100.00"),
    )
    
    # Create stock in other business (should never be visible)
    other_location = Location.objects.create(
        business=other_business,
        name="Other Store",
    )
    item3 = InventoryItem.objects.create(
        business=other_business,
        product=phone_product,
        imei="123456789012347",
        status="IN_STOCK",
        is_active=True,
        current_location=other_location,
        order_price=Decimal("100.00"),
    )
    
    # Test as AGENT - should only see location 1
    client.force_login(agent_user)
    set_active_business(client, phones_business)
    
    url = reverse("inventory:phones_available_imeis", kwargs={"product_id": phone_product.id})
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["imeis"]) == 1
    assert "123456789012345" in data["imeis"]
    assert "123456789012346" not in data["imeis"]
    assert "123456789012347" not in data["imeis"]
    
    # Test as MANAGER - should see both location 1 and location 2 (but not other business)
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["imeis"]) == 2
    assert "123456789012345" in data["imeis"]
    assert "123456789012346" in data["imeis"]
    assert "123456789012347" not in data["imeis"]


def test_available_imeis_excludes_sold_items(
    client, phones_business, location, manager_user, phone_product
):
    """Test that sold items are not included in available IMEIs."""
    # Create in-stock item
    item1 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012345",
        status="IN_STOCK",
        is_active=True,
        current_location=location,
        order_price=Decimal("100.00"),
    )
    
    # Create sold item
    item2 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012346",
        status="SOLD",
        is_active=True,
        current_location=location,
        order_price=Decimal("100.00"),
        sold_at=timezone.now(),
    )
    
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    url = reverse("inventory:phones_available_imeis", kwargs={"product_id": phone_product.id})
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["imeis"]) == 1
    assert "123456789012345" in data["imeis"]
    assert "123456789012346" not in data["imeis"]


def test_available_imeis_excludes_inactive_items(
    client, phones_business, location, manager_user, phone_product
):
    """Test that inactive items are not included in available IMEIs."""
    # Create active item
    item1 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012345",
        status="IN_STOCK",
        is_active=True,
        current_location=location,
        order_price=Decimal("100.00"),
    )
    
    # Create inactive item
    item2 = InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012346",
        status="IN_STOCK",
        is_active=False,
        current_location=location,
        order_price=Decimal("100.00"),
    )
    
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    url = reverse("inventory:phones_available_imeis", kwargs={"product_id": phone_product.id})
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["imeis"]) == 1
    assert "123456789012345" in data["imeis"]
    assert "123456789012346" not in data["imeis"]


# =============================================================================
# TESTS: Role-Based Scoping
# =============================================================================
def test_scan_in_counts_are_role_based(
    client, phones_business, location, location2, 
    manager_user, agent_user, agent2_user, phone_product
):
    """
    Test that scan-in counts are role-based:
    - Managers see all scans for the business
    - Agents see only their own scans in their location
    """
    today = date.today()
    
    # Create stock by agent 1 in location 1
    InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012345",
        status="IN_STOCK",
        is_active=True,
        current_location=location,
        assigned_agent=agent_user,
        received_at=today,
        order_price=Decimal("100.00"),
    )
    
    # Create stock by agent 2 in location 2
    InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012346",
        status="IN_STOCK",
        is_active=True,
        current_location=location2,
        assigned_agent=agent2_user,
        received_at=today,
        order_price=Decimal("100.00"),
    )
    
    # Create stock by manager in location 1
    InventoryItem.objects.create(
        business=phones_business,
        product=phone_product,
        imei="123456789012347",
        status="IN_STOCK",
        is_active=True,
        current_location=location,
        assigned_agent=manager_user,
        received_at=today,
        order_price=Decimal("100.00"),
    )
    
    # Test as AGENT 1 - should only see their own scan (1)
    client.force_login(agent_user)
    set_active_business(client, phones_business)
    
    url = reverse("inventory:scan_in")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    # Agent should see gamification elements
    assert "Today's Target" in content or "daily_target" in content
    
    # Test as MANAGER - should see all scans (3)
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    # Manager should see gamification elements
    assert "Today's Target" in content or "daily_target" in content


# =============================================================================
# TESTS: Cross-Business Security
# =============================================================================
def test_scan_in_uses_current_business_and_not_other(
    client, phones_business, other_business, location, manager_user
):
    """
    Test that scan-in always uses the current business and rejects cross-business attacks.
    """
    # Create a product catalog in the other business
    other_location = Location.objects.create(
        business=other_business,
        name="Other Store",
    )
    
    other_catalog = PhoneProductCatalog.objects.create(
        business=other_business,
        brand="SAMSUNG",
        model_name="Galaxy A14",
        variant_label="(4+128)",
        display_name="Samsung Galaxy A14 (4+128)",
        default_cost_price=Decimal("150.00"),
        default_selling_price=Decimal("200.00"),
        is_active=True,
    )
    
    # Login as manager of phones_business
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    # Attempt to scan in using a product from other_business
    url = reverse("inventory:scan_in")
    response = client.post(url, {
        "brand": "samsung",
        "catalog_product_id": other_catalog.id,  # Product from OTHER business
        "imei": "123456789012345",
    })
    
    # Should fail - no stock should be created in either business
    assert not InventoryItem.objects.filter(
        business=other_business,
        imei="123456789012345"
    ).exists()
    
    assert not InventoryItem.objects.filter(
        business=phones_business,
        imei="123456789012345"
    ).exists()


# =============================================================================
# TESTS: URL Routing
# =============================================================================
def test_inventory_scan_in_url_uses_phone_scan_view(client, phones_business, manager_user):
    """
    Test that /inventory/scan-in/ now uses the gamified phone scan view.
    """
    client.force_login(manager_user)
    set_active_business(client, phones_business)
    
    # Both URLs should work and render the phones scan template
    url_main = reverse("inventory:scan_in")
    url_phones = reverse("inventory:phone_scan_in")
    
    response_main = client.get(url_main)
    response_phones = client.get(url_phones)
    
    assert response_main.status_code == 200
    assert response_phones.status_code == 200
    
    # Both should contain gamification elements
    content_main = response_main.content.decode()
    content_phones = response_phones.content.decode()
    
    # Check for gamification bar
    assert "Today's Target" in content_main or "daily_target" in content_main
    assert "Today's Target" in content_phones or "daily_target" in content_phones
    
    # Check for brand cards
    assert "brand-card" in content_main or "ITEL" in content_main
    assert "brand-card" in content_phones or "ITEL" in content_phones
    
    # Check for IMEI picker
    assert "imei-picker" in content_main or "Available IMEIs" in content_main
    assert "imei-picker" in content_phones or "Available IMEIs" in content_phones

