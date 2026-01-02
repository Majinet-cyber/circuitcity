# inventory/tests/test_barcode_utils.py
"""
Tests for barcode utility functions.
"""
import pytest
from inventory.utils_barcodes import (
    get_barcode,
    set_barcode,
    product_has_barcode,
    validate_barcode,
    normalize_barcode,
)


class MockProduct:
    """Mock product for testing."""

    def __init__(self, barcode=None):
        self.barcode = barcode


class MockItem:
    """Mock inventory item for testing."""

    def __init__(self, barcode=None, product=None):
        self.barcode = barcode
        self.product = product


class TestBarcodeUtils:
    """Test suite for barcode utilities."""

    def test_get_barcode_from_product(self):
        """Should get barcode from product."""
        product = MockProduct(barcode="ABC123")
        assert get_barcode(product) == "ABC123"

    def test_get_barcode_from_item(self):
        """Should get barcode from item."""
        item = MockItem(barcode="ITEM456")
        assert get_barcode(item) == "ITEM456"

    def test_get_barcode_from_item_product(self):
        """Should fall back to product barcode if item has none."""
        product = MockProduct(barcode="PROD789")
        item = MockItem(barcode=None, product=product)
        assert get_barcode(item) == "PROD789"

    def test_get_barcode_none(self):
        """Should return None for object without barcode."""
        product = MockProduct(barcode=None)
        assert get_barcode(product) is None

    def test_get_barcode_empty_string(self):
        """Should return None for empty barcode."""
        product = MockProduct(barcode="  ")
        assert get_barcode(product) is None

    def test_set_barcode_success(self):
        """Should set barcode on product."""
        product = MockProduct()
        assert set_barcode(product, "NEW123") is True
        assert product.barcode == "NEW123"

    def test_set_barcode_strips_whitespace(self):
        """Should strip whitespace when setting barcode."""
        product = MockProduct()
        set_barcode(product, "  TRIM456  ")
        assert product.barcode == "TRIM456"

    def test_product_has_barcode_true(self):
        """Should return True for product with barcode."""
        product = MockProduct(barcode="EXISTS")
        assert product_has_barcode(product) is True

    def test_product_has_barcode_false(self):
        """Should return False for product without barcode."""
        product = MockProduct(barcode=None)
        assert product_has_barcode(product) is False

    def test_validate_barcode_valid(self):
        """Should validate correct barcodes."""
        valid, msg = validate_barcode("ABC123")
        assert valid is True
        assert msg == ""

    def test_validate_barcode_empty(self):
        """Should reject empty barcode."""
        valid, msg = validate_barcode("")
        assert valid is False
        assert "empty" in msg.lower()

    def test_validate_barcode_too_short(self):
        """Should reject barcode that's too short."""
        valid, msg = validate_barcode("AB")
        assert valid is False
        assert "3 characters" in msg

    def test_validate_barcode_too_long(self):
        """Should reject barcode that's too long."""
        valid, msg = validate_barcode("A" * 101)
        assert valid is False
        assert "too long" in msg.lower()

    def test_validate_barcode_invalid_chars(self):
        """Should reject barcode with invalid characters."""
        valid, msg = validate_barcode("ABC@123")
        assert valid is False
        assert "letters, numbers" in msg.lower()

    def test_normalize_barcode(self):
        """Should normalize barcode to uppercase and strip."""
        assert normalize_barcode("  abc123  ") == "ABC123"
        assert normalize_barcode("xyz-789") == "XYZ-789"

    def test_normalize_barcode_empty(self):
        """Should return empty string for None/empty input."""
        assert normalize_barcode(None) == ""
        assert normalize_barcode("") == ""
