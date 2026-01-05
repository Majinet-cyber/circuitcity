# inventory/tests/test_cement_seed_schema_safe.py
"""
Schema-safe tests for cement seed function.

Ensures the cement_seed.seed_cement_defaults() function:
1. Only uses fields that actually exist on MerchProduct
2. Creates valid cement products that pass model validation
3. Is idempotent (safe to call multiple times)
4. Only seeds for cement businesses
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import (
    CEMENT_BRANDS,
    get_cement_brands_list,
    is_cement_brand,
    normalize_cement_brand_name,
    seed_cement_defaults,
)
from inventory.models import MerchProduct
from tenants.models import Business


@pytest.mark.django_db
class TestCementSeedSchemaCompat:
    """Test cement seed uses only valid MerchProduct fields"""

    def test_seed_creates_valid_products(self):
        """Seed function must create products with valid schema fields only"""
        # Create cement business
        business = Business.objects.create(
            name="Cement Hardware",
            slug="cement-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )

        # Seed cement defaults
        result = seed_cement_defaults(business)

        # Verify products created
        assert result["created"] > 0
        assert result["skipped"] == 0

        # Verify all products pass validation
        products = MerchProduct.objects.filter(business=business)
        assert products.count() == len(CEMENT_BRANDS)

        for product in products:
            # These assertions ensure we only used fields that exist
            assert product.name  # CharField
            assert product.kind == BusinessKind.CEMENT
            assert product.category == "cement"
            assert product.base_unit == "bag"
            assert product.cost_price == Decimal("0.00")
            assert product.selling_price == Decimal("0.00")
            assert product.quantity_in_stock == 0
            assert product.is_active is True
            assert product.track_inventory is True

            # Ensure no invalid fields were set
            # (If seed tried to set invalid fields, it would have raised an error)

    def test_seed_is_idempotent(self):
        """Calling seed multiple times should not duplicate products"""
        business = Business.objects.create(
            name="Cement Store",
            slug="cement-store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )

        # First seed
        result1 = seed_cement_defaults(business)
        assert result1["created"] == len(CEMENT_BRANDS)
        assert result1["skipped"] == 0

        # Second seed (should skip all)
        result2 = seed_cement_defaults(business)
        assert result2["created"] == 0
        assert result2["skipped"] == len(CEMENT_BRANDS)

        # Verify no duplicates
        products = MerchProduct.objects.filter(business=business)
        assert products.count() == len(CEMENT_BRANDS)

    def test_seed_only_works_for_cement_businesses(self):
        """Seed should reject non-cement businesses"""
        grocery_business = Business.objects.create(
            name="Grocery Store",
            slug="grocery-store",
            business_kind=BusinessKind.GROCERY,
            status="ACTIVE",
        )

        result = seed_cement_defaults(grocery_business)
        assert result["created"] == 0
        assert "error" in result
        assert "Wrong business kind" in result["error"]

    def test_seed_handles_none_business(self):
        """Seed should handle None business gracefully"""
        result = seed_cement_defaults(None)
        assert result["created"] == 0
        assert "error" in result
        assert "No business provided" in result["error"]


@pytest.mark.django_db
class TestCementBrandHelpers:
    """Test cement brand helper functions"""

    def test_get_cement_brands_list(self):
        """get_cement_brands_list() returns proper format"""
        brands = get_cement_brands_list()
        assert len(brands) == len(CEMENT_BRANDS)

        for brand in brands:
            assert "key" in brand
            assert "name" in brand
            assert "icon" in brand

    def test_is_cement_brand(self):
        """is_cement_brand() recognizes brands and aliases"""
        assert is_cement_brand("Dangote") is True
        assert is_cement_brand("dangote") is True
        assert is_cement_brand("DANGOTE") is True
        assert is_cement_brand("Akshar") is True
        assert is_cement_brand("aksher") is True  # alias
        assert is_cement_brand("Not A Brand") is False

    def test_normalize_cement_brand_name(self):
        """normalize_cement_brand_name() returns canonical name"""
        assert normalize_cement_brand_name("aksher") == "Akshar"
        assert normalize_cement_brand_name("AKSHAR") == "Akshar"
        assert normalize_cement_brand_name("akshar") == "Akshar"
        assert normalize_cement_brand_name("Dangote") == "Dangote"
        assert normalize_cement_brand_name("Custom Brand") == "Custom Brand"  # pass-through


@pytest.mark.django_db
class TestCementSeedEdgeCases:
    """Test cement seed edge cases"""

    def test_seed_handles_existing_products_by_alias(self):
        """Seed should detect existing products even if created with alias"""
        business = Business.objects.create(
            name="Hardware Store",
            slug="hardware-store",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )

        # Manually create product with alias name
        MerchProduct.objects.create(
            business=business,
            name="aksher",  # Using alias instead of canonical "Akshar"
            kind=BusinessKind.CEMENT,
            category="cement",
            base_unit="bag",
            cost_price=Decimal("8000.00"),
            selling_price=Decimal("9000.00"),
            quantity_in_stock=100,
        )

        # Seed should skip "Akshar" because "aksher" alias already exists
        result = seed_cement_defaults(business)
        assert result["skipped"] >= 1  # At least Akshar should be skipped

        # Verify no duplicate created
        akshar_products = MerchProduct.objects.filter(
            business=business,
            name__iexact="akshar",
        )
        assert akshar_products.count() == 0  # No "Akshar" created

        aksher_products = MerchProduct.objects.filter(
            business=business,
            name__iexact="aksher",
        )
        assert aksher_products.count() == 1  # Original "aksher" still exists

    def test_seed_preserves_existing_product_data(self):
        """Seed should not modify existing products"""
        business = Business.objects.create(
            name="Hardware Store",
            slug="hardware-2",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
        )

        # Create product with custom pricing
        existing_product = MerchProduct.objects.create(
            business=business,
            name="Dangote",
            kind=BusinessKind.CEMENT,
            category="cement",
            base_unit="bag",
            cost_price=Decimal("7500.00"),
            selling_price=Decimal("8500.00"),
            quantity_in_stock=250,
        )

        # Seed
        result = seed_cement_defaults(business)
        assert result["skipped"] >= 1

        # Verify existing product unchanged
        existing_product.refresh_from_db()
        assert existing_product.cost_price == Decimal("7500.00")
        assert existing_product.selling_price == Decimal("8500.00")
        assert existing_product.quantity_in_stock == 250
