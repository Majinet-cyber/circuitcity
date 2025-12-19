# tests/test_gym_qr_and_grocery.py
"""
Tests for gym QR code features and grocery fast sell.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models_verticals import GymMember, GymSettings
from inventory.models_grocery import GroceryProduct, GrocerySale

User = get_user_model()


@pytest.fixture
def gym_business(db):
    """Create a gym business."""
    business = Business.objects.create(
        name="Test Gym",
        business_kind="gym"
    )
    # Create gym settings
    GymSettings.objects.create(
        business=business,
        default_membership_price=Decimal("50000.00"),
        default_trainer_fee=Decimal("30000.00")
    )
    return business


@pytest.fixture
def grocery_business(db):
    """Create a grocery business."""
    return Business.objects.create(
        name="Test Grocery",
        business_kind="grocery"
    )


@pytest.fixture
def manager_user(db, gym_business):
    """Create a manager user."""
    user = User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=gym_business,
        role="manager"
    )
    return user


@pytest.fixture
def grocery_manager(db, grocery_business):
    """Create a grocery manager user."""
    user = User.objects.create_user(
        username="grocery_manager",
        email="grocery@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=grocery_business,
        role="manager"
    )
    return user


# ==============================================================================
# GYM QR CODE TESTS
# ==============================================================================

@pytest.mark.django_db
def test_gym_member_qr_token_auto_generated(gym_business):
    """Test that QR token is auto-generated when creating a member."""
    member = GymMember.objects.create(
        business=gym_business,
        name="John Doe",
        phone="+265999123456",
        membership_fee=Decimal("50000.00")
    )
    
    assert member.qr_token
    assert len(member.qr_token) == 32  # SHA256 truncated to 32 chars
    assert member.qr_token.isalnum()


@pytest.mark.django_db
def test_gym_member_qr_token_unique(gym_business):
    """Test that each member gets a unique QR token."""
    member1 = GymMember.objects.create(
        business=gym_business,
        name="John Doe",
        phone="+265999123456",
        membership_fee=Decimal("50000.00")
    )
    
    member2 = GymMember.objects.create(
        business=gym_business,
        name="Jane Doe",
        phone="+265999654321",
        membership_fee=Decimal("50000.00")
    )
    
    assert member1.qr_token != member2.qr_token


@pytest.mark.django_db
def test_gym_qr_scan_result_page(client, manager_user, gym_business):
    """Test that QR scan result page loads correctly."""
    # Create a member
    member = GymMember.objects.create(
        business=gym_business,
        name="Test Member",
        phone="+265999123456",
        membership_fee=Decimal("50000.00")
    )
    
    # Login
    client.login(username="manager", password="testpass123")
    
    # Access QR scan result page
    url = reverse("gym:qr_scan_result", kwargs={"member_id": member.id})
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Test Member" in response.content.decode()


@pytest.mark.django_db
def test_gym_member_qr_card_page(client, manager_user, gym_business):
    """Test that member QR card page loads correctly."""
    # Create a member
    member = GymMember.objects.create(
        business=gym_business,
        name="Test Member",
        phone="+265999123456",
        membership_fee=Decimal("50000.00")
    )
    
    # Login
    client.login(username="manager", password="testpass123")
    
    # Access QR card page
    url = reverse("gym:member_qr_card", kwargs={"member_id": member.id})
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Membership Card" in response.content.decode()
    assert member.qr_token in response.content.decode()


@pytest.mark.django_db
def test_gym_member_color_theme_deterministic():
    """Test that member color theme is deterministic."""
    from inventory.utils_gym_qr import get_member_color_theme
    
    # Same member should always get same colors
    color1 = get_member_color_theme(1, "test_token_123")
    color2 = get_member_color_theme(1, "test_token_123")
    
    assert color1 == color2
    
    # Different members should get different colors
    color3 = get_member_color_theme(2, "test_token_456")
    assert color1 != color3


# ==============================================================================
# GROCERY FAST SELL TESTS
# ==============================================================================

@pytest.mark.django_db
def test_grocery_fast_sell_page_loads(client, grocery_manager, grocery_business):
    """Test that grocery fast sell page loads correctly."""
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Access fast sell page
    url = reverse("grocery:fast_sell")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Fast Sell" in response.content.decode()


@pytest.mark.django_db
def test_grocery_fast_sell_lookup_by_barcode(client, grocery_manager, grocery_business):
    """Test that fast sell lookup works with barcode."""
    # Create a product with barcode
    product = GroceryProduct.objects.create(
        business=grocery_business,
        name="Rice 5kg",
        barcode="123456789",
        unit_type="bag",
        quantity=Decimal("100.00"),
        cost_price=Decimal("5000.00"),
        selling_price=Decimal("7000.00")
    )
    
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Lookup by barcode
    url = reverse("grocery:fast_sell_lookup") + "?q=123456789"
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["product"]["name"] == "Rice 5kg"
    assert data["product"]["barcode"] == "123456789"


@pytest.mark.django_db
def test_grocery_fast_sell_lookup_by_name(client, grocery_manager, grocery_business):
    """Test that fast sell lookup works with product name."""
    # Create a product without barcode
    product = GroceryProduct.objects.create(
        business=grocery_business,
        name="Sugar 1kg",
        unit_type="kg",
        quantity=Decimal("50.00"),
        cost_price=Decimal("2000.00"),
        selling_price=Decimal("2500.00")
    )
    
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Lookup by name
    url = reverse("grocery:fast_sell_lookup") + "?q=Sugar"
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Sugar" in data["product"]["name"]


@pytest.mark.django_db
def test_grocery_fast_sell_lookup_not_found(client, grocery_manager, grocery_business):
    """Test that fast sell lookup returns error for non-existent product."""
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Lookup non-existent product
    url = reverse("grocery:fast_sell_lookup") + "?q=NonExistentProduct"
    response = client.get(url)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error"].lower()


@pytest.mark.django_db
def test_grocery_fast_sell_completes_sale(client, grocery_manager, grocery_business):
    """Test that fast sell can complete a sale."""
    # Create a product
    product = GroceryProduct.objects.create(
        business=grocery_business,
        name="Cooking Oil 2L",
        unit_type="litre",
        quantity=Decimal("30.00"),
        cost_price=Decimal("3000.00"),
        selling_price=Decimal("4000.00")
    )
    
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Submit sale
    url = reverse("grocery:fast_sell")
    response = client.post(url, {
        "product_id": product.id,
        "quantity": "2.00",
        "unit_price": "4000.00",
        "payment_method": "CASH"
    })
    
    # Check redirect (successful sale)
    assert response.status_code == 302
    
    # Verify sale was created
    sale = GrocerySale.objects.filter(business=grocery_business, product=product).first()
    assert sale is not None
    assert sale.quantity == Decimal("2.00")
    assert sale.unit_price == Decimal("4000.00")
    
    # Verify stock was deducted
    product.refresh_from_db()
    assert product.quantity == Decimal("28.00")


@pytest.mark.django_db
def test_grocery_fast_sell_prevents_overselling(client, grocery_manager, grocery_business):
    """Test that fast sell prevents selling more than available stock."""
    # Create a product with limited stock
    product = GroceryProduct.objects.create(
        business=grocery_business,
        name="Salt 500g",
        unit_type="gram",
        quantity=Decimal("5.00"),
        cost_price=Decimal("500.00"),
        selling_price=Decimal("700.00")
    )
    
    # Login
    client.login(username="grocery_manager", password="testpass123")
    
    # Try to sell more than available
    url = reverse("grocery:fast_sell")
    response = client.post(url, {
        "product_id": product.id,
        "quantity": "10.00",  # More than available
        "unit_price": "700.00",
        "payment_method": "CASH"
    })
    
    # Check that sale was not completed
    sale_count = GrocerySale.objects.filter(business=grocery_business, product=product).count()
    assert sale_count == 0
    
    # Verify stock was not changed
    product.refresh_from_db()
    assert product.quantity == Decimal("5.00")


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

@pytest.mark.django_db
def test_gym_add_member_wizard_flow(client, manager_user, gym_business):
    """Test the gamified gym member add wizard flow."""
    # Login
    client.login(username="manager", password="testpass123")
    
    # Access add member page
    url = reverse("gym:member_add")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Add New Member" in response.content.decode()
    
    # Submit member creation
    response = client.post(url, {
        "name": "Test Member",
        "phone": "+265999123456",
        "email": "test@example.com",
        "has_trainer": "false",
        "duration_days": "30"
    })
    
    # Check redirect (successful creation)
    assert response.status_code == 302
    
    # Verify member was created
    member = GymMember.objects.filter(business=gym_business, name="Test Member").first()
    assert member is not None
    assert member.phone == "+265999123456"
    assert member.qr_token  # QR token should be auto-generated

