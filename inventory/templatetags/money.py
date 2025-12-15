from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


def _to_decimal(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _fmt_amount(d: Decimal) -> str:
    # 2dp but drop .00 for clean display
    q = d.quantize(Decimal("0.01"))
    s = f"{q:,.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    return s


@register.filter(name="money")
def money_filter(value, currency: str = "MWK") -> str:
    d = _to_decimal(value)
    if d is None:
        return f"{currency} 0"
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
