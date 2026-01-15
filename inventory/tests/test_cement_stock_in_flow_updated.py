# inventory/tests/test_cement_stock_in_flow_updated.py
"""
Updated cement stock-in flow tests matching NEW 2-step wizard (Jan 2026).

OLD FLOW (REMOVED):
- Step 1: Category → Step 2: Product Type → Step 3: Brand/Variant → Step 4: Pricing

NEW FLOW (SIMPLIFIED):
- Step 1: Select Cement Brand (from DB)
- Step 2: Quantity & Pricing

This file replaces test_cement_stock_in_flow.py with tests matching the actual implementation.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementStockInFlowUpdated(TestCase):
    """Test NEW 2-step cement stock-in flow"""

    def setUp(self):
        """Create cement business with seeded products"""
        self.user = User.objects.create_user(
            username="cement_manager",
            email="manager@cement.test",
            password="test1234",
        )
        self.business = Business.objects.create(
            name="Construction Hardware Store",
            slug="construction-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
        )

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Seed cement products
        from inventory.cement_seed import seed_cement_defaults
        seed_cement_defaults(self.business)

    def test_step1_renders_successfully(self):
        """Step 1 (brand selection) renders without errors"""
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        # Should contain cement-related content
        content = response.content.decode('utf-8')
        assert 'cement' in content.lower() or 'brand' in content.lower()

    def test_step1_shows_cement_brands(self):
        """Step 1 displays cement brand cards"""
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        content = response.content.decode('utf-8')
        
        # Should show at least one cement brand (seeded)
        # Common brands: Dangote, Akshar, Savannah, Shayona
        has_brand = any(brand in content for brand in ['Dangote', 'Akshar', 'Savannah', 'Shayona', 'Njati'])
        assert has_brand, "Step 1 should show at least one cement brand"

    def test_complete_stock_in_flow_cement(self):
        """Complete flow: select brand → add stock → success"""
        # Get a cement product
        cement_product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            category__icontains="cement",
            is_active=True
        ).first()
        
        assert cement_product is not None, "Should have seeded cement products"
        
        initial_stock = cement_product.quantity_in_stock
        
        # Step 1: Select brand
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"product_id": cement_product.id}
        )
        assert response.status_code == 302  # Redirect to step 2
        assert "?step=2" in response.url
        
        # Step 2: Add stock
        response = self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {
                "quantity": 15,
                "cost_price": "48000",
                "selling_price": "52000",
            }
        )
        
        assert response.status_code == 302  # Success redirect
        
        # Verify stock updated
        cement_product.refresh_from_db()
        assert cement_product.quantity_in_stock == initial_stock + 15
        assert cement_product.selling_price == Decimal("52000")

    def test_stocked_product_is_sellable(self):
        """Product stocked via wizard is immediately sellable"""
        cement_product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            category__icontains="cement",
            is_active=True
        ).first()
        
        # Stock in product
        self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"product_id": cement_product.id}
        )
        self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {
                "quantity": 10,
                "cost_price": "45000",
                "selling_price": "50000",
            }
        )
        
        cement_product.refresh_from_db()
        assert cement_product.quantity_in_stock > 0, "Product must have stock"
        assert cement_product.selling_price > 0, "Product must have selling price"
        assert cement_product.is_active, "Product must be active"

    def test_step2_rejects_zero_quantity(self):
        """Step 2 validation: zero quantity is rejected"""
        cement_product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            is_active=True
        ).first()
        
        # Set up session for step 2
        session = self.client.session
        session["cement_stock_in_product_id"] = cement_product.id
        session.save()
        
        response = self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {
                "quantity": 0,  # Invalid
                "cost_price": "45000",
                "selling_price": "50000",
            }
        )
        
        # Should redirect back to step 2 (error)
        assert response.status_code == 302
        assert "?step=2" in response.url

    def test_step2_rejects_zero_price(self):
        """Step 2 validation: zero prices are rejected"""
        cement_product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            is_active=True
        ).first()
        
        session = self.client.session
        session["cement_stock_in_product_id"] = cement_product.id
        session.save()
        
        response = self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {
                "quantity": 10,
                "cost_price": 0,  # Invalid
                "selling_price": 0,  # Invalid
            }
        )
        
        # Should redirect back with error
        assert response.status_code == 302

    def test_stock_in_updates_existing_product(self):
        """Stocking in same product twice updates quantity (no duplicate)"""
        cement_product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            is_active=True
        ).first()
        
        initial_stock = cement_product.quantity_in_stock
        
        # First stock-in
        self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"product_id": cement_product.id}
        )
        self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {"quantity": 50, "cost_price": "45000", "selling_price": "50000"}
        )
        
        cement_product.refresh_from_db()
        after_first = cement_product.quantity_in_stock
        
        # Second stock-in (same product)
        self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"product_id": cement_product.id}
        )
        self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {"quantity": 50, "cost_price": "46000", "selling_price": "51000"}
        )
        
        cement_product.refresh_from_db()
        
        # Should have 100 total (50 + 50), not create duplicate product
        assert cement_product.quantity_in_stock == after_first + 50
        
        # Verify only ONE product exists for this brand
        brand_products = MerchProduct.objects.filter(
            business=self.business,
            name=cement_product.name,
            is_active=True
        )
        assert brand_products.count() == 1, "Should not create duplicate products"


@pytest.mark.django_db
class TestCementStockInEdgeCases(TestCase):
    """Edge cases and error handling"""

    def setUp(self):
        """Setup test fixtures"""
        self.user = User.objects.create_user(
            username="manager", email="mgr@test.com", password="pass"
        )
        self.business = Business.objects.create(
            name="Store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")
        
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Seed products
        from inventory.cement_seed import seed_cement_defaults
        seed_cement_defaults(self.business)

    def test_step2_without_step1_redirects(self):
        """Accessing step 2 without completing step 1 redirects"""
        response = self.client.get(reverse("cement:stock_in") + "?step=2")
        
        # Should redirect (no session data)
        assert response.status_code == 302

    def test_invalid_product_id_rejected(self):
        """Invalid product ID in step 1 is handled gracefully"""
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"product_id": 999999}  # Non-existent
        )
        
        # Should redirect with error
        assert response.status_code == 302
        assert "?step=1" in response.url

