# inventory/services/barcodes.py
"""
Barcode normalization service.

Provides a simple, consistent barcode normalizer that removes whitespace
while preserving the raw digits and letters intact.
"""
import re


def normalize_barcode(value: str) -> str:
    """
    Normalize a barcode by removing whitespace.

    Removes whitespace and keeps the raw digits/letters intact.
    This is a simpler normalization than normalize_barcode_enhanced,
    which also uppercases and removes special characters.

    Args:
        value: Raw barcode string

    Returns:
        Normalized barcode string (empty string if input is None/empty)
    """
    if not value:
        return ""

    # Remove whitespace and keep the raw digits/letters intact
    return re.sub(r"\s+", "", (value or "").strip())
