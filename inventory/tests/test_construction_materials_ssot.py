# inventory/tests/test_construction_materials_ssot.py
"""
Unit tests for Construction Materials SSOT catalog.

Tests:
- Paint sizes are exactly 1L, 5L, 20L (NO 4L)
- Legacy 4L redirects/normalizes to 5L
- Cement brands have no duplicates
- Product name building works correctly
- SSOT catalog functions work as expected
"""
import pytest

from inventory.catalog.construction_materials import (
    CEMENT_BRANDS,
    PAINT_SIZES,
    build_product_name,
    get_all_products,
    get_cement_brands,
    get_paint_sizes,
    get_product_by_slug,
    is_valid_paint_size,
    normalize_paint_size,
)


class TestPaintSizes:
    """Test paint size definitions and legacy handling"""

    def test_paint_sizes_malawi_correct(self):
        """Paint sizes must be exactly 1L, 5L, 20L (Malawi standard)"""
        assert PAINT_SIZES == ["1L", "5L", "20L"], "Paint sizes must be 1L, 5L, 20L (NO 4L)"

    def test_get_paint_sizes(self):
        """get_paint_sizes() returns correct sizes"""
        sizes = get_paint_sizes()
        assert sizes == ["1L", "5L", "20L"]

    def test_no_4l_in_paint_sizes(self):
        """4L must NOT be in paint sizes"""
        assert "4L" not in PAINT_SIZES
        assert "4l" not in PAINT_SIZES

    def test_legacy_4l_normalizes_to_5l(self):
        """Legacy 4L paint size normalizes to 5L"""
        assert normalize_paint_size("4L") == "5L"
        assert normalize_paint_size("4l") == "5L"

    def test_valid_sizes_pass_through(self):
        """Valid paint sizes pass through normalization unchanged"""
        assert normalize_paint_size("1L") == "1L"
        assert normalize_paint_size("5L") == "5L"
        assert normalize_paint_size("20L") == "20L"

    def test_invalid_size_defaults_to_5l(self):
        """Invalid/unrecognized sizes default to 5L"""
        assert normalize_paint_size("10L") == "5L"
        assert normalize_paint_size("") == "1L"  # Empty defaults to first size
        assert normalize_paint_size(None) == "1L"

    def test_is_valid_paint_size_recognizes_legacy(self):
        """is_valid_paint_size() accepts legacy 4L for redirect purposes"""
        assert is_valid_paint_size("1L") is True
        assert is_valid_paint_size("5L") is True
        assert is_valid_paint_size("20L") is True
        assert is_valid_paint_size("4L") is True  # Legacy - redirects
        assert is_valid_paint_size("4l") is True  # Legacy - redirects
        assert is_valid_paint_size("10L") is False  # Invalid


class TestCementBrands:
    """Test cement brand definitions (no duplicates)"""

    def test_cement_brands_no_duplicates(self):
        """Cement brand names must be unique (case-insensitive)"""
        brand_names = [b["name"].lower() for b in CEMENT_BRANDS]
        assert len(brand_names) == len(set(brand_names)), "Cement brands must be unique"

    def test_cement_brands_no_njati_extra(self):
        """'Njati Extra' should be DISTINCT from 'Njati' (separate brand)"""
        brand_names = [b["name"] for b in CEMENT_BRANDS]
        assert "Njati" in brand_names, "Njati must be in brand list"
        assert "Njati Extra" in brand_names, "Njati Extra must be in brand list (distinct brand)"
        
        # Verify they are distinct entries
        njati_count = sum(1 for b in CEMENT_BRANDS if "Njati" in b["name"])
        assert njati_count == 2, "Should have exactly 2 Njati variants: 'Njati' and 'Njati Extra'"

    def test_cement_brands_akshar_normalized(self):
        """'Akshar' (not 'Aksher') is the canonical spelling"""
        brand_names = [b["name"] for b in CEMENT_BRANDS]
        assert "Akshar" in brand_names, "Akshar must be in brand list"
        assert "Aksher" not in brand_names, "Aksher is old spelling, should be Akshar"

    def test_get_cement_brands(self):
        """get_cement_brands() returns canonical brand list"""
        brands = get_cement_brands()
        assert len(brands) > 0
        assert all("key" in b and "name" in b and "icon" in b for b in brands)

    def test_cement_brand_count(self):
        """Expected number of canonical cement brands"""
        # Expected: Dangote, Akshar, Duracrete, Khoma, Lime, Njati, Njati Extra, Nkope, Nthanthwe
        assert len(CEMENT_BRANDS) == 9, f"Expected 9 canonical brands (including Njati Extra), got {len(CEMENT_BRANDS)}"


