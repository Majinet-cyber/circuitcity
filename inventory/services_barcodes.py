# inventory/services_barcodes.py
"""
Barcode services for stock items (clothing, shoes, etc.)

Provides validation and creation helpers for barcode-tracked inventory.
"""
from __future__ import annotations

from typing import List, Dict, Optional, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError

from inventory.models_stock_barcodes import InventoryBarcode


def validate_barcodes_for_qty(codes: List[str], qty: int, business) -> Tuple[bool, Optional[str]]:
    """
    Validate that barcode list matches quantity requirement.

    Args:
        codes: List of barcode strings
        qty: Required quantity
        business: Business instance

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if validation passes
        - error_message: None if valid, error string if invalid
    """
    if not codes:
        return False, "No barcodes provided"

    if len(codes) != qty:
        return False, f"Expected {qty} barcodes, but got {len(codes)}"

    # Check for duplicates in the list
    unique_codes = set(codes)
    if len(unique_codes) != len(codes):
        return False, "Duplicate barcodes found in the list"

    # Check for existing barcodes in database
    existing = InventoryBarcode.objects.filter(business=business, code__in=codes, is_archived=False).values_list(
        "code", flat=True
    )

    if existing:
        existing_list = ", ".join(existing)
        return False, f"Barcodes already exist in your inventory: {existing_list}"

    return True, None


@transaction.atomic
def create_barcodes(product, codes: List[str], business, location=None, user=None) -> List[InventoryBarcode]:
    """
    Create barcode records for a product.

    Args:
        product: MerchProduct instance
        codes: List of barcode strings (must be unique)
        business: Business instance
        location: Location instance (optional)
        user: User instance (optional, for created_by)

    Returns:
        List of created InventoryBarcode instances

    Raises:
        ValidationError: If validation fails
    """
    if not codes:
        return []

    # Validate codes
    is_valid, error_msg = validate_barcodes_for_qty(codes, len(codes), business)
    if not is_valid:
        raise ValidationError(error_msg)

    # Create barcode records
    barcodes = []
    for code in codes:
        barcode = InventoryBarcode.objects.create(
            business=business, product=product, location=location, code=code.strip(), created_by=user
        )
        barcodes.append(barcode)

    return barcodes


def get_barcodes_for_product(product, include_archived=False):
    """
    Get all barcodes for a product.

    Args:
        product: MerchProduct instance
        include_archived: If True, include archived barcodes

    Returns:
        QuerySet of InventoryBarcode instances
    """
    qs = InventoryBarcode.objects.filter(product=product)
    if not include_archived:
        qs = qs.filter(is_archived=False)
    return qs.order_by("-created_at")


def archive_barcodes_for_product(product, user=None):
    """
    Archive all barcodes for a product.

    Args:
        product: MerchProduct instance
        user: User instance (optional, for archived_by)

    Returns:
        Number of barcodes archived
    """
    from django.utils import timezone

    barcodes = InventoryBarcode.objects.filter(product=product, is_archived=False)

    count = barcodes.update(is_archived=True, archived_at=timezone.now(), archived_by=user)

    return count
