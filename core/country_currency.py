# core/country_currency.py
"""
Canonical reference for African (and key global) countries, currencies, and flags.

This is the SINGLE SOURCE OF TRUTH for country/currency data across the platform.
Use this module in:
- Signup forms (country/currency dropdowns)
- Profile/Settings (country/currency editing)
- Workspace/Business display (flag, currency symbol)
- Marketplace (local pricing context)

Structure:
    AFRICAN_COUNTRIES = list of (iso2_code, name, currency_code, flag_emoji)
    COUNTRY_CURRENCY_MAP = {iso2_code: (currency_code, flag_emoji)}
    CURRENCY_NAMES = {currency_code: human_readable_name}
    get_country_choices() -> list of (code, label) for Django form choices
    get_currency_choices() -> list of (code, label) for Django form choices
    get_default_currency(country_code) -> currency code string
    get_flag(country_code) -> flag emoji string
"""
from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Master data: (iso2, name, default_currency, flag)
# ---------------------------------------------------------------------------
AFRICAN_COUNTRIES: list[tuple[str, str, str, str]] = [
    ("DZ", "Algeria",                  "DZD", "🇩🇿"),
    ("AO", "Angola",                   "AOA", "🇦🇴"),
    ("BJ", "Benin",                    "XOF", "🇧🇯"),
    ("BW", "Botswana",                 "BWP", "🇧🇼"),
    ("BF", "Burkina Faso",             "XOF", "🇧🇫"),
    ("BI", "Burundi",                  "BIF", "🇧🇮"),
    ("CV", "Cabo Verde",               "CVE", "🇨🇻"),
    ("CM", "Cameroon",                 "XAF", "🇨🇲"),
    ("CF", "Central African Republic", "XAF", "🇨🇫"),
    ("TD", "Chad",                     "XAF", "🇹🇩"),
    ("KM", "Comoros",                  "KMF", "🇰🇲"),
    ("CG", "Congo (Brazzaville)",      "XAF", "🇨🇬"),
    ("CD", "Congo (DRC)",              "CDF", "🇨🇩"),
    ("CI", "Côte d'Ivoire",            "XOF", "🇨🇮"),
    ("DJ", "Djibouti",                 "DJF", "🇩🇯"),
    ("EG", "Egypt",                    "EGP", "🇪🇬"),
    ("GQ", "Equatorial Guinea",        "XAF", "🇬🇶"),
    ("ER", "Eritrea",                  "ERN", "🇪🇷"),
    ("SZ", "Eswatini",                 "SZL", "🇸🇿"),
    ("ET", "Ethiopia",                 "ETB", "🇪🇹"),
    ("GA", "Gabon",                    "XAF", "🇬🇦"),
    ("GM", "Gambia",                   "GMD", "🇬🇲"),
    ("GH", "Ghana",                    "GHS", "🇬🇭"),
    ("GN", "Guinea",                   "GNF", "🇬🇳"),
    ("GW", "Guinea-Bissau",            "XOF", "🇬🇼"),
    ("KE", "Kenya",                    "KES", "🇰🇪"),
    ("LS", "Lesotho",                  "LSL", "🇱🇸"),
    ("LR", "Liberia",                  "LRD", "🇱🇷"),
    ("LY", "Libya",                    "LYD", "🇱🇾"),
    ("MG", "Madagascar",               "MGA", "🇲🇬"),
    ("MW", "Malawi",                   "MWK", "🇲🇼"),  # DEFAULT
    ("ML", "Mali",                     "XOF", "🇲🇱"),
    ("MR", "Mauritania",               "MRU", "🇲🇷"),
    ("MU", "Mauritius",                "MUR", "🇲🇺"),
    ("MA", "Morocco",                  "MAD", "🇲🇦"),
    ("MZ", "Mozambique",               "MZN", "🇲🇿"),
    ("NA", "Namibia",                  "NAD", "🇳🇦"),
    ("NE", "Niger",                    "XOF", "🇳🇪"),
    ("NG", "Nigeria",                  "NGN", "🇳🇬"),
    ("RW", "Rwanda",                   "RWF", "🇷🇼"),
    ("ST", "São Tomé and Príncipe",    "STN", "🇸🇹"),
    ("SN", "Senegal",                  "XOF", "🇸🇳"),
    ("SC", "Seychelles",               "SCR", "🇸🇨"),
    ("SL", "Sierra Leone",             "SLE", "🇸🇱"),
    ("SO", "Somalia",                  "SOS", "🇸🇴"),
    ("ZA", "South Africa",             "ZAR", "🇿🇦"),
    ("SS", "South Sudan",              "SSP", "🇸🇸"),
    ("SD", "Sudan",                    "SDG", "🇸🇩"),
    ("TZ", "Tanzania",                 "TZS", "🇹🇿"),
    ("TG", "Togo",                     "XOF", "🇹🇬"),
    ("TN", "Tunisia",                  "TND", "🇹🇳"),
    ("UG", "Uganda",                   "UGX", "🇺🇬"),
    ("ZM", "Zambia",                   "ZMW", "🇿🇲"),
    ("ZW", "Zimbabwe",                 "ZWL", "🇿🇼"),
]

