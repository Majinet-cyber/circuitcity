# core/tests/test_template_filters.py
"""
Unit tests for custom template filters in cc_extras.

These tests verify that get_item and mul filters handle edge cases
safely without raising exceptions.
"""
from decimal import Decimal

import pytest

from core.templatetags.cc_extras import get_item, mul


class TestGetItemFilter:
    """Tests for the get_item template filter."""

    def test_get_item_returns_value_for_existing_key(self):
        """Test get_item returns value when key exists."""
        obj = {"category": "cement", "price": 100}
        assert get_item(obj, "category") == "cement"
        assert get_item(obj, "price") == 100

    def test_get_item_returns_empty_string_for_missing_key(self):
        """Test get_item returns empty string when key doesn't exist."""
        obj = {"category": "cement"}
        assert get_item(obj, "missing_key") == ""

    def test_get_item_handles_none_object(self):
        """Test get_item returns empty string for None object."""
        assert get_item(None, "any_key") == ""

    def test_get_item_with_dict_like_object(self):
        """Test get_item works with objects that have .get() method."""

        class DictLike:
            def get(self, key, default=None):
                return {"foo": "bar"}.get(key, default)

        obj = DictLike()
        assert get_item(obj, "foo") == "bar"
        assert get_item(obj, "missing") == ""

    def test_get_item_with_list_index(self):
        """Test get_item works with list indices."""
        obj = ["first", "second", "third"]
        assert get_item(obj, 0) == "first"
        assert get_item(obj, 2) == "third"

    def test_get_item_handles_invalid_index(self):
        """Test get_item returns empty string for invalid list index."""
        obj = ["first", "second"]
        assert get_item(obj, 10) == ""
        assert get_item(obj, -10) == ""

    def test_get_item_handles_non_subscriptable(self):
        """Test get_item returns empty string for non-subscriptable objects."""
        obj = 42
        assert get_item(obj, "key") == ""


class TestMulFilter:
    """Tests for the mul template filter."""

    def test_mul_multiplies_integers(self):
        """Test mul multiplies two integers correctly."""
        assert mul(2, 3) == 6
        assert mul(5, 10) == 50
        assert mul(0, 100) == 0

    def test_mul_multiplies_floats(self):
        """Test mul multiplies floats correctly."""
        result = mul(2.5, 4)
        assert float(result) == 10.0

    def test_mul_multiplies_decimals(self):
        """Test mul handles Decimal objects."""
        result = mul(Decimal("10.50"), Decimal("2"))
        assert result == Decimal("21.00")

    def test_mul_handles_none_values(self):
        """Test mul returns 0 when either value is None."""
        assert mul(None, 3) == 0
        assert mul(5, None) == 0
        assert mul(None, None) == 0

    def test_mul_converts_strings_to_numbers(self):
        """Test mul converts string representations of numbers."""
        result = mul("2", "3")
        assert float(result) == 6.0

        result = mul("10.5", "2")
        assert float(result) == 21.0

    def test_mul_handles_invalid_strings(self):
        """Test mul returns 0 for non-numeric strings."""
        assert mul("abc", 5) == 0
        assert mul(10, "xyz") == 0

    def test_mul_realistic_cement_scenario(self):
        """Test mul with realistic cement stock calculation."""
        # Simulate: 50 bags * 15000 MK per bag
        quantity = 50
        cost_price = Decimal("15000.00")
        total = mul(quantity, cost_price)
        assert total == Decimal("750000.00")

    def test_mul_handles_zero(self):
        """Test mul handles zero correctly."""
        assert mul(0, 100) == 0
        assert mul(100, 0) == 0

    def test_mul_handles_negative_numbers(self):
        """Test mul handles negative numbers."""
        assert mul(-5, 3) == -15
        assert mul(5, -3) == -15
        assert mul(-5, -3) == 15

