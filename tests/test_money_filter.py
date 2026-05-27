"""
Tests for the money template filter.

CRITICAL: These tests ensure the money filter handles comma-separated strings correctly,
which was the root cause of the gym dashboard showing "MWK 0" for all amounts.
"""
from decimal import Decimal

import pytest
from django.template import Context, Template


class TestMoneyFilter:
    """Test suite for the money template filter."""

    def test_money_filter_with_decimal(self):
        """money filter should format Decimal correctly with commas and 2dp"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_decimal_fractional(self):
        """money filter should preserve fractional amounts"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": Decimal("55000.50")})
        result = template.render(context)
        assert result == "MWK 55,000.50"

    def test_money_filter_with_integer(self):
        """money filter should handle integer values"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": 870000})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_float(self):
        """money filter should handle float values"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": 870000.00})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_string_number(self):
        """money filter should handle string numbers"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": "870000"})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_comma_separated_string(self):
        """
        CRITICAL REGRESSION TEST:
        money filter MUST handle comma-separated strings correctly.
        This is what broke the gym dashboard (intcomma output was piped to money).
        """
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": "870,000.00"})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_comma_separated_string_no_decimals(self):
        """money filter should handle comma-separated strings without decimals"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": "870,000"})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_currency_prefix(self):
        """money filter should strip currency prefix from strings"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": "MWK 870,000.00"})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_filter_with_none(self):
        """money filter should return '0.00' for None"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": None})
        result = template.render(context)
        assert result == "MWK 0.00"

    def test_money_filter_with_zero(self):
        """money filter should format zero correctly"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": 0})
        result = template.render(context)
        assert result == "MWK 0.00"

    def test_money_filter_with_zero_decimal(self):
        """money filter should format Decimal zero correctly"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": Decimal("0.00")})
        result = template.render(context)
        assert result == "MWK 0.00"

    def test_money_filter_with_custom_currency(self):
        """money filter should support custom currency"""
        template = Template('{% load money %}{{ amount|money:"USD" }}')
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        assert result == "USD 870,000.00"

    def test_money_filter_with_negative_amount(self):
        """money filter should handle negative amounts"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": Decimal("-5000.50")})
        result = template.render(context)
        assert result == "MWK -5,000.50"

    def test_money_filter_with_very_large_amount(self):
        """money filter should handle very large amounts"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": Decimal("1234567890.12")})
        result = template.render(context)
        assert result == "MWK 1,234,567,890.12"

    def test_money_filter_with_invalid_string(self):
        """money filter should return '0.00' for invalid strings and log warning"""
        template = Template("{% load money %}{{ amount|money }}")
        context = Context({"amount": "invalid"})
        result = template.render(context)
        assert result == "MWK 0.00"

    def test_money_filter_does_not_chain_with_intcomma(self):
        """
        ANTI-PATTERN TEST:
        Verify that chaining intcomma|money still works (but is redundant).
        This test documents the old broken pattern and ensures backward compatibility.
        """
        template = Template("{% load money humanize %}{{ amount|intcomma|money }}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        # intcomma produces "870,000", money should handle it
        assert result == "MWK 870,000.00"

    def test_money_filter_does_not_chain_with_floatformat(self):
        """
        ANTI-PATTERN TEST:
        Verify that chaining floatformat|money still works (but is redundant).
        """
        template = Template("{% load money %}{{ amount|floatformat:2|money }}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        # floatformat produces "870000.00", money should handle it
        assert result == "MWK 870,000.00"

    def test_money_filter_does_not_chain_with_floatformat_and_intcomma(self):
        """
        CRITICAL ANTI-PATTERN TEST:
        This is the EXACT broken pattern from gym dashboard template.
        floatformat:2|intcomma|money => "870,000.00" => money should parse it correctly.
        """
        template = Template("{% load money humanize %}{{ amount|floatformat:2|intcomma|money }}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        # floatformat produces "870000.00", intcomma produces "870,000.00", money should handle it
        assert result == "MWK 870,000.00"


class TestFormatMwkFilter:
    """Test the format_mwk filter alias."""

    def test_format_mwk_filter(self):
        """format_mwk should work identically to money with MWK currency"""
        template = Template("{% load money %}{{ amount|format_mwk }}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_format_mwk_with_comma_separated_string(self):
        """format_mwk should handle comma-separated strings"""
        template = Template("{% load money %}{{ amount|format_mwk }}")
        context = Context({"amount": "870,000.00"})
        result = template.render(context)
        assert result == "MWK 870,000.00"


class TestMoneyTag:
    """Test the money simple tag."""

    def test_money_tag_basic(self):
        """money tag should work like money filter"""
        template = Template("{% load money %}{% money amount %}")
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        assert result == "MWK 870,000.00"

    def test_money_tag_with_custom_currency(self):
        """money tag should support custom currency"""
        template = Template('{% load money %}{% money amount "USD" %}')
        context = Context({"amount": Decimal("870000")})
        result = template.render(context)
        assert result == "USD 870,000.00"

