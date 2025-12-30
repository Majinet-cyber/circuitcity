"""
Liquor vertical configuration and conversion helpers.
Single source of truth for liquor workflows.

Business Goal: Make liquor workflows "stupid simple" for Malawian merchants.
Design Principle: Track stock internally in BASE UNITS (bottles/cans).
Crates/cases/packs are only "entry/selling shortcuts" that convert to base units.
"""
from decimal import Decimal
from typing import Dict, Optional, Tuple
from django.core.exceptions import ValidationError


class LiquorKind:
    """Liquor product types (categories)"""
    BEER = "beer"
    CIDER = "cider"
    WINE = "wine"
    SPIRITS = "spirits"
    WHISKY = "whiskey"  # Note: database uses "whiskey" spelling
    
    ALL = [BEER, CIDER, WINE, SPIRITS, WHISKY]
    
    CHOICES = [
        (BEER, "Beer"),
        (CIDER, "Cider"),
        (WINE, "Wine"),
        (SPIRITS, "Spirits"),
        (WHISKY, "Whisky/Whiskey"),
    ]


class LiquorBaseUnit:
    """Base units for liquor products"""
    BOTTLE = "bottle"
    CAN = "can"
    
    CHOICES = [
        (BOTTLE, "Bottle"),
        (CAN, "Can"),
    ]


class PackLabel:
    """Pack/bulk unit labels"""
    CRATE = "Crate"
    CASE = "Case"
    PACK = "Pack"


# Malawi-specific defaults
DEFAULT_PACK_SIZES: Dict[str, Tuple[str, int]] = {
    # (pack_label, pack_size)
    LiquorKind.BEER: (PackLabel.CRATE, 20),     # 20 bottles per crate (Malawi standard)
    LiquorKind.CIDER: (PackLabel.CRATE, 20),    # 20 bottles per crate
    LiquorKind.WINE: (PackLabel.CASE, 6),       # 6 bottles per case
    LiquorKind.SPIRITS: (PackLabel.CASE, 6),    # 6 bottles per case
    LiquorKind.WHISKY: (PackLabel.CASE, 6),     # 6 bottles per case
}


def get_default_pack_config(liquor_kind: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Get default pack label and size for a liquor kind.
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
    
    Returns:
        Tuple of (pack_label, pack_size) or (None, None) if not applicable
    """
    return DEFAULT_PACK_SIZES.get(liquor_kind, (None, None))


def get_base_unit_default(liquor_kind: str) -> str:
    """
    Get default base unit for a liquor kind.
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
    
    Returns:
        "bottle" or "can" (default is "bottle" for all)
    """
    # Beer and cider can be bottle or can; default to bottle
    # Wine, spirits, whisky are always bottles
    return LiquorBaseUnit.BOTTLE


def to_base_units(
    qty: int,
    unit: str,
    base_unit: str,
    pack_size: Optional[int] = None,
    pack_label: Optional[str] = None,
) -> int:
    """
    Convert quantity + unit to base units (bottles/cans).
    
    Args:
        qty: Quantity entered by user
        unit: Unit entered by user (e.g., "bottle", "crate", "case")
        base_unit: The product's base unit (e.g., "bottle", "can")
        pack_size: Number of base units in a pack (e.g., 20 for crate)
        pack_label: Pack label (e.g., "Crate", "Case")
    
    Returns:
        Quantity in base units
    
    Raises:
        ValidationError: If conversion is not possible or invalid
    """
    # Validate qty > 0
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    
    # Normalize unit strings to lowercase for comparison
    unit_lower = unit.lower().strip()
    base_unit_lower = base_unit.lower().strip()
    
    # If unit matches base unit, no conversion needed
    if unit_lower == base_unit_lower:
        return qty
    
    # If unit is a pack/crate/case, convert using pack_size
    pack_units = ["crate", "case", "pack"]
    if unit_lower in pack_units:
        # Check if pack_label and pack_size are configured
        if not pack_label or not pack_size:
            raise ValidationError(
                f"Cannot stock/sell by {unit} - pack size not configured. "
                "Please edit product and set pack size first."
            )
        
        # Check if unit matches pack_label
        if pack_label and unit_lower == pack_label.lower():
            return qty * pack_size
        else:
            raise ValidationError(
                f"This product uses '{pack_label}' not '{unit}'. "
                f"Please select '{pack_label}' or '{base_unit}'."
            )
    
    # Unknown unit
    raise ValidationError(
        f"Unknown unit '{unit}'. Expected '{base_unit}' or pack unit."
    )


def from_base_units(
    qty_base: int,
    target_unit: str,
    base_unit: str,
    pack_size: Optional[int] = None,
) -> Decimal:
    """
    Convert base units to display units (for receipts/displays).
    
    Args:
        qty_base: Quantity in base units
        target_unit: Unit to convert to (e.g., "bottle", "crate")
        base_unit: The product's base unit
        pack_size: Pack size if converting to pack units
    
    Returns:
        Quantity in target units (as Decimal for partial packs)
    """
    if target_unit.lower() == base_unit.lower():
        return Decimal(qty_base)
    
    pack_units = ["crate", "case", "pack"]
    if target_unit.lower() in pack_units:
        if not pack_size or pack_size == 0:
            raise ValidationError("Pack size not configured")
        return Decimal(qty_base) / Decimal(pack_size)
    
    raise ValidationError(f"Unknown target unit: {target_unit}")


def format_display_quantity(qty_base: int, base_unit: str, pack_size: Optional[int] = None, pack_label: Optional[str] = None) -> str:
    """
    Format base quantity for display (e.g., "2 Crates (40 bottles)" or "15 bottles").
    
    Args:
        qty_base: Quantity in base units
        base_unit: Base unit label (e.g., "bottle", "can")
        pack_size: Optional pack size for conversion
        pack_label: Optional pack label (e.g., "Crate")
    
    Returns:
        Formatted string
    """
    if not pack_size or not pack_label or qty_base < pack_size:
        # Show only base units
        return f"{qty_base} {base_unit}{'s' if qty_base != 1 else ''}"
    
    # Show packs + remainder
    packs = qty_base // pack_size
    remainder = qty_base % pack_size
    
    pack_str = f"{packs} {pack_label}{'s' if packs != 1 else ''}"
    if remainder > 0:
        return f"{pack_str} + {remainder} {base_unit}{'s' if remainder != 1 else ''}"
    else:
        return f"{pack_str} ({qty_base} {base_unit}s)"


def validate_pack_config(liquor_kind: str, pack_size: Optional[int]) -> None:
    """
    Validate pack configuration is reasonable.
    
    Args:
        liquor_kind: Liquor category
        pack_size: Pack size to validate
    
    Raises:
        ValidationError: If pack size is invalid
    """
    if pack_size is not None:
        if pack_size < 1:
            raise ValidationError("Pack size must be at least 1")
        if pack_size > 100:
            raise ValidationError("Pack size seems too large (max 100). Please check.")


def should_show_pack_option(liquor_kind: str) -> bool:
    """
    Determine if pack/bulk stocking should be shown by default for this liquor kind.
    
    Args:
        liquor_kind: Liquor category
    
    Returns:
        True if pack option should be shown (beer/cider), False otherwise
    """
    return liquor_kind in [LiquorKind.BEER, LiquorKind.CIDER]

