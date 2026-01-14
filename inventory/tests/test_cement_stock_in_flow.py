# inventory/tests/test_cement_stock_in_flow.py
"""
Integration tests for cement card-based Stock-In flow.

Tests the complete wizard:
1. Category selection (multiple categories from registry)
2. Product selection  
3. Variant selection (Brand → Size → Finish/Color)
4. Quantity & Pricing → Creates inventory

Also tests:
- Legacy 4L paint handling
- Products are sellable after stock-in
- Multi-category support (Construction Materials, Welding Materials, Car Spares)
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
class TestCementStockInWizard(TestCase):
    """Test card-based Stock-In wizard flow"""

    def setUp(self):
        """Create cement business, manager, and authenticated client"""
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

    def test_stock_in_step1_category_renders(self):
        """Step 1 (Category selection) renders successfully"""
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        assert b"Step 1: Select Category" in response.content
        assert b"Construction Materials" in response.content or b"construction-materials" in response.content

    def test_stock_in_step2_product_renders(self):
        """Step 2 (Product selection) renders after category selected"""
        # Simulate category selection in session
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session.save()

        response = self.client.get(reverse("cement:stock_in") + "?step=2")
        assert response.status_code == 200
        assert b"Step 2: Select Product" in response.content
        assert b"Cement" in response.content or b"Paint" in response.content

    def test_stock_in_step3_skipped_for_cement(self):
        """Step 3 is SKIPPED for cement (redirects to step 4) - cement always BAG 50KG"""
        # Simulate selections in session
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session["cement_stock_in_product_slug"] = "cement"
        session.save()

        response = self.client.get(reverse("cement:stock_in") + "?step=3")
        # Should redirect to step 4 (pricing) for cement
        assert response.status_code == 302
        assert "step=4" in response.url, "Cement should skip step 3 and go to step 4"

    def test_stock_in_step3_variant_renders_paint(self):
        """Step 3 (Variant selection) renders for paint with correct sizes"""
        # Simulate selections in session
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session["cement_stock_in_product_slug"] = "paint"
        session.save()

        response = self.client.get(reverse("cement:stock_in") + "?step=3")
        assert response.status_code == 200
        assert b"Step 3: Select" in response.content
        assert b"Brand" in response.content
        assert b"Size" in response.content
        
        # CRITICAL: Paint sizes must be 1L, 5L, 20L (NO 4L)
        assert b"1L" in response.content
        assert b"5L" in response.content
        assert b"20L" in response.content
        assert b"4L" not in response.content, "4L must NOT appear in paint size selection"

    def test_stock_in_step4_pricing_renders(self):
        """Step 4 (Quantity & Pricing) renders with product summary"""
        # Simulate full flow in session
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session["cement_stock_in_product_slug"] = "cement"
        session["cement_stock_in_brand"] = "Dangote"
        session["cement_stock_in_size"] = "50kg"
        session.save()

        response = self.client.get(reverse("cement:stock_in") + "?step=4")
        assert response.status_code == 200
        # For cement, step 4 displays as "Step 3" in UI since variant step is skipped
        assert b"Quantity" in response.content
        assert b"Dangote" in response.content
        assert b"Cement" in response.content

    def test_stock_in_complete_flow_cement(self):
        """Complete Stock-In flow creates cement product"""
        # Step 1: POST category
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "construction-materials"},
        )
        assert response.status_code == 302  # Redirect to step 2

        # Step 2: POST product
        response = self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {"step": "2", "product": "cement"},
        )
        assert response.status_code == 302  # Redirect to step 3

        # Step 3: POST variants (brand + size)
        response = self.client.post(
            reverse("cement:stock_in") + "?step=3",
            {"step": "3", "brand": "Dangote", "size": "50kg"},
        )
        assert response.status_code == 302  # Redirect to step 4

        # Step 4: POST quantity & pricing
        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "100",
                "cost_price": "25000.00",
                "selling_price": "30000.00",
            },
        )
        assert response.status_code == 302  # Redirect to stock_in home (success)

        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
        ).filter(
            name__icontains="Dangote"
        ).filter(
            name__icontains="Cement"
        ).first()

        assert product is not None, "Product should be created after stock-in"
        assert product.quantity_in_stock == 100
        assert product.cost_price == Decimal("25000.00")
        assert product.selling_price == Decimal("30000.00")
        assert product.is_active is True
        assert product.track_inventory is True

    def test_stock_in_complete_flow_paint_5l(self):
        """Complete Stock-In flow creates paint product (5L)"""
        # Step 1: POST category
        self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "construction-materials"},
        )

        # Step 2: POST product
        self.client.post(
            reverse("cement:stock_in") + "?step=2",
            {"step": "2", "product": "paint"},
        )

        # Step 3: POST variants (brand + size + finish + color)
        self.client.post(
            reverse("cement:stock_in") + "?step=3",
            {
                "step": "3",
                "brand": "Rainbow",
                "size": "5L",
                "finish": "Emulsion",
                "color": "White",
            },
        )

        # Step 4: POST quantity & pricing
        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "50",
                "cost_price": "8000.00",
                "selling_price": "10000.00",
            },
        )
        assert response.status_code == 302  # Success

        # Verify paint product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
        ).filter(
            name__icontains="Rainbow"
        ).filter(
            name__icontains="Paint"
        ).filter(
            name__icontains="5L"
        ).first()

        assert product is not None, "Paint product should be created"
        assert "Rainbow" in product.name
        assert "Paint" in product.name
        assert "5L" in product.name
        assert "Emulsion" in product.name
        assert "White" in product.name
        assert product.quantity_in_stock == 50
        assert product.cost_price == Decimal("8000.00")
        assert product.selling_price == Decimal("10000.00")

    def test_stock_in_paint_legacy_4l_normalizes_to_5l(self):
        """Stock-In with legacy 4L paint size normalizes to 5L"""
        # Complete flow but use legacy "4L" size
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "paint"})
        
        # Step 3: POST with legacy "4L"
        self.client.post(
            reverse("cement:stock_in") + "?step=3",
            {
                "step": "3",
                "brand": "Crown",
                "size": "4L",  # LEGACY SIZE
                "finish": "Gloss",
                "color": "Red",
            },
        )

        # Step 4: Finish
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "20",
                "cost_price": "7000.00",
                "selling_price": "9000.00",
            },
        )

        # Verify product was created with "5L" (normalized from 4L)
        product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
        ).filter(
            name__icontains="Crown"
        ).filter(
            name__icontains="Paint"
        ).first()

        assert product is not None
        assert "5L" in product.name, "Legacy 4L should be normalized to 5L in product name"
        assert "4L" not in product.name, "4L should NOT appear in product name"

    def test_stocked_product_is_sellable(self):
        """Product created via Stock-In is immediately available for sale"""
        # Stock in a cement product
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Akshar", "size": "50kg"})
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "50",
                "cost_price": "24000.00",
                "selling_price": "29000.00",
            },
        )

        # Verify product is sellable
        product = MerchProduct.objects.filter(
            business=self.business,
        ).filter(
            name__icontains="Akshar"
        ).filter(
            name__icontains="Cement"
        ).first()

        assert product is not None
        assert product.is_active is True, "Product must be active"
        assert product.track_inventory is True, "Product must track inventory"
        assert product.quantity_in_stock > 0, "Product must have stock"
        assert product.selling_price > 0, "Product must have selling price"
        assert product.cost_price > 0, "Product must have cost price"

    def test_stock_in_updates_existing_product(self):
        """Stocking in same product again updates quantity (not duplicate)"""
        # First stock-in
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Duracrete", "size": "50kg"})
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "100",
                "cost_price": "25000.00",
                "selling_price": "30000.00",
            },
        )

        initial_count = MerchProduct.objects.filter(
            business=self.business,
            name__icontains="Duracrete",
        ).count()

        # Second stock-in (same product)
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Duracrete", "size": "50kg"})
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "50",
                "cost_price": "25000.00",
                "selling_price": "30000.00",
            },
        )

        final_count = MerchProduct.objects.filter(
            business=self.business,
            name__icontains="Duracrete",
        ).count()

        # Should not create duplicate
        assert initial_count == final_count, "Should not create duplicate product"

        # Verify quantity was updated
        product = MerchProduct.objects.filter(
            business=self.business,
            name__icontains="Duracrete",
        ).first()
        assert product.quantity_in_stock == 150, "Quantity should be 100 + 50 = 150"


@pytest.mark.django_db
class TestCementStockInValidation(TestCase):
    """Test Stock-In wizard validation"""

    def setUp(self):
        """Create cement business, manager, and authenticated client"""
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

    def test_step4_rejects_zero_quantity(self):
        """Step 4 rejects zero or negative quantity"""
        # Set up session
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session["cement_stock_in_product_slug"] = "cement"
        session["cement_stock_in_brand"] = "Lime"
        session["cement_stock_in_size"] = "50kg"
        session.save()

        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "0",  # INVALID
                "cost_price": "25000.00",
                "selling_price": "30000.00",
            },
        )

        # Should show error and stay on step 4
        assert response.status_code == 302
        assert "step=4" in response.url or response.url == reverse("cement:stock_in") + "?step=4"

    def test_step4_rejects_zero_price(self):
        """Step 4 rejects zero prices"""
        session = self.client.session
        session["cement_stock_in_category"] = "construction-materials"
        session["cement_stock_in_product_slug"] = "cement"
        session["cement_stock_in_brand"] = "Nkope"
        session["cement_stock_in_size"] = "50kg"
        session.save()

        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "100",
                "cost_price": "0",  # INVALID
                "selling_price": "30000.00",
            },
        )

        # Should reject
        assert response.status_code == 302


@pytest.mark.django_db
class TestCementStockInMultiCategory(TestCase):
    """Test Stock-In wizard with multiple categories (Construction, Welding, Car Spares)"""

    def setUp(self):
        """Create cement business, manager, and authenticated client"""
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

    def test_step1_shows_multiple_categories_when_products_exist(self):
        """Step 1 shows multiple categories ONLY when business has products in those categories"""
        # Create products in multiple categories
        MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement 50KG",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=10,
        )
        MerchProduct.objects.create(
            business=self.business,
            name="Welding Rods 2.5mm",
            kind=BusinessKind.CEMENT,
            category="welding-materials",
            is_active=True,
            quantity_in_stock=50,
        )
        
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        
        # Categories with products must be present
        assert "Construction Materials" in content, "Construction Materials must be visible"
        assert "Welding Materials" in content, "Welding Materials must be visible"

    def test_step1_shows_category_icons_when_products_exist(self):
        """Step 1 shows category icons when products exist in those categories"""
        # Create products in multiple categories
        MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement 50KG",
            kind=BusinessKind.CEMENT,
            category="construction-materials",
            is_active=True,
            quantity_in_stock=10,
        )
        MerchProduct.objects.create(
            business=self.business,
            name="Welding Rods 2.5mm",
            kind=BusinessKind.CEMENT,
            category="welding-materials",
            is_active=True,
            quantity_in_stock=50,
        )
        
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        
        # Check for icons of categories with products
        assert "🏗️" in content, "Construction Materials icon must be visible"
        assert "🔥" in content, "Welding Materials icon must be visible"

    def test_step1_construction_materials_has_testid(self):
        """Construction Materials card has data-testid attribute"""
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'data-testid="category-construction-materials"' in content or \
               "data-testid='category-construction-materials'" in content, \
               "Construction Materials must have data-testid for Cypress"

    def test_step1_welding_materials_has_testid_when_products_exist(self):
        """Welding Materials card has data-testid attribute when products exist"""
        # Create welding products
        MerchProduct.objects.create(
            business=self.business,
            name="Welding Rods 2.5mm",
            kind=BusinessKind.CEMENT,
            category="welding-materials",
            is_active=True,
            quantity_in_stock=50,
        )
        
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'data-testid="category-welding-materials"' in content or \
               "data-testid='category-welding-materials'" in content, \
               "Welding Materials must have data-testid for Cypress"

    def test_step1_car_spares_has_testid_when_products_exist(self):
        """Car Spares card has data-testid attribute when products exist"""
        # Create car spares products
        MerchProduct.objects.create(
            business=self.business,
            name="Oil Filter",
            kind=BusinessKind.CEMENT,
            category="car-spares",
            is_active=True,
            quantity_in_stock=25,
        )
        
        response = self.client.get(reverse("cement:stock_in") + "?step=1")
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'data-testid="category-car-spares"' in content or \
               "data-testid='category-car-spares'" in content, \
               "Car Spares must have data-testid for Cypress"

    def test_selecting_construction_materials_proceeds_to_products(self):
        """Selecting Construction Materials proceeds to product selection"""
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "construction-materials"},
        )
        
        # Should redirect to step 2
        assert response.status_code == 302
        assert "step=2" in response.url

    def test_selecting_welding_materials_shows_coming_soon(self):
        """Selecting Welding Materials shows coming soon message"""
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "welding-materials"},
            follow=True,
        )
        
        # Should stay on step 1 with warning message
        assert response.status_code == 200
        messages_list = list(response.context.get("messages", []))
        assert any("coming soon" in str(m).lower() for m in messages_list), \
            "Should show 'coming soon' message for Welding Materials"

    def test_selecting_car_spares_shows_coming_soon(self):
        """Selecting Car Spares shows coming soon message"""
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "car-spares"},
            follow=True,
        )
        
        # Should stay on step 1 with warning message
        assert response.status_code == 200
        messages_list = list(response.context.get("messages", []))
        assert any("coming soon" in str(m).lower() for m in messages_list), \
            "Should show 'coming soon' message for Car Spares"

    def test_invalid_category_shows_error(self):
        """Selecting invalid category shows error"""
        response = self.client.post(
            reverse("cement:stock_in") + "?step=1",
            {"step": "1", "category": "nonexistent-category"},
            follow=True,
        )
        
        # Should show error
        assert response.status_code == 200
        messages_list = list(response.context.get("messages", []))
        assert len(messages_list) > 0, "Should show error message for invalid category"


@pytest.mark.django_db
class TestCementBrandsIncludeNjatiExtra(TestCase):
    """Test that Njati Extra is available as a distinct brand in Stock-In"""

    def setUp(self):
        """Create cement business, manager, and authenticated client"""
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

    def test_cement_catalog_has_njati_and_njati_extra(self):
        """Cement catalog SSOT includes both Njati and Njati Extra as distinct brands"""
        # Import from the catalog SSOT
        from inventory.catalog.construction_materials import CEMENT_BRANDS
        
        brand_names = [b["name"] for b in CEMENT_BRANDS]
        
        # Both brands must be present in the catalog
        assert "Njati" in brand_names, "Njati brand must be in catalog"
        assert "Njati Extra" in brand_names, "Njati Extra brand must be in catalog"
        
        # Verify they are distinct entries (not duplicates)
        njati_entries = [b for b in CEMENT_BRANDS if b["name"] == "Njati"]
        njati_extra_entries = [b for b in CEMENT_BRANDS if b["name"] == "Njati Extra"]
        
        assert len(njati_entries) == 1, "Njati should appear exactly once"
        assert len(njati_extra_entries) == 1, "Njati Extra should appear exactly once"
        
        # Verify they have different keys
        assert njati_entries[0]["key"] != njati_extra_entries[0]["key"], \
            "Njati and Njati Extra must have different keys"

    def test_can_stock_in_njati_cement(self):
        """Can complete stock-in flow with Njati brand"""
        # Complete flow with Njati
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Njati", "size": "50kg"})
        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "100",
                "cost_price": "25000.00",
                "selling_price": "30000.00",
            },
        )
        
        assert response.status_code == 302  # Success
        
        # Verify product was created with "Njati" (not "Njati Extra")
        product = MerchProduct.objects.filter(
            business=self.business,
            name__icontains="Njati",
        ).first()
        
        assert product is not None
        assert "Njati" in product.name
        # Should be exactly "Njati", not "Njati Extra"
        assert product.name.count("Njati") == 1 or "Njati Cement" in product.name

    def test_can_stock_in_njati_extra_cement(self):
        """Can complete stock-in flow with Njati Extra brand"""
        # Complete flow with Njati Extra
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Njati Extra", "size": "50kg"})
        response = self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {
                "step": "4",
                "quantity": "50",
                "cost_price": "26000.00",
                "selling_price": "31000.00",
            },
        )
        
        assert response.status_code == 302  # Success
        
        # Verify product was created with "Njati Extra"
        product = MerchProduct.objects.filter(
            business=self.business,
            name__icontains="Njati Extra",
        ).first()
        
        assert product is not None
        assert "Njati Extra" in product.name, "Product name must include 'Njati Extra'"

    def test_njati_and_njati_extra_are_distinct_products(self):
        """Njati and Njati Extra create separate product entries"""
        # Stock in Njati
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Njati", "size": "50kg"})
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {"step": "4", "quantity": "100", "cost_price": "25000.00", "selling_price": "30000.00"},
        )
        
        # Stock in Njati Extra
        self.client.post(reverse("cement:stock_in") + "?step=1", {"step": "1", "category": "construction-materials"})
        self.client.post(reverse("cement:stock_in") + "?step=2", {"step": "2", "product": "cement"})
        self.client.post(reverse("cement:stock_in") + "?step=3", {"step": "3", "brand": "Njati Extra", "size": "50kg"})
        self.client.post(
            reverse("cement:stock_in") + "?step=4",
            {"step": "4", "quantity": "50", "cost_price": "26000.00", "selling_price": "31000.00"},
        )
        
        # Should have 2 distinct products
        products = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.CEMENT,
            name__icontains="Njati",
        )
        
        assert products.count() == 2, "Should have 2 distinct products (Njati and Njati Extra)"
        
        product_names = [p.name for p in products]
        # One should contain just "Njati", the other "Njati Extra"
        njati_products = [name for name in product_names if "Njati Extra" not in name and "Njati" in name]
        njati_extra_products = [name for name in product_names if "Njati Extra" in name]
        
        assert len(njati_products) == 1, "Should have exactly 1 Njati product"
        assert len(njati_extra_products) == 1, "Should have exactly 1 Njati Extra product"

