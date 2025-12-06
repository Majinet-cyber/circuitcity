# tests/test_phones_scan_gamified.py
"""
Tests for gamified phone scan-in and scan-sell views.

Ensures:
- Brand cards render correctly
- Model dropdowns are scoped to brand
- Gamification stats are present
- Business/location scoping is respected
- IMEI validation works
- Stock entries are created correctly
"""
import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location
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
def location(db, phones_business):
    """Create a location for the phones business."""
    location = Location.objects.create(
        business=phones_business,
        name="Main Store",
        is_default=True,
    )
    return location


@pytest.fixture
def other_business(db):
    """Create another business for cross-tenant testing."""
    business = Business.objects.create(
        name="Other Phones Shop 2",
        slug="other-phones-shop-2",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE",
    )
    return business


@pytest.fixture
def manager_user(db, django_user_model, phones_business, location):
    """Create a manager user for the phones business."""
    user = django_user_model.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="MANAGER",
        status="ACTIVE",
        # Managers don't have a location - they have business-wide access
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
def tecno_phone(db, phones_business):
    """Create a TECNO phone product in catalog."""
    return PhoneProductCatalog.objects.create(
        business=phones_business,
        brand="TECNO",
        model_name="Spark 40",
        ram_gb=4,
        rom_gb=128,
        variant_label="4+128",
        default_cost_price=Decimal("450000.00"),
        default_selling_price=Decimal("550000.00"),
        is_active=True,
    )


@pytest.fixture
def itel_phone(db, phones_business):
    """Create an ITEL phone product in catalog."""
    return PhoneProductCatalog.objects.create(
        business=phones_business,
        brand="ITEL",
        model_name="A90",
        ram_gb=3,
        rom_gb=128,
        variant_label="3+128",
        default_cost_price=Decimal("280000.00"),
        default_selling_price=Decimal("350000.00"),
        is_active=True,
    )


