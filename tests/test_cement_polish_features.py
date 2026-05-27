# tests/test_cement_polish_features.py
"""
Tests for cement vertical polish features:
- Costs UI with category card radios
- Dashboard blue theme
- Sale editing with stock/profit consistency
- Mobile nav routing
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def cement_business(db):
    """Create a cement business for testing."""
    from tenants.models import Business
    
    business = Business.objects.create(
        name="Test Cement Store",
        business_kind="cement",
    )
    return business


@pytest.fixture
def manager_user(db, cement_business):
    """Create a manager user for the cement business."""
    from tenants.models import Membership
    
    user = User.objects.create_user(
        username="cement_manager",
        email="manager@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=cement_business,
        role="MANAGER",
        status="ACTIVE",
    )
    return user


@pytest.fixture
def agent_user(db, cement_business):
    """Create an agent user for the cement business."""
    from tenants.models import Membership
    
    user = User.objects.create_user(
        username="cement_agent",
        email="agent@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=cement_business,
        role="AGENT",
        status="ACTIVE",
    )
    return user


@pytest.fixture
def cement_product(db, cement_business):
    """Create a cement product for testing."""
    from inventory.models import MerchProduct
    
    product = MerchProduct.objects.create(
        business=cement_business,
        name="Dangote Cement 50KG",
        kind="cement",
        cost_price=Decimal("12000.00"),
        selling_price=Decimal("15000.00"),
        quantity_in_stock=100,
        base_unit="bag",
        is_active=True,
    )
    return product


@pytest.fixture
def cement_sale(db, cement_business, cement_product, manager_user):
    """Create a cement sale for testing."""
    from inventory.models_verticals import CementSale
    
    sale = CementSale.objects.create(
        business=cement_business,
        product=cement_product,
        quantity=5,
        unit_price=Decimal("15000.00"),
        unit_cost=Decimal("12000.00"),
        payment_method="CASH",
        sold_by=manager_user,
    )
    return sale


@pytest.fixture
def authenticated_client(manager_user, cement_business):
    """Return an authenticated client with business context."""
    client = Client()
    client.login(username="cement_manager", password="testpass123")
    # Set session for business
    session = client.session
    session["active_business_id"] = cement_business.pk
    session.save()
    return client


class TestCostsUICardRadios(TestCase):
    """Tests for costs page with category card radio buttons."""
    
    @pytest.fixture(autouse=True)
    def setup_fixtures(self, cement_business, manager_user, authenticated_client):
        self.business = cement_business
        self.user = manager_user
        self.client = authenticated_client
    
    def test_costs_page_renders_category_radios_not_select(self):
        """GET costs page should render category options as radio inputs, not select."""
        response = self.client.get(reverse("cement:costs"))
        
        # Should not contain <select> for category
        content = response.content.decode()
        assert '<select' not in content.lower() or 'name="category"' not in content
        
        # Should contain radio inputs for categories
        assert 'type="radio"' in content
        assert 'name="category"' in content
        
        # Should contain the card container class
        assert 'cc-category-cards' in content
    
    def test_costs_page_has_transport_labor_rent_utilities_options(self):
        """Costs page should have all category options."""
        response = self.client.get(reverse("cement:costs"))
        content = response.content.decode()
        
        # Check for category values in radio inputs
        assert 'value="transport"' in content
        assert 'value="labor"' in content
        assert 'value="rent"' in content
        assert 'value="utilities"' in content
        assert 'value="other"' in content


class TestCementDashboardBlueTheme(TestCase):
    """Tests for cement dashboard blue theme."""
    
    @pytest.fixture(autouse=True)
    def setup_fixtures(self, cement_business, manager_user, authenticated_client):
        self.business = cement_business
        self.user = manager_user
        self.client = authenticated_client
    
    def test_dashboard_contains_blue_theme_class(self):
        """Dashboard should contain the cement vertical class with blue theme."""
        response = self.client.get(reverse("cement:dashboard"))
        content = response.content.decode()
        
        # Should contain vertical-cement class
        assert 'vertical-cement' in content
    
    def test_dashboard_hero_has_blue_gradient(self):
        """Dashboard hero should use blue gradient colors."""
        response = self.client.get(reverse("cement:dashboard"))
        content = response.content.decode()
        
        # Should contain blue gradient colors (sky blue family)
        assert '#0ea5e9' in content or '0ea5e9' in content.lower()


class TestCementSaleEditing(TestCase):
    """Tests for cement sale editing functionality."""
    
    @pytest.fixture(autouse=True)
    def setup_fixtures(
        self, cement_business, manager_user, agent_user, 
        cement_product, cement_sale, authenticated_client
    ):
        self.business = cement_business
        self.manager = manager_user
        self.agent = agent_user
        self.product = cement_product
        self.sale = cement_sale
        self.client = authenticated_client
    
    def test_manager_can_access_edit_sale_page(self):
        """Manager should be able to access the edit sale page."""
        response = self.client.get(reverse("cement:edit_sale", args=[self.sale.id]))
        
        assert response.status_code == 200
        assert "Edit Sale" in response.content.decode() or "edit-page" in response.content.decode()
    
    def test_agent_cannot_access_edit_sale_page(self):
        """Agent should not be able to access the edit sale page."""
        # Login as agent
        agent_client = Client()
        agent_client.login(username="cement_agent", password="testpass123")
        session = agent_client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = agent_client.get(reverse("cement:edit_sale", args=[self.sale.id]))
        
        # Should redirect (to login or dashboard) or return forbidden
        assert response.status_code in [302, 403]
    
    def test_edit_sale_quantity_decrease_returns_stock(self):
        """Decreasing sale quantity should return stock to inventory."""
        from inventory.models import MerchProduct
        from inventory.models_verticals import CementSale
        
        original_stock = self.product.quantity_in_stock
        original_qty = self.sale.quantity
        
        # Edit sale: decrease quantity from 5 to 3
        response = self.client.post(
            reverse("cement:edit_sale", args=[self.sale.id]),
            {
                "quantity": 3,
                "unit_price": str(self.sale.unit_price),
                "payment_method": "CASH",
                "notes": "Edited for test",
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Refresh product
        self.product.refresh_from_db()
        
        # Stock should have increased by 2 (5 - 3 = 2 returned)
        expected_stock = original_stock + (original_qty - 3)
        assert self.product.quantity_in_stock == expected_stock
    
    def test_edit_sale_quantity_increase_reduces_stock(self):
        """Increasing sale quantity should reduce stock from inventory."""
        from inventory.models import MerchProduct
        
        original_stock = self.product.quantity_in_stock
        
        # Edit sale: increase quantity from 5 to 8
        response = self.client.post(
            reverse("cement:edit_sale", args=[self.sale.id]),
            {
                "quantity": 8,
                "unit_price": str(self.sale.unit_price),
                "payment_method": "CASH",
                "notes": "",
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Refresh product
        self.product.refresh_from_db()
        
        # Stock should have decreased by 3 (8 - 5 = 3 taken)
        expected_stock = original_stock - 3
        assert self.product.quantity_in_stock == expected_stock
    
    def test_edit_sale_price_updates_profit(self):
        """Changing sale price should update profit calculation."""
        from inventory.models_verticals import CementSale
        
        new_price = Decimal("18000.00")
        
        response = self.client.post(
            reverse("cement:edit_sale", args=[self.sale.id]),
            {
                "quantity": self.sale.quantity,
                "unit_price": str(new_price),
                "payment_method": "CASH",
                "notes": "",
            },
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Refresh sale
        self.sale.refresh_from_db()
        
        # Price should be updated
        assert self.sale.unit_price == new_price
        
        # Profit should be recalculated
        expected_profit = (new_price - self.sale.unit_cost) * self.sale.quantity
        assert self.sale.profit == expected_profit
    
    def test_cannot_edit_voided_sale(self):
        """Should not be able to edit a voided sale."""
        # Void the sale
        self.sale.is_void = True
        self.sale.save()
        
        response = self.client.get(reverse("cement:edit_sale", args=[self.sale.id]))
        
        # Should redirect with error message
        assert response.status_code == 302


class TestCementMobileNav(TestCase):
    """Tests for cement mobile navigation."""
    
    @pytest.fixture(autouse=True)
    def setup_fixtures(self, cement_business, manager_user, authenticated_client):
        self.business = cement_business
        self.user = manager_user
        self.client = authenticated_client
    
    def test_cement_page_has_correct_mobile_nav_items(self):
        """Cement page should have mobile nav with cement routes."""
        response = self.client.get(reverse("cement:dashboard"))
        content = response.content.decode()
        
        # Should contain cement-specific nav links
        assert '/cement/' in content
    
    def test_mobile_nav_items_for_cement_vertical(self):
        """Mobile nav should return cement-specific items for cement vertical."""
        from inventory.mobile_nav import get_mobile_nav_items
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get("/cement/dashboard/")
        request.user = self.user
        
        # Mock the business_vertical function to return CEMENT
        with patch("inventory.mobile_nav.business_vertical") as mock_vertical:
            mock_vertical.return_value = "cement"
            
            items = get_mobile_nav_items(request)
            
            # Should have 5 items: Home, Stock In, Sell, Products, More
            assert len(items) == 5
            
            # Check item keys
            keys = [item["key"] for item in items]
            assert "home" in keys
            assert "stock_in" in keys
            assert "sell" in keys
            assert "products" in keys
            assert "menu" in keys
            
            # Check URLs contain /cement/
            home_item = next(i for i in items if i["key"] == "home")
            assert "/cement/" in home_item["url"]


# ============================================================
# Run with pytest
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

