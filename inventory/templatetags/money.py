from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


def _to_decimal(v) -> Decimal | None:
    """
    Convert value to Decimal, handling various input formats.
    
    Supports:
    - Decimal/int/float directly
    - String numbers with commas: "870,000.00"
    - String with currency prefix: "MWK 870,000.00"
    - None returns None
    
    Returns None if conversion fails.
    """
    if v is None:
        return None
    
    # If already a Decimal, return as-is
    if isinstance(v, Decimal):
        return v
    
    # Convert to string for processing
    s = str(v).strip()
    
    # Remove common currency prefixes
    for currency in ["MWK", "MK", "USD", "$", "€", "£"]:
        s = s.replace(currency, "").strip()
    
    # Remove thousands separators (commas)
    s = s.replace(",", "")
    
    # Try to convert to Decimal
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        # Log warning but don't crash
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"money filter: Could not convert value to Decimal: {repr(v)}")
        return None


def _fmt_amount(d: Decimal) -> str:
    """
    Format Decimal as currency amount with thousands separators and 2 decimal places.
    
    Examples:
    - Decimal("870000") => "870,000.00"
    - Decimal("55000.50") => "55,000.50"
    - Decimal("0") => "0.00"
    """
    # Quantize to 2 decimal places
    q = d.quantize(Decimal("0.01"))
    
    # Format with thousands separator and 2 decimal places
    # Using Python's :,.2f format
    formatted = f"{q:,.2f}"
    
    return formatted


@register.filter(name="money")
def money_filter(value, currency: str = "MWK") -> str:
    """
    Format value as currency with thousands separators and 2 decimal places.
    
    Usage:
        {{ amount|money }} => "MWK 870,000.00"
        {{ amount|money:"USD" }} => "USD 870,000.00"
    
    Handles:
    - Decimal/int/float values
    - String values with commas: "870,000.00"
    - String values with currency: "MWK 870,000.00"
    - None => "MWK 0.00"
    """
    d = _to_decimal(value)
    if d is None:
        return f"{currency} 0.00"
    return f"{currency} {_fmt_amount(d)}"


@register.simple_tag(name="money")
def money_tag(value, currency: str = "MWK") -> str:
    # Backwards compatibility for `{% money x %}`
    return money_filter(value, currency)


@register.filter(name="format_mwk")
def format_mwk(value):
    """
    Format amount as MWK currency.
    Usage: {{ amount|format_mwk }} -> "MWK 12,345"
    Safely handles None, 0, and invalid values.
    """
    return money_filter(value, "MWK")


@register.filter(name="wallet_money")
def wallet_money(value, currency="MWK"):
    """
    Alias for money filter for backwards compatibility with wallet templates.
    
    Usage:
        {{ amount|wallet_money }} -> "MWK 870,000.00"
        {{ amount|wallet_money:"USD" }} -> "USD 870,000.00"
    
    This is an alias for the money filter to maintain compatibility with
    templates that were using the wallet_money filter from wallet.templatetags.wallet_money.
    """
    return money_filter(value, currency)