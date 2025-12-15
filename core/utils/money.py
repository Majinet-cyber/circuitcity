# core/utils/money.py
"""
Currency conversion and formatting utilities.
Single source of truth for money display across the app.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def get_mwk_per_usd() -> Optional[Decimal]:
    """
    Get the current MWK per USD exchange rate.
    
    Returns:
        Decimal rate (e.g., 1750.00) or None if not set
    """
    try:
        from core.models import ExchangeRate
        return ExchangeRate.get_rate_value()
    except Exception:
        return None


def mwk_to_usd(mwk_amount: Decimal, mwk_per_usd: Optional[Decimal]) -> Optional[Decimal]:
    """
    Convert MWK amount to USD.
    
    Args:
        mwk_amount: Amount in MWK (base currency)
        mwk_per_usd: Exchange rate (1 USD = mwk_per_usd MWK)
        
    Returns:
        USD amount as Decimal, or None if rate is invalid
    """
    if mwk_per_usd is None or mwk_per_usd <= 0:
        return None
    
    if mwk_amount is None or mwk_amount == 0:
        return Decimal("0")
    
    # Convert: USD = MWK / mwk_per_usd
    usd = mwk_amount / mwk_per_usd
    # Round to 2 decimal places
    return usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_decimal(amount) -> Decimal:
    """
    Safely convert various types to Decimal.
    
    Args:
        amount: int, float, Decimal, str, or None
        
    Returns:
        Decimal value, or Decimal(0) if conversion fails
    """
    if amount is None:
        return Decimal("0")
    
    if isinstance(amount, Decimal):
        return amount
    
    if isinstance(amount, str):
        # Remove commas and whitespace
        cleaned = amount.replace(",", "").replace(" ", "").strip()
        try:
            return Decimal(cleaned)
        except (ValueError, TypeError):
            return Decimal("0")
    
    try:
        return Decimal(str(amount))
    except (ValueError, TypeError):
        return Decimal("0")


def convert_mwk_to_usd(mwk_amount: Decimal, rate: Optional[Decimal]) -> Optional[Decimal]:
    """
    Convert MWK amount to USD for display.
    Alias for mwk_to_usd for backward compatibility.
    
    Args:
        mwk_amount: Amount in MWK (base currency)
        rate: Exchange rate (1 USD = rate MWK). If None, returns None.
        
    Returns:
        USD amount as Decimal, or None if rate is not available
    """
    return mwk_to_usd(mwk_amount, rate)


def format_money(
    amount_mwk: Decimal,
    currency: str = "MWK",
    rate: Optional[Decimal] = None,
    compact: bool = False
) -> str:
    """
    Format money amount with currency prefix.
    
    Args:
        amount_mwk: Amount in MWK (base currency stored in DB)
        currency: Display currency ("MWK" or "USD")
        rate: Exchange rate for USD conversion (1 USD = rate MWK). If None and USD requested, falls back to MWK.
        compact: If True, use compact format (e.g., "MWK 1.23M")
        
    Returns:
        Formatted string like "MWK 1,234,567" or "USD 85.50"
    """
    amount_mwk = to_decimal(amount_mwk)
    
    # Convert to USD if requested
    if currency == "USD":
        # Get rate if not provided
        if rate is None:
            rate = get_mwk_per_usd()
        
        if rate is None or rate <= 0:
            # Fallback to MWK if no valid rate available
            currency = "MWK"
            amount = amount_mwk
        else:
            amount = mwk_to_usd(amount_mwk, rate)
            if amount is None:
                currency = "MWK"
                amount = amount_mwk
            else:
                # Format USD with 2 decimals
                if compact and amount >= 1000000:
                    millions = float(amount) / 1000000
                    return f"USD {millions:.2f}M"
                elif compact and amount >= 1000:
                    thousands = float(amount) / 1000
                    return f"USD {thousands:.2f}K"
                return f"USD {amount:,.2f}"
    else:
        amount = amount_mwk
    
    # Format MWK (no decimals typically)
    if compact and amount >= 1000000:
        millions = float(amount) / 1000000
        return f"MWK {millions:.2f}M"
    elif compact and amount >= 1000:
        thousands = float(amount) / 1000
        return f"MWK {thousands:.2f}K"
    
    return f"MWK {amount:,.0f}"

