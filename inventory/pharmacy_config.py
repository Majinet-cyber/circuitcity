"""
Pharmacy vertical configuration and conversion helpers.
Single source of truth for pharmacy workflows.

Business Goal: Make pharmacy workflows "stupid simple" for Malawian merchants.
Design Principle: Track stock internally in BASE UNITS (smallest sellable unit per product).
Packaging (strips/boxes) are only "entry/selling shortcuts" that convert to base units.

REAL-WORLD RULES (enforced in UI + backend):
- TABLETS/CAPSULES: base unit = tablet/capsule. Optional strip/box packaging.
- SYRUPS/DROPS: base unit = bottle. No packaging.
- OINTMENTS/CREAMS: base unit = tube. No packaging.
- COSMETICS: base unit = piece. Optional packaging.
- BARCODE IS ALWAYS OPTIONAL - system must work fully without it.
- EXPIRY/BATCH are optional for v1 (must NOT block selling).
"""
from decimal import Decimal
from typing import Dict, Optional, Tuple
from django.core.exceptions import ValidationError


class PharmacyCategory:
    """Pharmacy product categories (simplified for Malawi merchants)"""

    TABLETS_CAPSULES = "tablets_capsules"
    SYRUP = "syrup"
    OINTMENT = "ointment"
    DROPS = "drops"
    COSMETICS = "cosmetics"
    OTHER = "other"
    
    # Detailed cosmetics subcategories (from models_pharmacy.PharmacyCategory)
    SKIN_CARE = "skin_care"
    HAIR_CARE = "hair_care"
    PERSONAL_CARE = "personal_care"
    BEAUTY_MAKEUP = "beauty_makeup"
    BABY_CARE = "baby_care"
    ORAL_CARE = "oral_care"

    ALL = [
        TABLETS_CAPSULES, SYRUP, OINTMENT, DROPS, COSMETICS, OTHER,
        # Detailed cosmetics categories
        SKIN_CARE, HAIR_CARE, PERSONAL_CARE, BEAUTY_MAKEUP, BABY_CARE, ORAL_CARE,
    ]

    CHOICES = [
        (TABLETS_CAPSULES, "Tablets/Capsules"),
        (SYRUP, "Syrup"),
        (OINTMENT, "Ointment/Cream"),
        (DROPS, "Drops"),
        (COSMETICS, "Cosmetics"),
        (OTHER, "Other"),
    ]


class PharmacyBaseUnit:
    """Base units for pharmacy products (what we track internally)"""

    TABLET = "tablet"
    CAPSULE = "capsule"
    BOTTLE = "bottle"
    TUBE = "tube"
    PIECE = "piece"

    CHOICES = [
        (TABLET, "Tablet"),
        (CAPSULE, "Capsule"),
        (BOTTLE, "Bottle"),
        (TUBE, "Tube"),
        (PIECE, "Piece"),
    ]


class PackagingUnit:
    """Packaging unit labels for stocking/selling (optional)"""

    STRIP = "strip"
    BOX = "box"

    CHOICES = [
        (STRIP, "Strip"),
        (BOX, "Box"),
    ]


# Malawi-specific defaults for categories
DEFAULT_BASE_UNITS: Dict[str, str] = {
    PharmacyCategory.TABLETS_CAPSULES: PharmacyBaseUnit.TABLET,
    PharmacyCategory.SYRUP: PharmacyBaseUnit.BOTTLE,
    PharmacyCategory.OINTMENT: PharmacyBaseUnit.TUBE,
    PharmacyCategory.DROPS: PharmacyBaseUnit.BOTTLE,
    PharmacyCategory.COSMETICS: PharmacyBaseUnit.PIECE,
    PharmacyCategory.OTHER: PharmacyBaseUnit.PIECE,
}

# Default packaging for categories (None = no packaging by default)
DEFAULT_PACKAGING_CONFIG: Dict[str, Tuple[bool, Optional[int], Optional[int]]] = {
    # (pack_enabled_by_default, suggested_strip_size, suggested_box_size)
    PharmacyCategory.TABLETS_CAPSULES: (True, 10, 10),  # 10 tablets per strip, 10 strips per box
    PharmacyCategory.SYRUP: (False, None, None),  # No packaging
    PharmacyCategory.OINTMENT: (False, None, None),  # No packaging
    PharmacyCategory.DROPS: (False, None, None),  # No packaging
    PharmacyCategory.COSMETICS: (False, None, None),  # No packaging (cosmetics usually sold as-is)
    PharmacyCategory.OTHER: (False, None, None),  # No packaging by default
}


def get_default_base_unit(category: str) -> str:
    """
    Get default base unit for a pharmacy category based on real-world patterns.

    Args:
        category: Pharmacy category (tablets_capsules, syrup, etc.)

    Returns:
        Base unit label (tablet, bottle, tube, or piece)
    """
    return DEFAULT_BASE_UNITS.get(category, PharmacyBaseUnit.PIECE)