# Additional global currencies that users may choose to override with
EXTRA_CURRENCIES: list[tuple[str, str]] = [
    ("USD", "US Dollar"),
    ("GBP", "British Pound"),
    ("EUR", "Euro"),
    ("AED", "UAE Dirham"),
    ("CNY", "Chinese Yuan"),
    ("INR", "Indian Rupee"),
    ("JPY", "Japanese Yen"),
]

# ---------------------------------------------------------------------------
# Derived lookup structures (built once at import time)
# ---------------------------------------------------------------------------

# {iso2: (currency_code, flag_emoji)}
COUNTRY_CURRENCY_MAP: dict[str, tuple[str, str]] = {
    iso2: (currency, flag)
    for iso2, _name, currency, flag in AFRICAN_COUNTRIES
}

# {iso2: name}
COUNTRY_NAME_MAP: dict[str, str] = {
    iso2: name for iso2, name, _c, _f in AFRICAN_COUNTRIES
}

# {currency_code: human_readable_name} – built from African data + extras
CURRENCY_NAMES: dict[str, str] = {}
_SEEN_CURRENCIES: set[str] = set()
for _iso2, _name, _cur, _flag in AFRICAN_COUNTRIES:
    if _cur not in _SEEN_CURRENCIES:
        # Use country name as basis for currency label where we can
        _SEEN_CURRENCIES.add(_cur)
        CURRENCY_NAMES[_cur] = _cur

# Override with nicer names
CURRENCY_NAMES.update({
    "MWK": "Malawian Kwacha",
    "ZMW": "Zambian Kwacha",
    "KES": "Kenyan Shilling",
    "TZS": "Tanzanian Shilling",
    "ZAR": "South African Rand",
    "NGN": "Nigerian Naira",
    "GHS": "Ghanaian Cedi",
    "UGX": "Ugandan Shilling",
    "ETB": "Ethiopian Birr",
    "RWF": "Rwandan Franc",
    "BWP": "Botswana Pula",
    "MZN": "Mozambican Metical",
    "EGP": "Egyptian Pound",
    "MAD": "Moroccan Dirham",
    "DZD": "Algerian Dinar",
    "TND": "Tunisian Dinar",
    "XOF": "West African CFA Franc",
    "XAF": "Central African CFA Franc",
    "USD": "US Dollar",
    "GBP": "British Pound",
    "EUR": "Euro",
})

# Default country/currency for new users/workspaces
DEFAULT_COUNTRY_CODE = "MW"
DEFAULT_COUNTRY_NAME = "Malawi"
DEFAULT_CURRENCY_CODE = "MWK"
DEFAULT_FLAG = "🇲🇼"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_country_choices() -> list[tuple[str, str]]:
    """
    Return a list of (code, label) for use in Django form ChoiceField.
    Sorted alphabetically by country name, with Malawi first.
    """
    sorted_countries = sorted(AFRICAN_COUNTRIES, key=lambda x: x[1])
    choices = [("", "Select country...")]
    # Malawi first
    choices += [("MW", "Malawi (default)")]
    choices += [
        (iso2, f"{flag} {name}")
        for iso2, name, _c, flag in sorted_countries
        if iso2 != "MW"
    ]
    return choices


