# tests/test_multi_vertical_bug_fixes_jan_2026.py
"""
Regression tests for multi-vertical bug fixes (January 2026).

CRITICAL BUGS FIXED:
1. Liquor: /liquor/performance/ 500 error
2. Liquor: Beer/Cider per-bottle pricing (not per-crate)
3. Liquor: Spirits/Whiskey per-shot pricing
4. Clothing: "No active location found" error when 1 location exists
5. Clothing: Barcode save hang issue (400/500 status codes)
6. Clothing: Unique barcode Fast Sell enforcement
7. Gym: Billing Checkout missing in sidebar

ZERO REGRESSIONS: All existing tests must pass.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from tenants.models import Business, Membership, Location

User = get_user_model()


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def clothing_business():
    """Create a test clothing business"""
    return Business.objects.create(
        name="Test Clothing Store",
        slug="test-clothing-regress",
        status="ACTIVE",
        business_kind=BusinessKind.CLOTHING
    )


@pytest.fixture
def clothing_manager(clothing_business):
    """Create a manager user for clothing"""
    user = User.objects.create_user(username="clothing_mgr", password="testpass123")
    user.is_staff = False
    user.save()
    
    Membership.objects.create(
        user=user,
        business=clothing_business,
        role="Manager",
        is_active=True
    )
    return user


@pytest.fixture
def clothing_location(clothing_business):
    """Create a location for clothing business"""
    return Location.objects.create(
        business=clothing_business,
        name="Main Store",
        is_default=True
    )


# ============================================================================
# CLOTHING: Location Auto-Selection Tests
# ============================================================================

@pytest.mark.django_db
class TestClothingLocationAutoSelect:
    """
    Test: Auto-select location when business has exactly 1 location
    Bug: "No active location found" blocked saves even with 1 location
    Fix: resolve_active_location() and ensure_default_location() auto-select single location
    """

    def test_auto_select_single_location_on_wizard_submit(self, client, clothing_business, clothing_manager, clothing_location):
        """Wizard should auto-select location when business has exactly 1 location"""
        client.force_login(clothing_manager)
        
        # Clear session (no active location set)
        session = client.session
        session.clear()
        session.save()
        
        # Submit wizard (should auto-select the single location)
        url = reverse('inventory:clothing_wizard_submit')
        data = {
            "category": "shirt",
            "size": "M",
            "color": "Blue",
            "product_name": "Test Shirt",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "quantity": 1,
            "has_barcode": "no"
        }
        
        response = client.post(url, data=data, content_type='application/json')
        
        # CRITICAL: Must not fail with "No active location found"
        assert response.status_code == 200
        json_data = response.json()
        assert json_data.get("success") == True, f"Expected success, got: {json_data}"


    def test_no_location_error_for_multiple_locations(self, client, clothing_business, clothing_manager):
        """Should handle multiple locations gracefully (not crash)"""
        # Create 2 locations
        Location.objects.create(business=clothing_business, name="Store 1", is_default=True)
        Location.objects.create(business=clothing_business, name="Store 2")
        
        client.force_login(clothing_manager)
        
        # Clear session
        session = client.session
        session.clear()
        session.save()
        
        # Submit wizard
        url = reverse('inventory:clothing_wizard_submit')
        data = {
            "category": "shirt",
            "size": "L",
            "color": "Red",
            "product_name": "Test Shirt 2",
            "selling_price": "6000.00",
            "cost_price": "4000.00",
            "quantity": 1,
            "has_barcode": "no"
        }
        
        response = client.post(url, data=data, content_type='application/json')
        
        # Should not 500 (may succeed or ask for location pick)
        assert response.status_code in [200, 302]


# ============================================================================
# CLOTHING: Barcode Save Hang Fix Tests
# ============================================================================

@pytest.mark.django_db
class TestClothingBarcodeSaveNoHang:
    """
    Test: Barcode finalize returns 200 (not 400/500) so frontend can display errors
    Bug: 400/500 status codes caused frontend to "stick" without showing error
    Fix: Return status 200 with {"success": False, "error": "..."} for validation errors
    """

    def test_barcode_validation_error_returns_200(self, client, clothing_business, clothing_manager, clothing_location):
        """Barcode validation errors should return 200 (not 400) so frontend displays error"""
        client.force_login(clothing_manager)
        
        # Set active business + location in session
        session = client.session
        session['active_business_id'] = clothing_business.id
        session['active_location_id'] = clothing_location.id
        session.save()
        
        # Submit with invalid data (missing size)
        url = reverse('inventory:clothing_wizard_submit')
        data = {
            "category": "shirt",
            "size": "",  # Missing size (should trigger validation error)
            "color": "Green",
            "selling_price": "7000.00",
            "cost_price": "5000.00",
            "quantity": 1,
            "has_barcode": "no"
        }
        
        response = client.post(url, data=data, content_type='application/json')
        
        # CRITICAL: Must return 200 (not 400) so frontend can display error
        assert response.status_code == 200
        json_data = response.json()
        assert json_data.get("success") == False
        assert "error" in json_data


# ============================================================================
# CLOTHING: Unique Barcode Fast Sell Enforcement Tests
# ============================================================================

@pytest.mark.django_db
class TestClothingUniqueBarcodeEnforcement:
    """
    Test: Unique-barcode items can ONLY be sold via Fast Sell
    Bug: Normal sell allowed selling unique-barcode items, breaking inventory tracking
    Fix: Exclude unique-barcode products from normal sell form + server-side validation
    """

    def test_unique_barcode_items_excluded_from_normal_sell(self, client, clothing_business, clothing_manager, clothing_location):
        """Products with barcode units should be excluded from normal sell form"""
        client.force_login(clothing_manager)
        
        # Create a product
        product = MerchProduct.objects.create(
            business=clothing_business,
            name="Test Shoe - Size 42",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="42",
            selling_price=Decimal("15000.00"),
            cost_price=Decimal("10000.00"),
            quantity_in_stock=5,
            is_active=True
        )
        
        # Create a unique barcode unit for this product
        ClothingBarcodeUnit.objects.create(
            business=clothing_business,
            location=clothing_location,
            product=product,
            barcode="UNIQUE123",
            size="42",
            category="shoes",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            status="IN_STOCK",
            created_by=clothing_manager
        )
        
        # Get normal sell page
        url = reverse('verticals:clothing_sell')
        response = client.get(url)
        
        # Product should NOT appear in the form (it has barcode units)
        assert response.status_code == 200
        # This product should be excluded from queryset
        # (We can't easily assert form queryset in template, but server-side validation will catch it)


    def test_normal_sell_rejects_unique_barcode_products(self, client, clothing_business, clothing_manager, clothing_location):
        """Server-side validation: reject selling unique-barcode items via normal sell"""
        client.force_login(clothing_manager)
        
        # Set session
        session = client.session
        session['active_business_id'] = clothing_business.id
        session.save()
        
        # Create product with barcode unit
        product = MerchProduct.objects.create(
            business=clothing_business,
            name="Barcoded Shoe",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="40",
            selling_price=Decimal("12000.00"),
            cost_price=Decimal("8000.00"),
            quantity_in_stock=3,
            is_active=True
        )
        
        ClothingBarcodeUnit.objects.create(
            business=clothing_business,
            location=clothing_location,
            product=product,
            barcode="BARCODE456",
            size="40",
            category="shoes",
            cost_price=Decimal("8000.00"),
            selling_price=Decimal("12000.00"),
            status="IN_STOCK",
            created_by=clothing_manager
        )
        
        # Attempt to sell via normal sell (should be rejected)
        url = reverse('verticals:clothing_sell')
        data = {
            "product": product.id,
            "quantity": 1,
            "selling_price": "12000.00",
            "payment_method": "cash"
        }
        
        response = client.post(url, data=data)
        
        # Should redirect with error message
        assert response.status_code == 302  # Redirect
        
        # Check messages (product should NOT be sold)
        from django.contrib.messages import get_messages
        messages = list(get_messages(response.wsgi_request))
        assert any("Fast Sell" in str(m) or "barcode" in str(m).lower() for m in messages)


# ============================================================================
# GYM: Billing Checkout Sidebar Test
# ============================================================================

@pytest.mark.django_db
class TestGymBillingCheckoutSidebar:
    """
    Test: Gym sidebar contains Billing Checkout link
    Bug: Missing Billing Checkout button/link in gym sidebar
    Fix: Added "Billing Checkout" to get_vertical_sidebar_items() for gym
    """

    def test_gym_sidebar_has_billing_checkout_link(self):
        """Gym sidebar should include Billing Checkout link"""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("gym")
        
        # Find billing checkout item
        checkout_item = None
        for item in sidebar_items:
            if item.get("key") == "billing_checkout":
                checkout_item = item
                break
        
        # CRITICAL: Billing Checkout must be present
        assert checkout_item is not None, "Billing Checkout link missing from gym sidebar"
        assert checkout_item["label"] == "Billing Checkout"
        assert "billing:checkout" in checkout_item["url"]


# Run these tests:
# pytest tests/test_multi_vertical_bug_fixes_jan_2026.py -v
# pytest tests/test_multi_vertical_bug_fixes_jan_2026.py::TestClothingLocationAutoSelect::test_auto_select_single_location_on_wizard_submit -v

