"""
Liquor vertical configuration and conversion helpers.
Single source of truth for liquor workflows.

Business Goal: Make liquor workflows "stupid simple" for Malawian merchants.
Design Principle: Track stock internally in BASE UNITS (bottles/cans/glasses/shots).
Crates/cases/packs are only "entry/selling shortcuts" that convert to base units.

REAL-WORLD RULES (enforced in UI + backend):
- BEER: sold per BOTTLE/CAN and optionally CRATE. Never shots.
- CIDER: sold per BOTTLE/CAN and optionally 6-PACK. NO CRATES for cider.
- WINE: sold per GLASS or BOTTLE. Never shots.
- WHISKY & SPIRITS: sold per SHOT or BOTTLE. (Optional CASE for stocking.)
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
    """Base units for liquor products (what we track internally)"""
    BOTTLE = "bottle"
    CAN = "can"
    GLASS = "glass"
    SHOT = "shot"
    
    CHOICES = [
        (BOTTLE, "Bottle"),
        (CAN, "Can"),
        (GLASS, "Glass"),
        (SHOT, "Shot"),
    ]


class PackLabel:
    """Pack/bulk unit labels for stocking/selling"""
    CRATE = "Crate"
    SIX_PACK = "6-Pack"
    CASE = "Case"


# Malawi-specific defaults
DEFAULT_PACK_SIZES: Dict[str, Tuple[Optional[str], Optional[int]]] = {
    # (pack_label, pack_size)
    LiquorKind.BEER: (PackLabel.CRATE, 20),      # 20 bottles per crate (Malawi standard)
    LiquorKind.CIDER: (PackLabel.SIX_PACK, 6),   # 6 bottles per 6-pack (NO CRATES for cider)
    LiquorKind.WINE: (PackLabel.CASE, 6),        # 6 bottles per case (optional for stocking)
    # NOTE: Spirits/Whisky stock-in is BOTTLE-ONLY (no case/crate/pack allowed)
    LiquorKind.SPIRITS: (None, None),            # Stock-in by bottle only
    LiquorKind.WHISKY: (None, None),             # Stock-in by bottle only
}

# Default glasses per bottle for wine (Malawi standard)
DEFAULT_GLASSES_PER_BOTTLE = 5

# Default shots per bottle for spirits/whisky (750ml bottle / 30ml shot = 25 shots + safety margin)
DEFAULT_SHOTS_PER_BOTTLE = 24  # Changed from 30 to 24 for Malawi standard

# Barman/staff shots per bottle (non-sellable, automatically accounted for)
DEFAULT_BARMAN_SHOTS_PER_BOTTLE = 2  # 2 shots per bottle reserved for staff/spillage


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
    Get default base unit for a liquor kind based on real-world selling patterns.
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
    
    Returns:
        Base unit label (bottle, can, glass, or shot)
    """
    # Beer and cider: sold by bottle/can
    if liquor_kind in (LiquorKind.BEER, LiquorKind.CIDER):
        return LiquorBaseUnit.BOTTLE
    
    # Wine: sold by glass (bottles are for stocking)
    elif liquor_kind == LiquorKind.WINE:
        return LiquorBaseUnit.GLASS
    
    # Spirits/Whisky: sold by shot (bottles are for stocking)
    elif liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
        return LiquorBaseUnit.SHOT
    
    # Default fallback
    return LiquorBaseUnit.BOTTLE


def get_allowed_units(liquor_kind: str, pack_enabled: bool = False, for_stock_in: bool = False) -> list:
    """
    Get list of allowed units for a liquor kind based on real-world rules.
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
        pack_enabled: Whether pack/bulk option is enabled for this product
        for_stock_in: If True, returns stock-in allowed units; if False, returns selling allowed units
    
    Returns:
        List of allowed unit labels (e.g., ["bottle", "crate"] for beer)
    """
    if liquor_kind == LiquorKind.BEER:
        # Beer: bottle/can + optional crate (same for stock-in and selling)
        units = [LiquorBaseUnit.BOTTLE, LiquorBaseUnit.CAN]
        if pack_enabled:
            units.append(PackLabel.CRATE.lower())
        return units
    
    elif liquor_kind == LiquorKind.CIDER:
        # Cider: bottle/can + optional 6-pack (NO CRATES, same for stock-in and selling)
        units = [LiquorBaseUnit.BOTTLE, LiquorBaseUnit.CAN]
        if pack_enabled:
            units.append("6-pack")
        return units
    
    elif liquor_kind == LiquorKind.WINE:
        # Wine: glass or bottle (NO SHOTS, same for stock-in and selling)
        return [LiquorBaseUnit.GLASS, LiquorBaseUnit.BOTTLE]
    
    elif liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
        # NEW RULE: Spirits/Whisky stock-in is BOTTLE-ONLY
        if for_stock_in:
            return [LiquorBaseUnit.BOTTLE]  # Stock-in: BOTTLE ONLY (no case, no shot)
        else:
            # Selling: shot or bottle allowed
            return [LiquorBaseUnit.SHOT, LiquorBaseUnit.BOTTLE]
    
    # Default fallback
    return [LiquorBaseUnit.BOTTLE]