def get_currency_choices() -> list[tuple[str, str]]:
    """
    Return a list of (code, label) for use in Django form ChoiceField.
    African currencies first, then global extras, MWK at top.
    """
    # Build from African countries (deduplicated)
    seen: set[str] = set()
    choices: list[tuple[str, str]] = [("", "Select currency...")]

    # MWK always first
    choices.append(("MWK", "MWK - Malawian Kwacha"))
    seen.add("MWK")

    # Rest of African currencies alphabetically
    for iso2, name, currency, flag in sorted(AFRICAN_COUNTRIES, key=lambda x: x[1]):
        if currency not in seen:
            label = CURRENCY_NAMES.get(currency, currency)
            choices.append((currency, f"{currency} - {label}"))
            seen.add(currency)

    # Global extras
    for code, name in EXTRA_CURRENCIES:
        if code not in seen:
            choices.append((code, f"{code} - {name}"))
            seen.add(code)

    return choices


def get_default_currency(country_code: Optional[str]) -> str:
    """
    Return the default currency code for a given country ISO-2 code.
    Falls back to MWK if unknown.
    """
    if not country_code:
        return DEFAULT_CURRENCY_CODE
    code = str(country_code).upper().strip()
    result = COUNTRY_CURRENCY_MAP.get(code)
    if result:
        return result[0]
    return DEFAULT_CURRENCY_CODE


def get_flag(country_code: Optional[str]) -> str:
    """
    Return the flag emoji for a given country ISO-2 code.
    Falls back to the Malawi flag.
    """
    if not country_code:
        return DEFAULT_FLAG
    code = str(country_code).upper().strip()
    result = COUNTRY_CURRENCY_MAP.get(code)
    if result:
        return result[1]
    return DEFAULT_FLAG


def get_country_name(country_code: Optional[str]) -> str:
    """Return country name for a given ISO-2 code."""
    if not country_code:
        return DEFAULT_COUNTRY_NAME
    return COUNTRY_NAME_MAP.get(str(country_code).upper().strip(), country_code)


def get_currency_symbol(currency_code: Optional[str]) -> str:
    """
    Return a short currency symbol/prefix for display purposes.
    Falls back to the currency code itself.
    """
    SYMBOLS: dict[str, str] = {
        "MWK": "MWK",
        "ZMW": "ZMW",
        "USD": "$",
        "GBP": "£",
        "EUR": "€",
        "KES": "KSh",
        "TZS": "TSh",
        "UGX": "USh",
        "ZAR": "R",
        "NGN": "₦",
        "GHS": "₵",
        "ETB": "Br",
        "RWF": "RF",
        "BWP": "P",
    }
    if not currency_code:
        return "MWK"
    return SYMBOLS.get(str(currency_code).upper().strip(), currency_code)


def country_currency_json() -> dict:
    """
    Return a JSON-serialisable dict mapping country code → default currency.
    Useful for frontend JS auto-fill.
    """
    return {iso2: cur for iso2, (cur, _flag) in COUNTRY_CURRENCY_MAP.items()}


__all__ = [
    "AFRICAN_COUNTRIES",
    "COUNTRY_CURRENCY_MAP",
    "COUNTRY_NAME_MAP",
    "CURRENCY_NAMES",
    "DEFAULT_COUNTRY_CODE",
    "DEFAULT_COUNTRY_NAME",
    "DEFAULT_CURRENCY_CODE",
    "DEFAULT_FLAG",
    "get_country_choices",
    "get_currency_choices",
    "get_default_currency",
    "get_flag",
    "get_country_name",
    "get_currency_symbol",
    "country_currency_json",
]
