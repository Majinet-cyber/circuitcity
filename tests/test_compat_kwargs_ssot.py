"""
tests/test_compat_kwargs_ssot.py

SSOT Unit tests for backwards-compatible kwargs mapping on models.

These tests ensure that legacy kwargs are properly mapped to canonical fields
without raising TypeError, maintaining backwards compatibility while establishing
the Single Source of Truth (SSOT) for field names.

Run with: pytest tests/test_compat_kwargs_ssot.py -v
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase

from tenants.models import Business
from inventory.models import Location, Product, MerchProduct, InventoryItem

User = get_user_model()


@pytest.mark.django_db
class TestBusinessCompatKwargs:
    """Test Business model accepts legacy kwargs without TypeError."""

    def test_business_owner_maps_to_created_by(self):
        """Test that 'owner' kwarg maps to 'created_by' field."""
        user = User.objects.create_user(
            username="testowner",
            email="owner@test.com",
            password="testpass123"
        )
        
        # Legacy kwarg: owner
        business = Business.objects.create(
            name="Owner Test Shop",
            slug="owner-test-shop",
            owner=user,  # Legacy kwarg
        )
        
        # Verify mapping to canonical field
        assert business.created_by == user
        business.delete()

    def test_business_owner_email_ignored(self):
        """Test that 'owner_email' kwarg is accepted but ignored (no field exists)."""
        # Should not raise TypeError even though owner_email doesn't map to a field
        business = Business.objects.create(
            name="Email Test Shop",
            slug="email-test-shop",
            owner_email="test@example.com",  # Legacy kwarg (ignored)
        )
        
        # Should create successfully
        assert business.name == "Email Test Shop"
        business.delete()

    def test_business_kind_alias_vertical(self):
        """Test that 'vertical' kwarg maps to 'business_kind' field."""
        business = Business.objects.create(
            name="Vertical Test Shop",
            slug="vertical-test-shop",
            vertical="phones",  # Legacy kwarg
        )
        
        assert business.business_kind == "phones"
        business.delete()

    def test_business_kind_alias_kind(self):
        """Test that 'kind' kwarg maps to 'business_kind' field."""
        business = Business.objects.create(
            name="Kind Test Shop",
            slug="kind-test-shop",
            kind="liquor",  # Legacy kwarg
        )
        
        assert business.business_kind == "liquor"
        business.delete()

    def test_business_canonical_takes_precedence(self):
        """Test that canonical field takes precedence over legacy kwarg."""
        user1 = User.objects.create_user(username="user1", email="u1@test.com", password="pass")
        user2 = User.objects.create_user(username="user2", email="u2@test.com", password="pass")
        
        business = Business.objects.create(
            name="Precedence Test",
            slug="precedence-test",
            created_by=user1,  # Canonical field
            owner=user2,  # Legacy kwarg (should be ignored)
        )
        
        # Canonical field should win
        assert business.created_by == user1
        business.delete()


@pytest.mark.django_db
class TestLocationCompatKwargs:
    """Test Location model accepts legacy kwargs without TypeError."""

    def setup_method(self):
        """Create a business for location tests."""
        self.business = Business.objects.create(
            name="Location Test Business",
            slug="loc-test-biz",
            status="ACTIVE",
        )
        # Clean up any auto-created locations from signals
        Location.objects.filter(business=self.business).delete()

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'business') and self.business.pk:
            # Delete locations first to avoid constraint issues
            Location.objects.filter(business=self.business).delete()
            self.business.delete()

    def test_location_is_headquarters_maps_to_is_default(self):
        """Test that 'is_headquarters' kwarg maps to 'is_default' field."""
        location = Location.objects.create(
            business=self.business,
            name="HQ Location",
            is_headquarters=True,  # Legacy kwarg
        )
        
        assert location.is_default is True
        location.delete()

    def test_location_address_maps_to_city(self):
        """Test that 'address' kwarg maps to 'city' field."""
        location = Location.objects.create(
            business=self.business,
            name="Address Test Location",
            address="123 Main St, Lilongwe",  # Legacy kwarg
        )
        
        assert location.city == "123 Main St, Lilongwe"
        location.delete()

    def test_location_is_active_maps_to_is_default(self):
        """Test that 'is_active' kwarg maps to 'is_default' field."""
        location = Location.objects.create(
            business=self.business,
            name="Active Location",
            is_active=True,  # Legacy kwarg
        )
        
        assert location.is_default is True
        location.delete()

    def test_location_multiple_legacy_kwargs(self):
        """Test that multiple legacy kwargs can be used together."""
        location = Location.objects.create(
            business=self.business,
            name="Multi Legacy",
            is_headquarters=True,  # Legacy kwarg
            address="Downtown",  # Legacy kwarg
        )
        
        assert location.is_default is True
        assert location.city == "Downtown"
        location.delete()


@pytest.mark.django_db
class TestProductCompatKwargs:
    """Test Product model accepts legacy kwargs without TypeError."""

    def test_product_business_kwarg_ignored(self):
        """Test that 'business' kwarg is accepted but ignored (Product is global)."""
        business = Business.objects.create(
            name="Test Biz",
            slug="test-biz",
        )
        
        # Should not raise TypeError even though Product doesn't have business FK
        product = Product.objects.create(
            code="TEST001",
            brand="TestBrand",
            model="TestModel",
            business=business,  # Legacy kwarg (ignored)
        )
        
        assert product.brand == "TestBrand"
        assert not hasattr(product, 'business')  # Product is global, no business FK
        product.delete()
        business.delete()

    def test_product_order_price_kwarg_ignored(self):
        """Test that 'order_price' kwarg is accepted but ignored (field is on InventoryItem)."""
        product = Product.objects.create(
            code="TEST002",
            brand="TestBrand",
            model="TestModel2",
            order_price=Decimal("100.00"),  # Legacy kwarg (ignored)
        )
        
        assert product.model == "TestModel2"
        # order_price is on InventoryItem, not Product
        product.delete()

    def test_product_selling_price_kwarg_ignored(self):
        """Test that 'selling_price' kwarg is accepted but ignored."""
        product = Product.objects.create(
            code="TEST003",
            brand="TestBrand",
            model="TestModel3",
            selling_price=Decimal("150.00"),  # Legacy kwarg (ignored)
        )
        
        assert product.model == "TestModel3"
        product.delete()

    def test_product_multiple_ignored_kwargs(self):
        """Test that multiple ignored kwargs can be used together."""
        business = Business.objects.create(name="Test", slug="test")
        
        product = Product.objects.create(
            code="TEST004",
            brand="TestBrand",
            model="TestModel4",
            business=business,  # Ignored
            order_price=Decimal("100.00"),  # Ignored
            selling_price=Decimal("150.00"),  # Ignored
        )
        
        assert product.model == "TestModel4"
        product.delete()
        business.delete()


@pytest.mark.django_db
class TestMerchProductCompatKwargs:
    """Test MerchProduct model accepts legacy kwargs without TypeError."""

    def setup_method(self):
        """Create a business for MerchProduct tests."""
        self.business = Business.objects.create(
            name="Merch Test Business",
            slug="merch-test-biz",
            status="ACTIVE",
        )
        # Clean up any auto-created locations from signals
        Location.objects.filter(business=self.business).delete()

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'business') and self.business.pk:
            Location.objects.filter(business=self.business).delete()
            self.business.delete()

    def test_merchproduct_model_maps_to_name(self):
        """Test that 'model' kwarg maps to 'name' field."""
        product = MerchProduct.objects.create(
            business=self.business,
            model="Legacy Product Name",  # Legacy kwarg
            kind="grocery",
        )
        
        assert product.name == "Legacy Product Name"
        product.delete()

    def test_merchproduct_cost_maps_to_cost_price(self):
        """Test that 'cost' kwarg maps to 'cost_price' field."""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Cost Test Product",
            cost=Decimal("50.00"),  # Legacy kwarg
        )
        
        assert product.cost_price == Decimal("50.00")
        product.delete()

    def test_merchproduct_sell_price_maps_to_selling_price(self):
        """Test that 'sell_price' kwarg maps to 'selling_price' field."""
        product = MerchProduct.objects.create(
            business=self.business,
            name="Sell Price Test",
            sell_price=Decimal("75.00"),  # Legacy kwarg
        )
        
        assert product.selling_price == Decimal("75.00")
        product.delete()

    def test_merchproduct_all_legacy_kwargs(self):
        """Test that all legacy kwargs can be used together."""
        product = MerchProduct.objects.create(
            business=self.business,
            model="Full Legacy Product",  # Legacy: maps to name
            cost=Decimal("40.00"),  # Legacy: maps to cost_price
            sell_price=Decimal("60.00"),  # Legacy: maps to selling_price
            kind="clothing",
        )
        
        assert product.name == "Full Legacy Product"
        assert product.cost_price == Decimal("40.00")
        assert product.selling_price == Decimal("60.00")
        product.delete()


@pytest.mark.django_db(transaction=True)
class TestInventoryItemCompatKwargs:
    """Test InventoryItem model accepts legacy kwargs without TypeError."""

    def setup_method(self):
        """Create required objects for InventoryItem tests."""
        self.business = Business.objects.create(
            name="Inventory Test Business",
            slug="inv-test-biz",
            status="ACTIVE",
        )
        
        # Clean up any auto-created locations, then create our test location
        Location.objects.filter(business=self.business).delete()
        
        self.location = Location.objects.create(
            business=self.business,
            name="Test Location",
            is_default=True,
        )
        
        self.product = Product.objects.create(
            code="INV001",
            brand="TestBrand",
            model="TestModel",
        )

    # No teardown needed - pytest's transaction rollback handles cleanup

    def test_inventoryitem_brand_kwarg_ignored(self):
        """Test that 'brand' kwarg is accepted but ignored (brand is on Product FK)."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            brand="IgnoredBrand",  # Legacy kwarg (ignored)
            order_price=Decimal("100.00"),
        )
        
        # Brand is on Product, not InventoryItem
        assert item.product.brand == "TestBrand"
        # Soft delete instead of hard delete (signal blocks hard delete)
        item.is_active = False
        item.save()

    def test_inventoryitem_model_kwarg_ignored(self):
        """Test that 'model' kwarg is accepted but ignored (model is on Product FK)."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            model="IgnoredModel",  # Legacy kwarg (ignored)
            order_price=Decimal("100.00"),
        )
        
        # Model is on Product, not InventoryItem
        assert item.product.model == "TestModel"
        # Soft delete instead of hard delete
        item.is_active = False
        item.save()

    def test_inventoryitem_cost_maps_to_order_price(self):
        """Test that 'cost' kwarg maps to 'order_price' field."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            cost=Decimal("125.00"),  # Legacy kwarg
        )
        
        assert item.order_price == Decimal("125.00")
        # Soft delete instead of hard delete
        item.is_active = False
        item.save()

    def test_inventoryitem_sell_price_maps_to_selling_price(self):
        """Test that 'sell_price' kwarg maps to 'selling_price' field."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100.00"),
            sell_price=Decimal("150.00"),  # Legacy kwarg
        )
        
        assert item.selling_price == Decimal("150.00")
        # Soft delete instead of hard delete
        item.is_active = False
        item.save()

    def test_inventoryitem_all_legacy_kwargs(self):
        """Test that all legacy kwargs can be used together without TypeError."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            brand="IgnoredBrand",  # Legacy kwarg (ignored)
            model="IgnoredModel",  # Legacy kwarg (ignored)
            cost=Decimal("110.00"),  # Legacy kwarg (maps to order_price)
            sell_price=Decimal("165.00"),  # Legacy kwarg (maps to selling_price)
        )
        
        assert item.order_price == Decimal("110.00")
        assert item.selling_price == Decimal("165.00")
        # Brand and model are on Product FK, not InventoryItem
        assert item.product.brand == "TestBrand"
        assert item.product.model == "TestModel"
        # Soft delete instead of hard delete
        item.is_active = False
        item.save()


