# tests/test_abs_filter.py
"""
Tests for the abs template filter.
Ensures that the TemplateSyntaxError is fixed.
"""
import pytest
from django.test import TestCase
from django.template import Template, Context
from decimal import Decimal


@pytest.mark.django_db
class TestAbsTemplateFilter(TestCase):
    """Test the abs template filter."""
    
    def test_abs_filter_works_with_negative_number(self):
        """Test that abs filter converts negative to positive."""
        template = Template("{% load wallet_extras %}{{ value|abs }}")
        context = Context({"value": -100})
        result = template.render(context)
        self.assertEqual(result.strip(), "100")
    
    def test_abs_filter_works_with_decimal(self):
        """Test that abs filter works with Decimal type."""
        template = Template("{% load wallet_extras %}{{ value|abs }}")
        context = Context({"value": Decimal("-25000.50")})
        result = template.render(context)
        self.assertEqual(result.strip(), "25000.50")
    
    def test_abs_filter_works_with_positive_number(self):
        """Test that abs filter preserves positive numbers."""
        template = Template("{% load wallet_extras %}{{ value|abs }}")
        context = Context({"value": 50})
        result = template.render(context)
        self.assertEqual(result.strip(), "50")
    
    def test_abs_filter_with_zero(self):
        """Test that abs filter handles zero correctly."""
        template = Template("{% load wallet_extras %}{{ value|abs }}")
        context = Context({"value": 0})
        result = template.render(context)
        self.assertEqual(result.strip(), "0")
    
    def test_abs_filter_with_invalid_value(self):
        """Test that abs filter handles invalid values gracefully."""
        template = Template("{% load wallet_extras %}{{ value|abs }}")
        context = Context({"value": "not a number"})
        result = template.render(context)
        # Should return the original value on error
        self.assertEqual(result.strip(), "not a number")
    
    def test_abs_filter_combined_with_other_filters(self):
        """Test that abs filter can be chained with other filters."""
        template = Template("{% load wallet_extras humanize %}{{ value|abs|floatformat:0|intcomma }}")
        context = Context({"value": Decimal("-25000.75")})
        result = template.render(context)
        # abs(-25000.75) = 25000.75, floatformat:0 = 25001, intcomma = 25,001
        self.assertIn("25,001", result)