def validate_cider_pack_size(pack_size: int) -> None:
    """
    Validate that cider pack_size is exactly 6.
    
    Args:
        pack_size: Pack size to validate
    
    Raises:
        ValidationError: If pack_size is not 6
    """
    if pack_size != 6:
        raise ValidationError(
            f"Cider pack size must be exactly 6 (6-pack). "
            f"Got: {pack_size}. Cider does not use crates."
        )


def validate_unit_for_kind(liquor_kind: str, unit: str, pack_enabled: bool = False, for_stock_in: bool = False) -> None:
    """
    Validate that a unit is allowed for a liquor kind.
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
        unit: Unit to validate (e.g., "bottle", "shot", "crate")
        pack_enabled: Whether pack/bulk option is enabled
        for_stock_in: If True, validates against stock-in rules; if False, validates against selling rules
    
    Raises:
        ValidationError: If unit is not allowed for this liquor kind
    """
    allowed_units = get_allowed_units(liquor_kind, pack_enabled, for_stock_in=for_stock_in)
    unit_lower = unit.lower().strip()
    
    if unit_lower not in allowed_units:
        allowed_str = ", ".join(allowed_units)
        
        # Specific error messages for common mistakes
        if unit_lower == "shot" and liquor_kind in (LiquorKind.BEER, LiquorKind.CIDER):
            raise ValidationError(
                f"{liquor_kind.title()} cannot be sold by shot. "
                f"Use bottle/can or pack."
            )
        elif unit_lower == "shot" and liquor_kind == LiquorKind.WINE:
            raise ValidationError(
                f"Wine cannot be sold by shot. "
                f"Use glass or bottle."
            )
        elif unit_lower == "crate" and liquor_kind == LiquorKind.CIDER:
            raise ValidationError(
                f"Cider uses 6-packs, not crates. "
                f"Please select 6-pack or bottle/can."
            )
        elif unit_lower == "case" and liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY) and for_stock_in:
            raise ValidationError(
                f"{liquor_kind.title()} stock-in must be by BOTTLE only. "
                f"Case/pack not allowed for stock-in. Use bottle."
            )
        elif unit_lower == "shot" and liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY) and for_stock_in:
            raise ValidationError(
                f"{liquor_kind.title()} stock-in must be by BOTTLE only. "
                f"Cannot stock-in by shot. Use bottle."
            )
        else:
            context = "stock-in" if for_stock_in else "selling"
            raise ValidationError(
                f"Invalid unit '{unit}' for {liquor_kind.title()} {context}. "
                f"Allowed units: {allowed_str}"
            )