class TestCompatKwargsIntegration(TestCase):
    """Integration tests for compat kwargs across multiple models."""

    def test_full_stack_with_legacy_kwargs(self):
        """Test creating a complete inventory stack using only legacy kwargs."""
        # Create business with legacy kwargs
        user = User.objects.create_user(
            username="legacy_owner",
            email="legacy@test.com",
            password="testpass"
        )
        
        business = Business.objects.create(
            name="Full Stack Test",
            slug="full-stack-test",
            owner=user,  # Legacy
            owner_email="legacy@test.com",  # Legacy (ignored)
            vertical="phones",  # Legacy
        )
        
        # Clean up any auto-created locations
        Location.objects.filter(business=business).delete()
        
        # Create location with legacy kwargs
        location = Location.objects.create(
            business=business,
            name="Main Store",
            is_headquarters=True,  # Legacy
            address="Downtown",  # Legacy
        )
        
        # Create product with legacy kwargs
        product = Product.objects.create(
            code="FULL001",
            brand="TestBrand",
            model="TestModel",
            business=business,  # Legacy (ignored)
        )
        
        # Create inventory item with legacy kwargs
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            brand="IgnoredBrand",  # Legacy (ignored)
            model="IgnoredModel",  # Legacy (ignored)
            cost=Decimal("200.00"),  # Legacy
            sell_price=Decimal("300.00"),  # Legacy
        )
        
        # Verify all mappings worked
        assert business.created_by == user
        assert business.business_kind == "phones"
        assert location.is_default is True
        assert location.city == "Downtown"
        assert item.order_price == Decimal("200.00")
        assert item.selling_price == Decimal("300.00")

    def test_mixed_canonical_and_legacy_kwargs(self):
        """Test that canonical and legacy kwargs can be mixed safely."""
        business = Business.objects.create(
            name="Mixed Test",
            slug="mixed-test",
            business_kind="liquor",  # Canonical
            vertical="phones",  # Legacy (should be ignored in favor of canonical)
        )
        
        # Canonical field should take precedence
        assert business.business_kind == "liquor"