def get_default_packaging_config(category: str) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    Get default packaging configuration for a pharmacy category.

    Args:
        category: Pharmacy category

    Returns:
        Tuple of (pack_enabled_by_default, suggested_strip_size, suggested_box_size)
    """
    return DEFAULT_PACKAGING_CONFIG.get(category, (False, None, None))


def get_allowed_units(category: str, has_strips: bool = False, has_boxes: bool = False) -> list:
    """
    Get list of allowed units for a pharmacy category.

    Args:
        category: Pharmacy category
        has_strips: Whether product has strip packaging configured
        has_boxes: Whether product has box packaging configured

    Returns:
        List of allowed unit labels (e.g., ["tablet", "strip", "box"] for tablets)
    """
    base_unit = get_default_base_unit(category)
    units = [base_unit]

    # Add packaging units if configured
    if has_strips:
        units.append(PackagingUnit.STRIP)
    if has_boxes:
        units.append(PackagingUnit.BOX)

    return units


def validate_unit_for_category(category: str, unit: str, has_strips: bool = False, has_boxes: bool = False) -> None:
    """
    Validate that a unit is allowed for a pharmacy category.

    Args:
        category: Pharmacy category
        unit: Unit to validate (e.g., "tablet", "strip", "box")
        has_strips: Whether product has strip packaging configured
        has_boxes: Whether product has box packaging configured

    Raises:
        ValidationError: If unit is not allowed for this category
    """
    allowed_units = get_allowed_units(category, has_strips, has_boxes)
    unit_lower = unit.lower().strip()

    if unit_lower not in allowed_units:
        allowed_str = ", ".join(allowed_units)

        # Specific error messages for common mistakes
        if unit_lower in ("strip", "box") and not has_strips and not has_boxes:
            raise ValidationError(
                f"Cannot use {unit} - packaging not configured for this product. "
                f"Please edit product and set strip/box sizes first."
            )
        else:
            raise ValidationError(f"Invalid unit '{unit}' for {category}. " f"Allowed units: {allowed_str}")


def to_base_units(
    qty: int,
    unit: str,
    product,  # PharmacyBatch instance
) -> int:
    """
    SINGLE SOURCE OF TRUTH: Convert quantity + unit to base units.

    This is the ONE conversion helper used everywhere:
    - Stock in operations
    - Sales operations
    - Inventory calculations

    Args:
        qty: Quantity entered by user
        unit: Unit entered by user (e.g., "tablet", "strip", "box", "bottle")
        product: PharmacyBatch instance (must have strip_size, box_size, etc.)

    Returns:
        Quantity in base units

    Raises:
        ValidationError: If conversion is not possible or invalid
    """
    # Validate qty > 0
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    # Get product attributes
    base_unit = get_default_base_unit(getattr(product, "category", PharmacyCategory.OTHER))
    strip_size = getattr(product, "strip_size", None)
    box_size = getattr(product, "box_size", None)
    tablets_per_box = getattr(product, "tablets_per_box", None)

    # Normalize unit string
    unit_lower = unit.lower().strip()

    # If unit matches base unit, no conversion needed
    if unit_lower == base_unit.lower():
        return qty

    # Strip conversion
    if unit_lower == "strip":
        if not strip_size:
            raise ValidationError(
                f"Cannot stock/sell by strip - strip size not configured. "
                f"Please edit product and set strip size first."
            )
        return qty * strip_size

    # Box conversion
    if unit_lower == "box":
        # Two modes: box via strips OR box directly to tablets
        if tablets_per_box:
            # Direct box -> tablets conversion
            return qty * tablets_per_box
        elif box_size and strip_size:
            # Box -> strips -> tablets conversion
            return qty * box_size * strip_size
        elif box_size:
            # Box size without strip size (treat box_size as tablets per box)
            return qty * box_size
        else:
            raise ValidationError(
                f"Cannot stock/sell by box - box size not configured. " f"Please edit product and set box size first."
            )

    # Unknown unit
    raise ValidationError(
        f"Cannot convert '{unit}' to base units. " f"Expected base unit '{base_unit}' or configured packaging unit."
    )


def from_base_units(
    qty_base: int,
    target_unit: str,
    base_unit: str,
    strip_size: Optional[int] = None,
    box_size: Optional[int] = None,
    tablets_per_box: Optional[int] = None,
) -> Decimal:
    """
    Convert base units to display units (for receipts/displays).

    Args:
        qty_base: Quantity in base units
        target_unit: Unit to convert to (e.g., "tablet", "strip", "box")
        base_unit: The product's base unit
        strip_size: Strip size if converting to strips
        box_size: Box size if converting to boxes (strips per box)
        tablets_per_box: Direct tablets per box (alternative to box_size)

    Returns:
        Quantity in target units (as Decimal for partial packs)
    """
    if target_unit.lower() == base_unit.lower():
        return Decimal(qty_base)

    if target_unit.lower() == "strip":
        if not strip_size or strip_size == 0:
            raise ValidationError("Strip size not configured")
        return Decimal(qty_base) / Decimal(strip_size)

    if target_unit.lower() == "box":
        if tablets_per_box:
            return Decimal(qty_base) / Decimal(tablets_per_box)
        elif box_size and strip_size:
            return Decimal(qty_base) / Decimal(box_size * strip_size)
        elif box_size:
            return Decimal(qty_base) / Decimal(box_size)
        else:
            raise ValidationError("Box size not configured")

    raise ValidationError(f"Unknown target unit: {target_unit}")


def format_display_quantity(
    qty_base: int,
    base_unit: str,
    strip_size: Optional[int] = None,
    box_size: Optional[int] = None,
    tablets_per_box: Optional[int] = None,
) -> str:
    """
    Format base quantity for display (e.g., "2 Boxes (200 tablets)" or "15 tablets").

    Args:
        qty_base: Quantity in base units
        base_unit: Base unit label (e.g., "tablet", "bottle", "tube")
        strip_size: Optional strip size for conversion
        box_size: Optional box size for conversion (strips per box)
        tablets_per_box: Optional direct tablets per box

    Returns:
        Formatted string
    """
    # Calculate total box/strip representation if possible
    if tablets_per_box and qty_base >= tablets_per_box:
        boxes = qty_base // tablets_per_box
        remainder = qty_base % tablets_per_box

        box_str = f"{boxes} Box{'es' if boxes != 1 else ''}"
        if remainder > 0:
            unit_plural = f"{base_unit}s" if remainder != 1 else base_unit
            return f"{box_str} + {remainder} {unit_plural}"
        else:
            return f"{box_str} ({qty_base} {base_unit}s)"

    elif box_size and strip_size:
        tablets_per_box_calc = box_size * strip_size
        if qty_base >= tablets_per_box_calc:
            boxes = qty_base // tablets_per_box_calc
            remainder = qty_base % tablets_per_box_calc

            box_str = f"{boxes} Box{'es' if boxes != 1 else ''}"
            if remainder > 0:
                unit_plural = f"{base_unit}s" if remainder != 1 else base_unit
                return f"{box_str} + {remainder} {unit_plural}"
            else:
                return f"{box_str} ({qty_base} {base_unit}s)"

    elif strip_size and qty_base >= strip_size:
        strips = qty_base // strip_size
        remainder = qty_base % strip_size

        strip_str = f"{strips} Strip{'s' if strips != 1 else ''}"
        if remainder > 0:
            unit_plural = f"{base_unit}s" if remainder != 1 else base_unit
            return f"{strip_str} + {remainder} {unit_plural}"
        else:
            return f"{strip_str} ({qty_base} {base_unit}s)"

    # Show only base units
    unit_plural = f"{base_unit}s" if qty_base != 1 else base_unit
    return f"{qty_base} {unit_plural}"


def get_default_config_for_category(category: str) -> dict:
    """
    Get default configuration for a pharmacy category (Malawi standards).

    Args:
        category: Pharmacy category

    Returns:
        Dict with:
            - base_unit: str
            - pack_enabled_by_default: bool
            - suggested_strip_size: Optional[int]
            - suggested_box_size: Optional[int]
    """
    base_unit = get_default_base_unit(category)
    pack_enabled, strip_size, box_size = get_default_packaging_config(category)

    return {
        "base_unit": base_unit,
        "pack_enabled_by_default": pack_enabled,
        "suggested_strip_size": strip_size,
        "suggested_box_size": box_size,
    }


def should_show_packaging_option(category: str) -> bool:
    """
    Determine if packaging option should be shown by default for this category.

    Args:
        category: Pharmacy category

    Returns:
        True if packaging option should be shown (tablets/capsules), False otherwise
    """
    pack_enabled, _, _ = get_default_packaging_config(category)
    return pack_enabled


def validate_packaging_config(
    strip_size: Optional[int], box_size: Optional[int], tablets_per_box: Optional[int]
) -> None:
    """
    Validate packaging configuration is reasonable.

    Args:
        strip_size: Strip size to validate
        box_size: Box size to validate (strips per box)
        tablets_per_box: Direct tablets per box (alternative to box_size)

    Raises:
        ValidationError: If packaging configuration is invalid
    """
    if strip_size is not None:
        if strip_size < 1:
            raise ValidationError("Strip size must be at least 1")
        if strip_size > 1000:
            raise ValidationError("Strip size seems too large (max 1000). Please check.")

    if box_size is not None:
        if box_size < 1:
            raise ValidationError("Box size must be at least 1")
        if box_size > 1000:
            raise ValidationError("Box size seems too large (max 1000). Please check.")

    if tablets_per_box is not None:
        if tablets_per_box < 1:
            raise ValidationError("Tablets per box must be at least 1")
        if tablets_per_box > 10000:
            raise ValidationError("Tablets per box seems too large (max 10000). Please check.")