# =============================================================================
# SCAN-IN Tests
# =============================================================================
def test_phone_scan_in_page_renders_brand_cards(client, manager_user, phones_business):
    """Test that scan-in page renders brand cards."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_in")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for brand names
    assert "ITEL" in content
    assert "TECNO" in content
    assert "SAMSUNG" in content
    
    # Check for gamification elements
    assert "Today's Target" in content or "daily_target" in content
    assert "Scanned today" in content or "scanned_today" in content


def test_phone_scan_in_creates_stock_entry(client, manager_user, phones_business, location, tecno_phone):
    """Test that scan-in successfully creates a stock entry."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_in")
    data = {
        "brand": "tecno",
        "catalog_product_id": str(tecno_phone.id),
        "imei": "123456789012345",
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # Check that inventory item was created
    item = InventoryItem.objects.filter(
        business=phones_business,
        imei="123456789012345",
    ).first()
    
    assert item is not None
    assert item.status == "IN_STOCK"
    assert item.is_active is True
    assert item.order_price == tecno_phone.default_cost_price


def test_phone_scan_in_rejects_duplicate_imei(client, manager_user, phones_business, location, tecno_phone):
    """Test that scan-in rejects duplicate IMEI within same business."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    # Create a Product for the existing item
    from inventory.models import Product
    product, _ = Product.objects.get_or_create(
        brand=tecno_phone.brand,
        model=tecno_phone.model_name,
        variant=tecno_phone.variant_label,
        defaults={
            "code": f"{tecno_phone.brand}-{tecno_phone.model_name}-{tecno_phone.variant_label}".replace(" ", "-"),
            "name": tecno_phone.display_name,
            "cost_price": tecno_phone.default_cost_price or Decimal("0.00"),
            "sale_price": tecno_phone.default_selling_price or Decimal("0.00"),
        }
    )
    
    # Create existing item with same IMEI
    InventoryItem.objects.create(
        business=phones_business,
        imei="123456789012345",
        status="IN_STOCK",
        order_price=Decimal("400000.00"),
        current_location=location,
        product=product,
    )
    
    url = reverse("inventory:phone_scan_in")
    data = {
        "brand": "tecno",
        "catalog_product_id": str(tecno_phone.id),
        "imei": "123456789012345",
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # Should only have 1 item (the original)
    count = InventoryItem.objects.filter(
        business=phones_business,
        imei="123456789012345",
    ).count()
    assert count == 1


def test_phone_scan_in_is_scoped_to_current_business_only(
    client, manager_user, phones_business, location, other_business, tecno_phone
):
    """Test that scan-in cannot use products from other businesses."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    # Create a product in OTHER business
    foreign_phone = PhoneProductCatalog.objects.create(
        business=other_business,
        brand="TECNO",
        model_name="Foreign Model",
        ram_gb=8,
        rom_gb=256,
        variant_label="8+256",
        is_active=True,
    )
    
    url = reverse("inventory:phone_scan_in")
    data = {
        "brand": "tecno",
        "catalog_product_id": str(foreign_phone.id),
        "imei": "999999999999999",
    }
    response = client.post(url, data)
    
    # Should fail (404 or validation error)
    assert response.status_code in (200, 302)  # redirects with error message
    
    # No item should be created
    assert not InventoryItem.objects.filter(imei="999999999999999").exists()


def test_phone_scan_in_context_includes_gamification_stats(
    client, manager_user, phones_business
):
    """Test that scan-in page context includes gamification stats."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_in")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "scanned_today" in response.context
    assert "daily_target" in response.context
    assert "progress_pct" in response.context
    
    # Stats should be numeric
    assert isinstance(response.context["scanned_today"], int)
    assert isinstance(response.context["daily_target"], int)
    assert isinstance(response.context["progress_pct"], int)


def test_phone_scan_in_normalizes_imei(client, manager_user, phones_business, location, tecno_phone):
    """Test that IMEI is normalized (digits only, last 15)."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_in")
    
    # Submit IMEI with extra characters and leading digits
    data = {
        "brand": "tecno",
        "catalog_product_id": str(tecno_phone.id),
        "imei": "00123456789012345",  # 17 digits - should take last 15
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # Check that item was created with normalized IMEI (last 15 digits)
    item = InventoryItem.objects.filter(
        business=phones_business,
        imei="123456789012345",
    ).first()
    
    assert item is not None


# =============================================================================
# SCAN-SELL Tests
# =============================================================================
def test_phone_scan_sell_page_renders_brand_cards(client, manager_user, phones_business):
    """Test that scan-sell page renders brand cards."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_sell")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for brand names
    assert "ITEL" in content
    assert "TECNO" in content
    assert "SAMSUNG" in content
    
    # Check for sales gamification elements
    assert "Sales Target" in content or "daily_sales_target" in content
    assert "Sold today" in content or "sold_today" in content


def test_phone_scan_sell_marks_item_as_sold(
    client, manager_user, phones_business, location, tecno_phone
):
    """Test that scan-sell successfully marks an in-stock item as sold."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    # Create a Product for the item
    from inventory.models import Product
    product, _ = Product.objects.get_or_create(
        brand=tecno_phone.brand,
        model=tecno_phone.model_name,
        variant=tecno_phone.variant_label,
        defaults={
            "code": f"{tecno_phone.brand}-{tecno_phone.model_name}-{tecno_phone.variant_label}".replace(" ", "-"),
            "name": tecno_phone.display_name,
            "cost_price": tecno_phone.default_cost_price or Decimal("0.00"),
            "sale_price": tecno_phone.default_selling_price or Decimal("0.00"),
        }
    )
    
    # Create an in-stock item
    item = InventoryItem.objects.create(
        business=phones_business,
        imei="123456789012345",
        status="IN_STOCK",
        order_price=Decimal("450000.00"),
        is_active=True,
        current_location=location,
        product=product,
    )
    
    url = reverse("inventory:phone_scan_sell")
    data = {
        "brand": "tecno",
        "imei": "123456789012345",
        "selling_price": "550000.00",
        "payment_method": "CASH",
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # Refresh item from DB
    item.refresh_from_db()
    
    assert item.status == "SOLD"
    assert item.selling_price == Decimal("550000.00")
    assert item.sold_at is not None
    assert item.payment_method == "CASH"


def test_phone_scan_sell_rejects_nonexistent_imei(client, manager_user, phones_business):
    """Test that scan-sell rejects IMEI not in stock."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_sell")
    data = {
        "brand": "tecno",
        "imei": "999999999999999",
        "selling_price": "550000.00",
        "payment_method": "CASH",
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # No item should be marked as sold
    assert not InventoryItem.objects.filter(
        imei="999999999999999",
        status="SOLD",
    ).exists()


def test_phone_scan_sell_context_includes_gamification_stats(
    client, manager_user, phones_business
):
    """Test that scan-sell page context includes sales gamification stats."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_sell")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "sold_today" in response.context
    assert "daily_sales_target" in response.context
    assert "sales_progress_pct" in response.context
    
    # Stats should be numeric
    assert isinstance(response.context["sold_today"], int)
    assert isinstance(response.context["daily_sales_target"], int)
    assert isinstance(response.context["sales_progress_pct"], int)


def test_phone_scan_sell_is_scoped_to_current_business(
    client, manager_user, phones_business, location, other_business
):
    """Test that scan-sell cannot sell items from other businesses."""
    client.force_login(manager_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    # Create a location for other business
    other_location = Location.objects.create(
        business=other_business,
        name="Other Store",
        is_default=True,
    )
    
    # Create a Product for the other business item
    from inventory.models import Product
    other_product, _ = Product.objects.get_or_create(
        brand="TECNO",
        model="Other Model",
        variant="8+256",
        defaults={
            "code": "TECNO-Other-Model-8-256",
            "name": "TECNO Other Model (8+256)",
            "cost_price": Decimal("400000.00"),
            "sale_price": Decimal("500000.00"),
        }
    )
    
    # Create item in OTHER business
    InventoryItem.objects.create(
        business=other_business,
        imei="123456789012345",
        status="IN_STOCK",
        order_price=Decimal("400000.00"),
        is_active=True,
        current_location=other_location,
        product=other_product,
    )
    
    url = reverse("inventory:phone_scan_sell")
    data = {
        "brand": "tecno",
        "imei": "123456789012345",
        "selling_price": "550000.00",
        "payment_method": "CASH",
    }
    response = client.post(url, data, follow=True)
    
    assert response.status_code == 200
    
    # Item from other business should NOT be marked as sold
    item = InventoryItem.objects.get(business=other_business, imei="123456789012345")
    assert item.status == "IN_STOCK"  # Still in stock


# =============================================================================
# Agent vs Manager Tests
# =============================================================================
def test_agent_can_access_phone_scan_in(client, agent_user, phones_business):
    """Test that agents can access the phone scan-in page."""
    client.force_login(agent_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_in")
    response = client.get(url)
    
    assert response.status_code == 200


def test_agent_can_access_phone_scan_sell(client, agent_user, phones_business):
    """Test that agents can access the phone scan-sell page."""
    client.force_login(agent_user)
    
    # Set active business in session
    session = client.session
    session["active_business_id"] = phones_business.id
    session.save()
    
    url = reverse("inventory:phone_scan_sell")
    response = client.get(url)
    
    assert response.status_code == 200