def to_base_units(
    qty: int,
    unit: str,
    product,  # MerchProduct instance
) -> int:
    """
    SINGLE SOURCE OF TRUTH: Convert quantity + unit to base units.
    
    This is the ONE conversion helper used everywhere:
    - Stock in operations
    - Sales operations
    - Inventory calculations
    
    Args:
        qty: Quantity entered by user
        unit: Unit entered by user (e.g., "bottle", "crate", "6-pack", "shot", "glass")
        product: MerchProduct instance (must have category, pack_label, bottles_per_crate, etc.)
    
    Returns:
        Quantity in base units
    
    Raises:
        ValidationError: If conversion is not possible or invalid
    """
    # Validate qty > 0
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    
    # Get product attributes
    liquor_kind = (product.category or "").lower()
    base_unit = get_base_unit_default(liquor_kind)
    pack_label = product.pack_label
    pack_size = product.bottles_per_crate
    glasses_per_bottle = product.glasses_per_bottle
    shots_per_bottle = product.shots_per_bottle
    
    # Normalize unit string
    unit_lower = unit.lower().strip()
    
    # Validate unit is allowed for this liquor kind
    validate_unit_for_kind(liquor_kind, unit, pack_enabled=(pack_label is not None))
    
    # If unit matches base unit, no conversion needed
    if unit_lower == base_unit.lower():
        return qty
    
    # Bottle -> Glass conversion (for wine)
    if unit_lower == "bottle" and base_unit == LiquorBaseUnit.GLASS:
        if not glasses_per_bottle:
            raise ValidationError(
                f"Cannot convert bottles to glasses - glasses_per_bottle not configured. "
                f"Please edit product and set glasses per bottle."
            )
        return qty * glasses_per_bottle
    
    # Bottle -> Shot conversion (for spirits/whisky)
    if unit_lower == "bottle" and base_unit == LiquorBaseUnit.SHOT:
        # Use default if not configured (backward compatibility)
        effective_shots_per_bottle = shots_per_bottle or DEFAULT_SHOTS_PER_BOTTLE
        if not effective_shots_per_bottle:
            raise ValidationError(
                f"Cannot convert bottles to shots - shots_per_bottle not configured. "
                f"Please edit product and set shots per bottle."
            )
        return qty * effective_shots_per_bottle
    
    # Pack/Crate/Case conversion
    pack_unit_aliases = ["crate", "case", "pack", "6-pack", "6pack", "sixpack"]
    if unit_lower in pack_unit_aliases:
        if not pack_label or not pack_size:
            raise ValidationError(
                f"Cannot stock/sell by {unit} - pack size not configured. "
                f"Please edit product and set pack size first."
            )
        
        # For cider, ensure they're using 6-pack not crate
        if liquor_kind == LiquorKind.CIDER and unit_lower == "crate":
            raise ValidationError(
                f"Cider uses 6-packs, not crates. Please select 6-pack or bottle/can."
            )
        
        # Check if unit matches pack_label (loose matching)
        pack_label_lower = pack_label.lower().strip().replace("-", "").replace(" ", "")
        unit_normalized = unit_lower.replace("-", "").replace(" ", "")
        
        if pack_label_lower == unit_normalized or unit_lower in ["crate", "case", "pack"]:
            return qty * pack_size
        else:
            raise ValidationError(
                f"This product uses '{pack_label}' not '{unit}'. "
                f"Please select '{pack_label}' or base unit."
            )
    
    # Unknown unit
    raise ValidationError(
        f"Cannot convert '{unit}' to base units. "
        f"Expected base unit '{base_unit}' or configured pack unit."
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


def format_display_quantity(
    qty_base: int,
    base_unit: str,
    pack_size: Optional[int] = None,
    pack_label: Optional[str] = None
) -> str:
    """
    Format base quantity for display (e.g., "2 Crates (40 bottles)" or "15 bottles").
    
    Args:
        qty_base: Quantity in base units
        base_unit: Base unit label (e.g., "bottle", "can", "glass", "shot")
        pack_size: Optional pack size for conversion
        pack_label: Optional pack label (e.g., "Crate", "6-Pack")
    
    Returns:
        Formatted string
    """
    if not pack_size or not pack_label or qty_base < pack_size:
        # Show only base units
        unit_plural = f"{base_unit}s" if qty_base != 1 else base_unit
        return f"{qty_base} {unit_plural}"
    
    # Show packs + remainder
    packs = qty_base // pack_size
    remainder = qty_base % pack_size
    
    pack_str = f"{packs} {pack_label}{'s' if packs != 1 else ''}"
    if remainder > 0:
        unit_plural = f"{base_unit}s" if remainder != 1 else base_unit
        return f"{pack_str} + {remainder} {unit_plural}"
    else:
        return f"{pack_str} ({qty_base} {base_unit}s)"


def get_default_config_for_kind(liquor_kind: str) -> dict:
    """
    Get default configuration for a liquor kind (Malawi standards).
    
    Args:
        liquor_kind: beer, cider, wine, spirits, or whiskey
    
    Returns:
        Dict with:
            - base_unit: str
            - pack_label: Optional[str]
            - pack_size: Optional[int]
            - glasses_per_bottle: Optional[int] (wine only)
            - shots_per_bottle: Optional[int] (spirits/whisky only)
            - pack_enabled_by_default: bool
    """
    config = {
        "base_unit": get_base_unit_default(liquor_kind),
        "pack_label": None,
        "pack_size": None,
        "glasses_per_bottle": None,
        "shots_per_bottle": None,
        "pack_enabled_by_default": False,
    }
    
    # Get pack defaults
    pack_label, pack_size = DEFAULT_PACK_SIZES.get(liquor_kind, (None, None))
    config["pack_label"] = pack_label
    config["pack_size"] = pack_size
    
    # Beer and cider enable packs by default
    if liquor_kind in (LiquorKind.BEER, LiquorKind.CIDER):
        config["pack_enabled_by_default"] = True
    
    # Wine: add glasses_per_bottle
    if liquor_kind == LiquorKind.WINE:
        config["glasses_per_bottle"] = DEFAULT_GLASSES_PER_BOTTLE
    
    # Spirits/Whisky: add shots_per_bottle
    if liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
        config["shots_per_bottle"] = DEFAULT_SHOTS_PER_BOTTLE
    
    return config


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