class TestProductNameBuilding:
    """Test product name building from SSOT"""

    def test_build_cement_product_name(self):
        """Cement product names built correctly"""
        name = build_product_name("cement", brand="Dangote", size="50kg")
        assert "Dangote" in name
        assert "Cement" in name
        assert "BAG" in name or "50" in name

    def test_build_paint_product_name(self):
        """Paint product names built correctly"""
        name = build_product_name("paint", brand="Rainbow", size="5L", finish="Emulsion", color="White")
        assert "Rainbow" in name
        assert "Paint" in name
        assert "5L" in name
        assert "Emulsion" in name
        assert "White" in name

    def test_build_paint_name_without_optional_variants(self):
        """Paint name builds without optional color/finish"""
        name = build_product_name("paint", brand="Rainbow", size="5L")
        assert "Rainbow" in name
        assert "Paint" in name
        assert "5L" in name

    def test_build_iron_sheets_name(self):
        """Iron sheets name builds with gauge and color"""
        name = build_product_name("iron-sheets", size="3.0m", gauge="28", color="Galvanized")
        assert "Iron Sheets" in name
        assert "3.0m" in name
        assert "Gauge 28" in name
        assert "Galvanized" in name


class TestCatalogFunctions:
    """Test SSOT catalog helper functions"""

    def test_get_all_products(self):
        """get_all_products() returns construction products"""
        products = get_all_products()
        assert len(products) > 0
        assert any(p["slug"] == "cement" for p in products)
        assert any(p["slug"] == "paint" for p in products)

    def test_get_product_by_slug_cement(self):
        """get_product_by_slug() retrieves cement product"""
        cement = get_product_by_slug("cement")
        assert cement is not None
        assert cement["slug"] == "cement"
        assert cement["base_name"] == "Cement"
        assert cement["default_unit"] == "bag"

    def test_get_product_by_slug_paint(self):
        """get_product_by_slug() retrieves paint product"""
        paint = get_product_by_slug("paint")
        assert paint is not None
        assert paint["slug"] == "paint"
        assert paint["base_name"] == "Paint"
        assert paint["default_unit"] == "tin"
        
        # Verify paint sizes come from SSOT
        sizes = [s["key"] for s in paint["sizes"]]
        assert sizes == ["1L", "5L", "20L"]

    def test_get_product_by_slug_not_found(self):
        """get_product_by_slug() returns None for unknown product"""
        assert get_product_by_slug("nonexistent") is None

    def test_paint_product_has_correct_variants(self):
        """Paint product has correct variant structure"""
        paint = get_product_by_slug("paint")
        assert paint["variants"] is not None
        assert "finishes" in paint["variants"]
        assert "colors" in paint["variants"]
        assert len(paint["variants"]["finishes"]) > 0
        assert len(paint["variants"]["colors"]) > 0


@pytest.mark.django_db
class TestSSotIntegration:
    """Integration tests - ensure SSOT is used correctly"""

    def test_cement_seed_uses_ssot(self):
        """cement_seed.py uses SSOT brands (including Njati Extra)"""
        from inventory.cement_seed import CEMENT_CATALOG

        # Check no duplicates in seeded products
        product_names = [p["name"].lower() for p in CEMENT_CATALOG]
        assert len(product_names) == len(set(product_names)), "Seeded products must be unique"

        # Check that both Njati and Njati Extra are in seed
        assert any("njati cement" in name.lower() and "extra" not in name.lower() for name in product_names), \
            "Njati should be in cement seed"
        assert any("njati extra" in name.lower() for name in product_names), \
            "Njati Extra should be in cement seed (distinct from Njati)"

    def test_hardware_catalog_uses_ssot_paint_sizes(self):
        """hardware.py catalog uses SSOT paint sizes (1L, 5L, 20L)"""
        from inventory.catalog.hardware import HARDWARE_CATALOG
        
        paint_product = next((p for p in HARDWARE_CATALOG if p["slug"] == "paint"), None)
        assert paint_product is not None
        
        paint_sizes = paint_product["variation_schema"]["sizes"]
        assert paint_sizes == ["1L", "5L", "20L"], "Hardware catalog must use SSOT paint sizes"
        assert "4L" not in paint_sizes, "4L must NOT be in hardware catalog sizes"

