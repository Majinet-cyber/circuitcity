# tests/test_country_currency.py
"""
Tests for core/country_currency.py — country, currency, and flag data.
"""
import pytest
from django.test import TestCase

from core.country_currency import (
    AFRICAN_COUNTRIES,
    COUNTRY_CURRENCY_MAP,
    CURRENCY_NAMES,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_CURRENCY_CODE,
    get_country_choices,
    get_currency_choices,
    get_default_currency,
    get_flag,
)


@pytest.mark.django_db
class CountryCurrencyDataTests(TestCase):
    """Tests for the core data structures."""

    def test_african_countries_list_not_empty(self):
        self.assertGreater(len(AFRICAN_COUNTRIES), 50, "Should have all 54 African countries")

    def test_each_country_has_four_fields(self):
        for entry in AFRICAN_COUNTRIES:
            self.assertEqual(len(entry), 4, f"Expected 4-tuple, got: {entry}")

    def test_malawi_is_in_countries(self):
        codes = [c[0] for c in AFRICAN_COUNTRIES]
        self.assertIn("MW", codes)

    def test_default_country_is_malawi(self):
        self.assertEqual(DEFAULT_COUNTRY_CODE, "MW")

    def test_default_currency_is_mwk(self):
        self.assertEqual(DEFAULT_CURRENCY_CODE, "MWK")

    def test_country_currency_map_populated(self):
        self.assertGreater(len(COUNTRY_CURRENCY_MAP), 0)
        self.assertIn("MW", COUNTRY_CURRENCY_MAP)

    def test_malawi_currency_is_mwk(self):
        currency_code, _flag = COUNTRY_CURRENCY_MAP["MW"]
        self.assertEqual(currency_code, "MWK")

    def test_malawi_flag_is_correct(self):
        _currency, flag = COUNTRY_CURRENCY_MAP["MW"]
        self.assertEqual(flag, "🇲🇼")

    def test_all_iso2_codes_are_two_chars(self):
        for iso2, *_ in AFRICAN_COUNTRIES:
            self.assertEqual(len(iso2), 2, f"ISO-2 code should be 2 chars: {iso2}")
            self.assertTrue(iso2.isupper(), f"ISO-2 code should be uppercase: {iso2}")

    def test_currency_names_populated(self):
        self.assertGreater(len(CURRENCY_NAMES), 0)
        self.assertIn("MWK", CURRENCY_NAMES)

    def test_mwk_name(self):
        self.assertIn("Malawi", CURRENCY_NAMES.get("MWK", ""))


@pytest.mark.django_db
class CountryCurrencyHelperTests(TestCase):
    """Tests for helper functions."""

    def test_get_country_choices_returns_list(self):
        choices = get_country_choices()
        self.assertIsInstance(choices, list)
        self.assertGreater(len(choices), 0)

    def test_get_country_choices_has_tuples(self):
        choices = get_country_choices()
        for code, label in choices:
            self.assertIsInstance(code, str)
            self.assertIsInstance(label, str)
            self.assertGreater(len(code), 0)

    def test_get_currency_choices_returns_list(self):
        choices = get_currency_choices()
        self.assertIsInstance(choices, list)
        self.assertGreater(len(choices), 0)

    def test_get_default_currency_malawi(self):
        currency = get_default_currency("MW")
        self.assertEqual(currency, "MWK")

    def test_get_default_currency_kenya(self):
        currency = get_default_currency("KE")
        self.assertEqual(currency, "KES")

    def test_get_default_currency_unknown_returns_default(self):
        currency = get_default_currency("XX")
        self.assertEqual(currency, DEFAULT_CURRENCY_CODE)

    def test_get_flag_malawi(self):
        flag = get_flag("MW")
        self.assertEqual(flag, "🇲🇼")

    def test_get_flag_unknown_returns_empty_or_globe(self):
        flag = get_flag("XX")
        self.assertIsInstance(flag, str)

    def test_get_country_choices_includes_malawi(self):
        choices = get_country_choices()
        codes = [c[0] for c in choices]
        self.assertIn("MW", codes)

    def test_get_currency_choices_includes_mwk(self):
        choices = get_currency_choices()
        codes = [c[0] for c in choices]
        self.assertIn("MWK", codes)

    def test_get_currency_choices_includes_usd(self):
        choices = get_currency_choices()
        codes = [c[0] for c in choices]
        self.assertIn("USD", codes)
