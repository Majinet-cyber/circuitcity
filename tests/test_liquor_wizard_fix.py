"""
Test liquor wizard (Add Product) and Stock In flows
"""
import json
import pytest
from decimal import Decimal
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business
from inventory.models import MerchProduct, Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def liquor_business(db):
    """Create a liquor business with a manager user"""
    business = Business.objects.create(
        name="Test Liquor Store",
        slug="test-liquor-store",
        kind=BusinessKind.LIQUOR,
        is_active=True,
    )
    
    # Create default location
    location = Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
    )
    
    # Create manager user
    user = User.objects.create_user(
        username="manager@test.com",
        email="manager@test.com",
        password="testpass123",
        is_staff=True,
    )
    
    # Associate user with business
    from tenants.models import Membership
    Membership.objects.create(
        user=user,
        business=business,
        role="manager",
        is_active=True,
    )
    
    return {
        "business": business,
        "location": location,
        "user": user,
    }


@pytest.mark.django_db
class TestLiquorWizard:
    """Test the liquor product wizard (Add Product)"""
    
    def test_wizard_page_loads(self, liquor_business):
        """Test that the wizard page loads correctly"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        url = reverse("inventory:liquor_wizard")
        response = client.get(url)
        
        assert response.status_code == 200
        assert b"Add Liquor Product" in response.content or b"Choose Liquor Type" in response.content
    
    def test_wizard_submit_beer_with_crate(self, liquor_business):
        """Test wizard submission for beer with crate pricing"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        url = reverse("inventory:liquor_wizard_submit")
        
        # Data in format sent by the wizard template (nested format)
        data = {
            "category": "beer",
            "details": {
                "product_name": "Castle Lager",
                "cost_per_bottle": "500.00",
                "sell_per_bottle": "800.00",
                "enable_crate": True,
                "crate_size": 20,
                "sell_per_crate": "15000.00",
            }
        }
        
        response = client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        
        # Should succeed
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "product_id" in result
        assert "redirect" in result
        
        # Verify product was created
        product = MerchProduct.objects.get(id=result["product_id"])
        assert product.name == "Castle Lager"
        assert product.kind == BusinessKind.LIQUOR
        assert product.category == "beer"
        assert product.price_per_bottle == Decimal("800.00")
        assert product.cost_per_bottle == Decimal("500.00")
        assert product.bottles_per_crate == 20
        assert product.supports_crates is True
    
    def test_wizard_submit_spirits_with_shots(self, liquor_business):
        """Test wizard submission for spirits with shot pricing"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        url = reverse("inventory:liquor_wizard_submit")
        
        # Data in format sent by the wizard template (nested format)
        data = {
            "category": "spirits",
            "details": {
                "product_name": "Gilbeys Gin",
                "cost_per_bottle": "3000.00",
                "sell_per_bottle": "5000.00",
                "enable_shot": True,
                "shots_per_bottle": 30,
                "sell_per_shot": "200.00",
            }
        }
        
        response = client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        
        # Should succeed
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        
        # Verify product was created with shot fields
        product = MerchProduct.objects.get(id=result["product_id"])
        assert product.name == "Gilbeys Gin"
        assert product.has_shots is True
        assert product.shots_per_bottle == 30
        assert product.price_per_shot == Decimal("200.00")
    
    def test_wizard_submit_missing_name(self, liquor_business):
        """Test wizard rejects submission without product name"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        url = reverse("inventory:liquor_wizard_submit")
        
        # Missing product_name
        data = {
            "category": "beer",
            "details": {
                "sell_per_bottle": "800.00",
            }
        }
        
        response = client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        
        # Should fail with error
        assert response.status_code == 400
        result = response.json()
        assert result["success"] is False
        assert "Product name is required" in result["error"]


@pytest.mark.django_db
class TestLiquorStockIn:
    """Test the liquor stock-in flow"""
    
    def test_stock_in_page_loads(self, liquor_business):
        """Test that stock-in page loads correctly"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        # Create a test product first
        product = MerchProduct.objects.create(
            business=liquor_business["business"],
            name="Test Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            price_per_bottle=Decimal("800.00"),
            quantity_in_stock=0,
        )
        
        url = reverse("liquor:scan_in")
        response = client.get(url)
        
        assert response.status_code == 200
        assert b"Stock In - Liquor" in response.content or b"Stock In" in response.content
    
    def test_stock_in_submit_bottles(self, liquor_business):
        """Test stock-in submission for bottles"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        # Create a test product
        product = MerchProduct.objects.create(
            business=liquor_business["business"],
            name="Test Cider",
            kind=BusinessKind.LIQUOR,
            category="cider",
            price_per_bottle=Decimal("600.00"),
            quantity_in_stock=0,
        )
        
        url = reverse("liquor:scan_in")
        
        # Submit stock-in
        response = client.post(url, {
            "product_id": product.id,
            "unit_type": "bottle",
            "quantity": 24,
            "cost_per_unit": "500.00",
            "selling_price": "600.00",
        })
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify stock was updated
        product.refresh_from_db()
        assert product.quantity_in_stock == 24
        assert product.cost_per_bottle == Decimal("500.00")
        assert product.price_per_bottle == Decimal("600.00")
    
    def test_stock_in_submit_crates(self, liquor_business):
        """Test stock-in submission for crates (should convert to bottles)"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        # Create a test product with crate support
        product = MerchProduct.objects.create(
            business=liquor_business["business"],
            name="Test Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            price_per_bottle=Decimal("800.00"),
            bottles_per_crate=20,
            supports_crates=True,
            quantity_in_stock=0,
        )
        
        url = reverse("liquor:scan_in")
        
        # Submit 2 crates (should become 40 bottles)
        response = client.post(url, {
            "product_id": product.id,
            "unit_type": "crate",
            "quantity": 2,
            "cost_per_unit": "15000.00",  # Cost per crate
            "selling_price": "800.00",  # Selling price per bottle
        })
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify stock was updated (2 crates = 40 bottles)
        product.refresh_from_db()
        assert product.quantity_in_stock == 40
        
        # Cost should be per bottle (15000 / 20 = 750)
        assert product.cost_per_bottle == Decimal("750.00")
    
    def test_stock_in_rejects_crates_for_spirits(self, liquor_business):
        """Test that stock-in rejects crates for spirits (spirits must use bottles)"""
        client = Client()
        client.force_login(liquor_business["user"])
        
        # Set active business in session
        session = client.session
        session["active_business_id"] = liquor_business["business"].id
        session.save()
        
        # Create a spirits product
        product = MerchProduct.objects.create(
            business=liquor_business["business"],
            name="Test Gin",
            kind=BusinessKind.LIQUOR,
            category="spirits",
            price_per_bottle=Decimal("5000.00"),
            quantity_in_stock=0,
        )
        
        url = reverse("liquor:scan_in")
        
        # Try to submit crates (should fail)
        response = client.post(url, {
            "product_id": product.id,
            "unit_type": "crate",
            "quantity": 1,
            "cost_per_unit": "3000.00",
        })
        
        # Should redirect (with error message in session)
        assert response.status_code == 302
        
        # Stock should NOT have changed
        product.refresh_from_db()
        assert product.quantity_in_stock == 0

