# inventory/tests/test_catalog_registry.py
"""
Unit tests for Catalog Registry SSOT.

Tests:
- All required categories are present (Construction Materials, Welding Materials, Car Spares)
- Registry functions work correctly
- Categories have proper structure and metadata
"""
import pytest

from inventory.catalog.registry import (
    STOCK_IN_CATEGORIES,
    get_all_stock_in_categories,
    get_category_by_key,
    get_category_handler,
    is_category_enabled,
)


class TestCatalogRegistry:
    """Test catalog registry structure and content"""

    def test_registry_has_construction_materials(self):
        """Construction Materials category must be in registry"""
        categories = get_all_stock_in_categories()
        keys = [cat["key"] for cat in categories]
        assert "construction-materials" in keys, "Construction Materials must be in registry"

    def test_registry_has_welding_materials(self):
        """Welding Materials category must be in registry"""
        categories = get_all_stock_in_categories()
        keys = [cat["key"] for cat in categories]
        assert "welding-materials" in keys, "Welding Materials must be in registry"

    def test_registry_has_car_spares(self):
        """Car Spares category must be in registry"""
        categories = get_all_stock_in_categories()
        keys = [cat["key"] for cat in categories]
        assert "car-spares" in keys, "Car Spares must be in registry"

    def test_minimum_three_categories(self):
        """Registry must have at least 3 categories"""
        categories = get_all_stock_in_categories()
        assert len(categories) >= 3, f"Registry must have at least 3 categories, got {len(categories)}"

    def test_all_categories_have_required_fields(self):
        """All categories must have required fields"""
        required_fields = ["key", "label", "icon", "description", "handler", "enabled"]
        categories = get_all_stock_in_categories()
        
        for category in categories:
            for field in required_fields:
                assert field in category, f"Category {category.get('key', 'UNKNOWN')} missing field: {field}"

    def test_all_categories_have_data_testid(self):
        """All categories must have data-testid for Cypress tests"""
        categories = get_all_stock_in_categories()
        
        for category in categories:
            assert "data_testid" in category, f"Category {category['key']} missing data_testid"
            assert category["data_testid"].startswith("category-"), \
                f"data_testid should start with 'category-', got: {category['data_testid']}"

    def test_category_keys_are_unique(self):
        """Category keys must be unique"""
        all_keys = [cat["key"] for cat in STOCK_IN_CATEGORIES]
        assert len(all_keys) == len(set(all_keys)), "Category keys must be unique"

    def test_get_category_by_key_construction_materials(self):
        """get_category_by_key() returns correct category"""
        category = get_category_by_key("construction-materials")
        assert category is not None
        assert category["key"] == "construction-materials"
        assert category["label"] == "Construction Materials"
        assert category["icon"] == "🏗️"

    def test_get_category_by_key_welding_materials(self):
        """get_category_by_key() returns Welding Materials"""
        category = get_category_by_key("welding-materials")
        assert category is not None
        assert category["key"] == "welding-materials"
        assert category["label"] == "Welding Materials"
        assert category["icon"] == "🔥"

    def test_get_category_by_key_car_spares(self):
        """get_category_by_key() returns Car Spares"""
        category = get_category_by_key("car-spares")
        assert category is not None
        assert category["key"] == "car-spares"
        assert category["label"] == "Car Spares"
        assert category["icon"] == "🚗"

    def test_get_category_by_key_invalid_returns_none(self):
        """get_category_by_key() returns None for invalid key"""
        category = get_category_by_key("nonexistent-category")
        assert category is None

    def test_is_category_enabled_construction_materials(self):
        """Construction Materials should be enabled"""
        assert is_category_enabled("construction-materials") is True

    def test_is_category_enabled_welding_materials(self):
        """Welding Materials should be enabled"""
        assert is_category_enabled("welding-materials") is True

    def test_is_category_enabled_car_spares(self):
        """Car Spares should be enabled"""
        assert is_category_enabled("car-spares") is True

    def test_get_category_handler_construction_materials(self):
        """Construction Materials should have cement_flow handler"""
        handler = get_category_handler("construction-materials")
        assert handler == "cement_flow"

    def test_get_category_handler_welding_materials(self):
        """Welding Materials uses the generic form handler for stock-in"""
        handler = get_category_handler("welding-materials")
        assert handler == "generic_form"

    def test_get_category_handler_car_spares(self):
        """Car spares use the generic form handler for stock-in"""
        handler = get_category_handler("car-spares")
        assert handler == "generic_form"

    def test_construction_materials_distinct_from_others(self):
        """Construction Materials must be distinct from Welding/Car Spares"""
        categories = get_all_stock_in_categories()
        
        construction = next((c for c in categories if c["key"] == "construction-materials"), None)
        welding = next((c for c in categories if c["key"] == "welding-materials"), None)
        car = next((c for c in categories if c["key"] == "car-spares"), None)
        
        assert construction is not None
        assert welding is not None
        assert car is not None
        
        # Verify they are distinct
        assert construction["label"] != welding["label"]
        assert construction["label"] != car["label"]
        assert welding["label"] != car["label"]

