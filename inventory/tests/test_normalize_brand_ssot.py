# inventory/tests/test_normalize_brand_ssot.py
"""
Tests for brand normalization with alias support.

Requirements:
- normalize_brand("aksher") must return "Akshar"
- normalize_brand("akshar") must return "Akshar"
- normalize_brand("AKSHAR") must return "Akshar"
- is_cement_brand("aksher") must be True
- All aliases must be handled correctly
"""
import pytest

from inventory.catalog.construction_materials import normalize_brand
from inventory.cement_seed import is_cement_brand, normalize_cement_brand_name


class TestBrandNormalizationSSoT:
    """Test brand normalization from SSOT (construction_materials.py)"""

    def test_normalize_brand_aksher_alias(self):
        """normalize_brand("aksher") must return "Akshar" (typo alias)"""
        assert normalize_brand("aksher", "cement") == "Akshar"

    def test_normalize_brand_akshar_canonical(self):
        """normalize_brand("akshar") must return "Akshar" (canonical)"""
        assert normalize_brand("akshar", "cement") == "Akshar"

    def test_normalize_brand_case_insensitive(self):
        """normalize_brand() must be case-insensitive"""
        assert normalize_brand("AKSHAR", "cement") == "Akshar"
        assert normalize_brand("AkShAr", "cement") == "Akshar"
        assert normalize_brand("aksher", "cement") == "Akshar"
        assert normalize_brand("AKSHER", "cement") == "Akshar"

    def test_normalize_brand_other_cement_brands(self):
        """normalize_brand() works for other cement brands"""
        assert normalize_brand("dangote", "cement") == "Dangote"
        assert normalize_brand("DANGOTE", "cement") == "Dangote"
        assert normalize_brand("duracrete", "cement") == "Duracrete"
        assert normalize_brand("khoma", "cement") == "Khoma"
        assert normalize_brand("njati", "cement") == "Njati"

    def test_normalize_brand_njati_extra_distinct(self):
        """normalize_brand() treats "Njati Extra" as distinct from "Njati" """
        assert normalize_brand("njati extra", "cement") == "Njati Extra"
        assert normalize_brand("njatiextra", "cement") == "Njati Extra"
        assert normalize_brand("njati", "cement") == "Njati"

    def test_normalize_brand_custom_brand_passthrough(self):
        """normalize_brand() returns original name for unknown brands"""
        assert normalize_brand("CustomBrand", "cement") == "CustomBrand"
        assert normalize_brand("Unknown", "cement") == "Unknown"

    def test_normalize_brand_paint_brands(self):
        """normalize_brand() works for paint brands"""
        assert normalize_brand("rainbow", "paint") == "Rainbow"
        assert normalize_brand("RAINBOW", "paint") == "Rainbow"
        assert normalize_brand("crown", "paint") == "Crown"
        assert normalize_brand("plascon", "paint") == "Plascon"


class TestCementBrandHelpers:
    """Test cement_seed.py brand helpers (backward compatibility)"""

    def test_is_cement_brand_aksher_alias(self):
        """is_cement_brand("aksher") must be True"""
        assert is_cement_brand("aksher") is True

    def test_is_cement_brand_akshar_canonical(self):
        """is_cement_brand("akshar") must be True"""
        assert is_cement_brand("akshar") is True
        assert is_cement_brand("Akshar") is True
        assert is_cement_brand("AKSHAR") is True

    def test_is_cement_brand_other_brands(self):
        """is_cement_brand() recognizes other cement brands"""
        assert is_cement_brand("Dangote") is True
        assert is_cement_brand("dangote") is True
        assert is_cement_brand("Duracrete") is True
        assert is_cement_brand("Khoma") is True
        assert is_cement_brand("Njati") is True
        assert is_cement_brand("Njati Extra") is True
        assert is_cement_brand("njatiextra") is True  # alias

    def test_is_cement_brand_invalid(self):
        """is_cement_brand() returns False for unknown brands"""
        assert is_cement_brand("NotABrand") is False
        assert is_cement_brand("Random") is False
        assert is_cement_brand("") is False

    def test_normalize_cement_brand_name_aksher(self):
        """normalize_cement_brand_name("aksher") must return "Akshar" """
        assert normalize_cement_brand_name("aksher") == "Akshar"
        assert normalize_cement_brand_name("AKSHER") == "Akshar"
        assert normalize_cement_brand_name("akshar") == "Akshar"
        assert normalize_cement_brand_name("AKSHAR") == "Akshar"

    def test_normalize_cement_brand_name_other_brands(self):
        """normalize_cement_brand_name() normalizes other brands"""
        assert normalize_cement_brand_name("dangote") == "Dangote"
        assert normalize_cement_brand_name("DANGOTE") == "Dangote"
        assert normalize_cement_brand_name("duracrete") == "Duracrete"
        assert normalize_cement_brand_name("khoma") == "Khoma"

    def test_normalize_cement_brand_name_custom_passthrough(self):
        """normalize_cement_brand_name() passes through unknown brands"""
        assert normalize_cement_brand_name("CustomBrand") == "CustomBrand"


class TestAliasesIntegrity:
    """Test that all brand aliases are properly defined in SSOT"""

    def test_aksher_alias_exists_in_ssot(self):
        """CEMENT_BRANDS must include 'aksher' alias for Akshar"""
        from inventory.catalog.construction_materials import CEMENT_BRANDS

        akshar_brand = next((b for b in CEMENT_BRANDS if b["name"] == "Akshar"), None)
        assert akshar_brand is not None, "Akshar brand not found in SSOT"
        assert "aliases" in akshar_brand, "Akshar brand missing 'aliases' field"
        assert "aksher" in akshar_brand["aliases"], "'aksher' alias not found for Akshar"

    def test_all_brands_have_aliases_field(self):
        """All CEMENT_BRANDS must have 'aliases' field"""
        from inventory.catalog.construction_materials import CEMENT_BRANDS

        for brand in CEMENT_BRANDS:
            assert "aliases" in brand, f"Brand {brand['name']} missing 'aliases' field"
            assert isinstance(brand["aliases"], list), f"Brand {brand['name']} aliases must be a list"
            assert len(brand["aliases"]) > 0, f"Brand {brand['name']} has no aliases"

    def test_njati_extra_has_aliases(self):
        """Njati Extra must have proper aliases"""
        from inventory.catalog.construction_materials import CEMENT_BRANDS

        njati_extra = next((b for b in CEMENT_BRANDS if b["name"] == "Njati Extra"), None)
        assert njati_extra is not None, "Njati Extra not found in SSOT"
        assert "aliases" in njati_extra
        assert "njati extra" in njati_extra["aliases"]
        assert "njatiextra" in njati_extra["aliases"]

