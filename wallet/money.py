from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MONEY_QUANT = Decimal("0.01")


def q2(value: Any = None) -> Decimal:
    """
    Return a Decimal rounded to two places using HALF_UP.

    Financial forms in this app receive blanks, None, and occasionally malformed
    strings from browsers. Treat those as zero at the parsing boundary so money
    calculations do not crash with 500s.
    """
    if value in (None, ""):
        return Decimal("0.00")
    try:
        if not isinstance(value, Decimal):
            value = Decimal(str(value).replace(",", "").strip())
        return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return Decimal("0.00")
