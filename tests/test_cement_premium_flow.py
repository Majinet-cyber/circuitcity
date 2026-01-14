# tests/test_cement_premium_flow.py
"""
Tests for Cement Vertical Premium Flow:
- Phase 2: Stock-in category filter (cement-only by default)
- Phase 3: Skip variant step for cement (default BAG 50KG)
- Phase 5: Payment method as radio cards
- Phase 6: Smart pricing / margin feedback
- Phase 7: Premium dashboard KPIs
"""
import pytest
from decimal import Decimal
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.verticals.cement import (
    get_filtered_stock_in_categories,
    is_cement_product,
    get_cement_default_variant,
)


@pytest.fixture
def cement_business(db):
    """Create a cement business for testing."""
    from tenants.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(
        username="cement_tester",
        email="cement@test.com",
        password="testpass123"
    )
    
    business = Business.objects.create(
        name="Test Cement Shop",
        business_kind=BusinessKind.CEMENT,
        owner=user,
    )
    
    return business, user


class TestCementCategoryFilter:
    """Phase 2: Stock-in category filter tests."""
    
    def test_cement_only_by_default_no_products(self, cement_business):
        """Case A: No products => show only cement/construction-materials."""
        business, _ = cement_business
        
        categories = get_filtered_stock_in_categories(business)
        
        assert len(categories) == 1
        assert categories[0]["key"] == "construction-materials"
    
    def test_cement_only_when_only_cement_products(self, cement_business):
        """Case A: Only cement products => show only construction-materials."""
        business, _ = cement_business
        
        # Create cement product
        MerchProduct.objects.create(
            business=business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=10,
        )
        
        categories = get_filtered_stock_in_categories(business)
        
        assert len(categories) == 1
        assert categories[0]["key"] == "construction-materials"
    
    def test_multiple_categories_when_products_exist(self, cement_business):
        """Case B: Multiple category products => show those categories."""
        business, _ = cement_business
        
        # Create cement product
        MerchProduct.objects.create(
            business=business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=10,
        )
        
        # Create welding product
        MerchProduct.objects.create(
            business=business,
            name="Welding Rod 2.5mm",
            kind=BusinessKind.CEMENT,  # Same business kind, different category
            category="welding-materials",
            is_active=True,
            quantity_in_stock=50,
        )
        
        categories = get_filtered_stock_in_categories(business)
        category_keys = [cat["key"] for cat in categories]
        
        assert "construction-materials" in category_keys
        assert "welding-materials" in category_keys


class TestCementSkipVariantStep:
    """Phase 3: Skip variant step for cement tests."""
    
    def test_is_cement_product_returns_true(self):
        """Cement product slug should be identified correctly."""
        assert is_cement_product("cement") is True
    
    def test_is_cement_product_returns_false_for_paint(self):
        """Non-cement products should return False."""
        assert is_cement_product("paint") is False
        assert is_cement_product("iron-sheets") is False
    
    def test_cement_default_variant_has_50kg_size(self):
        """Default cement variant should be 50kg bag."""
        variant = get_cement_default_variant()
        
        assert variant["size"] == "50kg"
        assert "50KG" in variant["size_label"]


class TestCementPaymentMethodCards(TestCase):
    """Phase 5: Payment method as radio cards tests."""
    
    def setUp(self):
        from tenants.models import Business
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cement_sell_tester",
            email="sell@test.com",
            password="testpass123"
        )
        
        self.business = Business.objects.create(
            name="Test Cement Shop",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )
        
        # Create a cement product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=100,
            cost_price=Decimal("8000"),
            selling_price=Decimal("9500"),
            base_unit="bag",
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        # Set up session for sell step 3
        session = self.client.session
        session["cement_sell_product_id"] = self.product.id
        session["cement_sell_brand"] = "Dangote"
        session["active_business_id"] = self.business.id
        session.save()
    
    def test_sell_step3_renders_payment_cards_not_select(self):
        """Payment method should be radio cards, not a select dropdown."""
        response = self.client.get(reverse("cement:sell") + "?step=3")
        
        content = response.content.decode()
        
        # Should have payment cards
        assert 'data-testid="payment-method-cards"' in content
        assert 'payment-card' in content
        
        # Should have CASH, MOBILE_MONEY, BANK options
        assert 'data-method="CASH"' in content
        assert 'data-method="MOBILE_MONEY"' in content
        assert 'data-method="BANK"' in content
        
        # Should NOT have a select element for payment method
        assert '<select' not in content.lower() or 'payment_method' not in content.lower()


class TestCementMarginFeedback(TestCase):
    """Phase 6: Smart pricing / margin feedback tests."""
    
    def setUp(self):
        from tenants.models import Business
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cement_margin_tester",
            email="margin@test.com",
            password="testpass123"
        )
        
        self.business = Business.objects.create(
            name="Test Cement Shop",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )
        
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=100,
            cost_price=Decimal("8000"),
            selling_price=Decimal("9500"),
            base_unit="bag",
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["cement_sell_product_id"] = self.product.id
        session.save()
    
    def test_sell_page_has_margin_feedback_container(self):
        """Sell step 3 should have margin feedback elements."""
        response = self.client.get(reverse("cement:sell") + "?step=3")
        
        content = response.content.decode()
        
        # Should have margin badge
        assert 'margin-badge' in content
        # Should have profit display
        assert 'total-profit' in content
        # Should have sale summary section
        assert 'sale-summary' in content or 'Sale Summary' in content


class TestCementPremiumDashboard(TestCase):
    """Phase 7: Premium dashboard KPIs tests."""
    
    def setUp(self):
        from tenants.models import Business
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cement_dashboard_tester",
            email="dashboard@test.com",
            password="testpass123"
        )
        
        self.business = Business.objects.create(
            name="Test Cement Shop",
            business_kind=BusinessKind.CEMENT,
            owner=self.user,
        )
        
        # Create products with varying stock levels
        MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=100,
            cost_price=Decimal("8000"),
            selling_price=Decimal("9500"),
            base_unit="bag",
        )
        
        # Low stock product
        MerchProduct.objects.create(
            business=self.business,
            name="Akshar Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=2,  # Low stock
            cost_price=Decimal("7500"),
            selling_price=Decimal("9000"),
            base_unit="bag",
        )
        
        # Out of stock product
        MerchProduct.objects.create(
            business=self.business,
            name="Duracrete Cement BAG (50KG)",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=0,  # Out of stock
            cost_price=Decimal("7800"),
            selling_price=Decimal("9200"),
            base_unit="bag",
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
    
    def test_stock_list_has_kpi_strip(self):
        """Stock list page should have KPI strip."""
        response = self.client.get(reverse("cement:stock_list"))
        
        content = response.content.decode()
        
        # Should have KPI strip
        assert 'data-testid="kpi-strip"' in content
        # Should show total units
        assert 'Total Units' in content
        # Should show stock value
        assert 'Stock Value' in content
        # Should show potential profit
        assert 'Potential Profit' in content
    
    def test_stock_list_has_reorder_queue(self):
        """Stock list page should have reorder queue for low/out of stock items."""
        response = self.client.get(reverse("cement:stock_list"))
        
        content = response.content.decode()
        
        # Should have reorder queue
        assert 'data-testid="reorder-queue"' in content or 'Reorder Queue' in content
    
    def test_stock_list_has_warehouse_health_score(self):
        """Stock list page should have warehouse health score."""
        response = self.client.get(reverse("cement:stock_list"))
        
        content = response.content.decode()
        
        # Should have warehouse health score
        assert 'Warehouse Health Score' in content or 'Warehouse Score' in content

