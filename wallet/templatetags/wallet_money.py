from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()

@register.filter(name="wallet_money")
def wallet_money(value, currency="MWK"):
    """
    Usage:
      {{ amount|wallet_money }} -> "MWK 12,345"
      {{ amount|wallet_money:"USD" }} -> "USD 12,345"
    """
    if value is None or value == "":
        return f"{currency} 0"

    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    # Render ints without decimals, others with 2dp
    if n == n.to_integral():
        formatted = f"{int(n):,}"
    else:
        formatted = f"{n:,.2f}"

    return f"{currency} {formatted}"


@register.filter(name="wallet_format_mwk")
def wallet_format_mwk(value):
    # legacy compatibility: {{ x|wallet_format_mwk }} -> "MWK 12,345"
    return wallet_money(value, "MWK")

