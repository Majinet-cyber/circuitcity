# inventory/tests/test_template_filters.py
"""
Tests for custom template filters (cc_filters).
Ensures get_item and mul filters work correctly and never crash templates.
"""
from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase


class GetItemFilterTests(TestCase):
    """Test the get_item template filter."""

    def test_get_item_from_dict(self):
        """Test getting item from a dictionary."""
        template = Template("{% load cc_filters %}{{ data|get_item:'key' }}")
        context = Context({"data": {"key": "value"}})
        result = template.render(context)
        self.assertEqual(result, "value")

    def test_get_item_from_dict_missing_key(self):
        """Test getting missing key from dict returns empty string."""
        template = Template("{% load cc_filters %}{{ data|get_item:'missing' }}")
        context = Context({"data": {"key": "value"}})
        result = template.render(context)
        self.assertEqual(result, "")

    def test_get_item_from_object_attribute(self):
        """Test getting attribute from an object."""

        class MockObject:
            name = "Test Name"
            value = 42

        template = Template("{% load cc_filters %}{{ obj|get_item:'name' }}")
        context = Context({"obj": MockObject()})
        result = template.render(context)
        self.assertEqual(result, "Test Name")

    def test_get_item_from_none(self):
        """Test that None value returns empty string."""
        template = Template("{% load cc_filters %}{{ data|get_item:'key' }}")
        context = Context({"data": None})
        result = template.render(context)
        self.assertEqual(result, "")

    def test_get_item_with_numeric_value(self):
        """Test getting numeric values from dict."""
        template = Template("{% load cc_filters %}{{ data|get_item:'count' }}")
        context = Context({"data": {"count": 42}})
        result = template.render(context)
        self.assertEqual(result, "42")

    def test_get_item_gracefully_handles_errors(self):
        """Test that get_item never raises exceptions."""
        # Test with invalid key types
        template = Template("{% load cc_filters %}{{ data|get_item:invalid }}")
        context = Context({"data": {"key": "value"}, "invalid": None})
        result = template.render(context)
        self.assertEqual(result, "")


class MulFilterTests(TestCase):
    """Test the mul template filter."""

    def test_mul_two_integers(self):
        """Test multiplying two integers."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": 5, "b": 3})
        result = template.render(context)
        self.assertEqual(result, "15")

    def test_mul_two_strings(self):
        """Test multiplying two numeric strings."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": "2", "b": "3"})
        result = template.render(context)
        self.assertEqual(result, "6")

    def test_mul_with_decimal(self):
        """Test multiplying with Decimal values."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": Decimal("10.50"), "b": 2})
        result = template.render(context)
        self.assertEqual(result, "21.00")

    def test_mul_with_none_values(self):
        """Test that None values are treated as 0."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": None, "b": 5})
        result = template.render(context)
        self.assertEqual(result, "0")

    def test_mul_none_times_none(self):
        """Test multiplying None * None returns 0."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": None, "b": None})
        result = template.render(context)
        self.assertEqual(result, "0")

    def test_mul_with_float(self):
        """Test multiplying with float values."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": 2.5, "b": 4})
        result = template.render(context)
        self.assertEqual(result, "10.0")

    def test_mul_invalid_string_returns_zero(self):
        """Test that invalid strings return 0 instead of crashing."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": "invalid", "b": 5})
        result = template.render(context)
        self.assertEqual(result, "0")

    def test_mul_large_numbers(self):
        """Test multiplying large numbers."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": 1000000, "b": 50})
        result = template.render(context)
        self.assertEqual(result, "50000000")

    def test_mul_zero(self):
        """Test multiplying by zero."""
        template = Template("{% load cc_filters %}{{ a|mul:b }}")
        context = Context({"a": 100, "b": 0})
        result = template.render(context)
        self.assertEqual(result, "0")


class TemplateRenderingIntegrationTests(TestCase):
    """
    Integration tests for templates using cc_filters.
    These ensure the actual cement templates don't crash.
    """

    def test_stock_list_value_calculation(self):
        """Test that stock value calculation works (quantity * cost_price)."""
        template = Template(
            "{% load cc_filters %}" "{% load humanize %}" "MK {{ quantity|mul:cost_price|floatformat:2|intcomma }}"
        )
        context = Context({"quantity": 10, "cost_price": Decimal("5500.50")})
        result = template.render(context)
        self.assertIn("55,005.00", result)

    def test_category_map_lookup(self):
        """Test category map lookup with get_item (as used in products_catalog.html)."""
        template = Template("{% load cc_filters %}{{ category_map|get_item:slug }}")
        context = Context(
            {
                "category_map": {
                    "construction": "Construction Materials",
                    "paint": "Paint & Coatings",
                },
                "slug": "construction",
            }
        )
        result = template.render(context)
        self.assertEqual(result, "Construction Materials")

    def test_category_map_lookup_missing_key(self):
        """Test category map lookup with missing key returns empty string."""
        template = Template("{% load cc_filters %}{{ category_map|get_item:slug }}")
        context = Context(
            {
                "category_map": {"construction": "Construction Materials"},
                "slug": "nonexistent",
            }
        )
        result = template.render(context)
        self.assertEqual(result, "")

    def test_complex_template_with_both_filters(self):
        """Test a complex template using both filters."""
        template = Template(
            "{% load cc_filters %}" "Product: {{ names|get_item:'product' }}, " "Total: {{ qty|mul:price }}"
        )
        context = Context(
            {
                "names": {"product": "Cement Bag", "brand": "Dangote"},
                "qty": 5,
                "price": Decimal("12000.00"),
            }
        )
        result = template.render(context)
        self.assertIn("Product: Cement Bag", result)
        self.assertIn("Total: 60000.00", result)
