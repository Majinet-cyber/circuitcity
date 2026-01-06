# inventory/tests/test_clothing_size_validation.py
"""
Tests for clothing size validation rules.

CRITICAL: Shoes (footwear) must ONLY accept numeric sizes (30-50).
Other categories may accept alpha sizes (XS, S, M, L, XL, XXL, etc).
"""
import pytest
from django.core.exceptions import ValidationError

from inventory.clothing_size_validation import (
    get_allowed_sizes_for_category,
    is_footwear_category,
    validate_clothing_size,
    validate_shoe_size,
    validate_size_for_django_form,
)


class TestShoesSizeValidation:
    """Test that shoes ONLY accept numeric sizes 30-50"""

    def test_shoes_numeric_size_valid(self):
        """Shoes with numeric size 30-50 should be valid"""
        for size in ["30", "35", "40", "42", "45", "50"]:
            is_valid, error = validate_clothing_size(size, "shoes", "")
            assert is_valid, f"Size {size} should be valid for shoes, got error: {error}"

    def test_shoes_alpha_size_invalid(self):
        """Shoes with alpha sizes (XL, XXL, S, M, L) should be INVALID"""
        invalid_sizes = ["XL", "XXL", "S", "M", "L", "XS", "XXXL"]
        for size in invalid_sizes:
            is_valid, error = validate_clothing_size(size, "shoes", "")
            assert not is_valid, f"Size {size} should be INVALID for shoes"
            assert "numeric only" in error.lower(), f"Error should mention 'numeric only', got: {error}"

    def test_shoes_out_of_range_invalid(self):
        """Shoes with numeric size outside 30-50 range should be invalid"""
        for size in ["20", "25", "55", "60"]:
            is_valid, error = validate_clothing_size(size, "shoes", "")
            assert not is_valid, f"Size {size} should be invalid (out of range)"
            assert "30" in error and "50" in error, f"Error should mention range, got: {error}"

    def test_shoes_subcategories(self):
        """All shoe subcategories (sneaker, boot, etc) should follow numeric rule"""
        subcategories = ["sneaker", "boot", "sports-shoe", "office-shoe"]
        for subcat in subcategories:
            # Numeric should be valid
            is_valid, _ = validate_clothing_size("42", "shoes", subcat)
            assert is_valid, f"Numeric size should be valid for {subcat}"

            # Alpha should be invalid
            is_valid, error = validate_clothing_size("XL", "shoes", subcat)
            assert not is_valid, f"Alpha size should be invalid for {subcat}"

    def test_shoe_size_validation_direct(self):
        """Test validate_shoe_size directly"""
        # Valid
        is_valid, _ = validate_shoe_size("40")
        assert is_valid

        # Invalid alpha
        is_valid, error = validate_shoe_size("XL")
        assert not is_valid
        assert "numeric only" in error.lower()

        # Out of range
        is_valid, error = validate_shoe_size("100")
        assert not is_valid
        assert "30" in error and "50" in error


class TestOtherClothingSizeValidation:
    """Test that non-shoe categories allow alpha or numeric sizes"""

    def test_shirt_alpha_sizes_valid(self):
        """Shirts should accept alpha sizes (XS, S, M, L, XL, XXL)"""
        for size in ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]:
            is_valid, error = validate_clothing_size(size, "shirt", "")
            assert is_valid, f"Size {size} should be valid for shirt, got error: {error}"

    def test_shirt_numeric_sizes_valid(self):
        """Shirts should also accept numeric sizes"""
        for size in ["38", "40", "42", "44"]:
            is_valid, error = validate_clothing_size(size, "shirt", "")
            assert is_valid, f"Size {size} should be valid for shirt"

    def test_jeans_numeric_sizes_valid(self):
        """Jeans should accept numeric sizes (waist)"""
        for size in ["28", "30", "32", "34", "36", "40"]:
            is_valid, error = validate_clothing_size(size, "jeans", "")
            assert is_valid, f"Size {size} should be valid for jeans"

    def test_jeans_waist_inseam_valid(self):
        """Jeans should accept waist x inseam format (32x30)"""
        for size in ["32x30", "34x32", "36x34"]:
            is_valid, error = validate_clothing_size(size, "jeans", "")
            assert is_valid, f"Size {size} should be valid for jeans"

    def test_dress_alpha_sizes_valid(self):
        """Dresses should accept alpha sizes"""
        for size in ["XS", "S", "M", "L", "XL"]:
            is_valid, error = validate_clothing_size(size, "dress", "")
            assert is_valid, f"Size {size} should be valid for dress"


