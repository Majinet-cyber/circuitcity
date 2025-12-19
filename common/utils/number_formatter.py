"""
Universal Number Formatting Utilities
Mobile-first, responsive number formatting for Emajinet (Circuit City)

NON-NEGOTIABLE RULES:
- Numbers must NEVER be truncated
- Display full value where possible
- Compact only when explicitly requested
- Always provide tooltips/hover for compact values
"""

from decimal import Decimal
from typing import Optional, Tuple, Union
from django.utils.html import format_html
from django.utils.safestring import mark_safe


def format_money(
    amount: Union[int, float, Decimal],
    currency: str = "MWK",
    compact: bool = False,
    show_decimals: bool = False
) -> str:
    """
    Format money with currency symbol.
    
    Args:
        amount: The amount to format
        currency: Currency code (default: MWK)
        compact: If True, use compact notation (355k, 2.4m) for large numbers
        show_decimals: If True, show decimal places
    
    Returns:
        Formatted money string (e.g., "MWK 355,000" or "MWK 355k")
    """
    if amount is None:
        return f"{currency} 0"
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return f"{currency} 0"
    
    if compact:
        return f"{currency} {format_compact_number(amount, show_decimals=show_decimals)}"
    
    # Full format with thousands separator
    if show_decimals:
        formatted = f"{amount:,.2f}"
    else:
        formatted = f"{int(amount):,}"
    
    return f"{currency} {formatted}"


def format_compact_number(
    value: Union[int, float, Decimal],
    show_decimals: bool = True
) -> str:
    """
    Format numbers in compact notation (k, m, b).
    
    Args:
        value: The number to format
        show_decimals: If True, show one decimal place
    
    Returns:
        Compact number (e.g., "355k", "2.4m", "1.2b")
    """
    if value is None:
        return "0"
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "0"
    
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    
    if abs_value >= 1_000_000_000:
        # Billions
        num = abs_value / 1_000_000_000
        suffix = "b"
    elif abs_value >= 1_000_000:
        # Millions
        num = abs_value / 1_000_000
        suffix = "m"
    elif abs_value >= 1_000:
        # Thousands
        num = abs_value / 1_000
        suffix = "k"
    else:
        # Less than 1000 - no suffix
        return f"{sign}{abs_value:,.0f}" if not show_decimals else f"{sign}{abs_value:,.1f}"
    
    if show_decimals:
        return f"{sign}{num:.1f}{suffix}"
    else:
        return f"{sign}{int(num)}{suffix}"


def format_number_with_tooltip(
    value: Union[int, float, Decimal],
    compact_threshold: int = 100_000,
    currency: Optional[str] = None
) -> str:
    """
    Format number with HTML tooltip showing full value when compacted.
    Use this for HTML contexts (Django templates).
    
    Args:
        value: The number to format
        compact_threshold: Numbers above this threshold will be compacted
        currency: If provided, format as money
    
    Returns:
        HTML string with tooltip (safe for templates)
    """
    if value is None:
        return "0"
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "0"
    
    abs_value = abs(value)
    
    # If below threshold, show full value
    if abs_value < compact_threshold:
        if currency:
            return format_money(value, currency=currency, compact=False)
        return f"{int(value):,}"
    
    # Show compact with tooltip
    if currency:
        full_value = format_money(value, currency=currency, compact=False)
        compact_value = format_money(value, currency=currency, compact=True)
    else:
        full_value = f"{int(value):,}"
        compact_value = format_compact_number(value)
    
    return format_html(
        '<span class="num-tooltip" data-full-value="{}" title="{}">{}</span>',
        full_value,
        full_value,
        compact_value
    )


def get_display_ranges(value: Union[int, float, Decimal]) -> Tuple[str, str]:
    """
    Get both full and compact representations of a number.
    
    Args:
        value: The number to format
    
    Returns:
        Tuple of (full_value, compact_value)
    """
    if value is None:
        return ("0", "0")
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return ("0", "0")
    
    full = f"{int(value):,}"
    compact = format_compact_number(value)
    
    return (full, compact)


def format_percentage(
    value: Union[int, float, Decimal],
    decimal_places: int = 1,
    include_symbol: bool = True
) -> str:
    """
    Format percentage values.
    
    Args:
        value: The percentage value (e.g., 25 for 25%)
        decimal_places: Number of decimal places
        include_symbol: If True, append % symbol
    
    Returns:
        Formatted percentage (e.g., "25.5%")
    """
    if value is None:
        return "0%"
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "0%"
    
    formatted = f"{value:.{decimal_places}f}"
    
    if include_symbol:
        return f"{formatted}%"
    return formatted


def format_unit_value(
    value: Union[int, float, Decimal],
    unit: str,
    compact: bool = False
) -> str:
    """
    Format number with unit (e.g., "500 kg", "2.5k items").
    
    Args:
        value: The number value
        unit: The unit of measurement
        compact: If True, use compact notation
    
    Returns:
        Formatted string with unit
    """
    if value is None:
        return f"0 {unit}"
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return f"0 {unit}"
    
    if compact:
        formatted = format_compact_number(value)
    else:
        formatted = f"{int(value):,}"
    
    return f"{formatted} {unit}"


def should_compact(value: Union[int, float, Decimal], threshold: int = 100_000) -> bool:
    """
    Determine if a number should be compacted based on threshold.
    
    Args:
        value: The number to check
        threshold: Threshold for compacting
    
    Returns:
        True if should compact, False otherwise
    """
    if value is None:
        return False
    
    try:
        abs_value = abs(float(value))
        return abs_value >= threshold
    except (ValueError, TypeError):
        return False


# Alias for backwards compatibility
format_currency = format_money
format_number_compact = format_compact_number