class TestFootwearCategoryDetection:
    """Test is_footwear_category detection"""

    def test_shoes_detected_as_footwear(self):
        """Categories with 'shoe' keyword should be detected"""
        assert is_footwear_category("shoes", "")
        assert is_footwear_category("sneaker", "")
        assert is_footwear_category("boot", "")
        assert is_footwear_category("sports-shoe", "")
        assert is_footwear_category("office-shoe", "")

    def test_non_footwear_not_detected(self):
        """Non-footwear categories should not be detected"""
        assert not is_footwear_category("shirt", "")
        assert not is_footwear_category("jeans", "")
        assert not is_footwear_category("dress", "")
        assert not is_footwear_category("jacket", "")


class TestGetAllowedSizes:
    """Test get_allowed_sizes_for_category"""

    def test_shoes_returns_numeric_only(self):
        """Shoes should return only numeric sizes 30-50"""
        sizes = get_allowed_sizes_for_category("shoes", "")
        assert all(s.isdigit() for s in sizes), "Shoes should only return numeric sizes"
        assert "30" in sizes
        assert "50" in sizes
        assert "XL" not in sizes
        assert "XXL" not in sizes

    def test_shirt_returns_alpha_sizes(self):
        """Shirts should return alpha sizes"""
        sizes = get_allowed_sizes_for_category("shirt", "")
        assert "S" in sizes or "M" in sizes or "L" in sizes, "Shirts should include alpha sizes"


class TestDjangoFormValidator:
    """Test validate_size_for_django_form (raises ValidationError)"""

    def test_valid_size_returns_cleaned(self):
        """Valid size should return cleaned (uppercase) size"""
        result = validate_size_for_django_form("m", "shirt", "")
        assert result == "M", "Should return uppercase"

    def test_invalid_size_raises_validation_error(self):
        """Invalid size should raise ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            validate_size_for_django_form("XL", "shoes", "")
        assert "numeric only" in str(exc_info.value).lower()

    def test_shoes_numeric_valid_django(self):
        """Shoes with numeric size should be valid"""
        result = validate_size_for_django_form("42", "shoes", "")
        assert result == "42"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_size_invalid(self):
        """Empty size should be invalid"""
        is_valid, error = validate_clothing_size("", "shirt", "")
        assert not is_valid
        assert "required" in error.lower()

    def test_whitespace_trimmed(self):
        """Whitespace should be trimmed"""
        is_valid, _ = validate_clothing_size("  42  ", "shoes", "")
        assert is_valid

    def test_case_insensitive_alpha_sizes(self):
        """Alpha sizes should be case-insensitive"""
        is_valid, _ = validate_clothing_size("xl", "shirt", "")
        assert is_valid

        is_valid, _ = validate_clothing_size("XL", "shirt", "")
        assert is_valid

    def test_shoes_boundary_sizes(self):
        """Test exact boundaries for shoes"""
        # 30 should be valid (minimum)
        is_valid, _ = validate_shoe_size("30")
        assert is_valid

        # 50 should be valid (maximum)
        is_valid, _ = validate_shoe_size("50")
        assert is_valid

        # 29 should be invalid (below minimum)
        is_valid, _ = validate_shoe_size("29")
        assert not is_valid

        # 51 should be invalid (above maximum)
        is_valid, _ = validate_shoe_size("51")
        assert not is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
