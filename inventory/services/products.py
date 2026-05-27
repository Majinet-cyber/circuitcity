# inventory/services/products.py
"""
Shared product creation/update service for consistency across verticals.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.core.exceptions import ValidationError

from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind


@transaction.atomic
def create_or_update_clothing_product(
    *,
    business,
    name: str,
    barcode: Optional[str] = None,
    category: Optional[str] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    cost_price: Optional[Decimal] = None,
    selling_price: Optional[Decimal] = None,
    quantity: int = 0,
) -> MerchProduct:
    """
    Create or update a clothing product.

    Uses the same logic as clothing scan_in view for consistency.

    Args:
        business: Business instance
        name: Product name (required)
        barcode: Optional barcode (None if not provided)
        category: Optional category
        size: Optional size
        color: Optional color
        cost_price: Optional cost price
        selling_price: Optional selling price
        quantity: Initial stock quantity (default 0)

    Returns:
        MerchProduct instance (created or existing)

    Raises:
        ValidationError: If required fields are missing or invalid
    """
    if not name or not name.strip():
        raise ValidationError("Product name is required")

    # Normalize barcode (None if empty/whitespace)
    final_barcode = barcode.strip() if barcode and barcode.strip() else None

    # Get or create product
    # CRITICAL FIX: Set spec_label for clothing (use size, prevents NULL constraint)
    spec_label_value = size if size else ""
    if spec_label_value and not spec_label_value.startswith("Size "):
        spec_label_value = f"Size {spec_label_value}"

    product, created = MerchProduct.objects.get_or_create(
        business=business,
        name=name.strip(),
        kind=BusinessKind.CLOTHING,
        defaults={
            "category": category,
            "size": size,
            "color": color,
            "spec_label": spec_label_value,  # CRITICAL: Always set spec_label (prevents NULL constraint)
            "cost_price": cost_price,
            "selling_price": selling_price,
            "quantity_in_stock": quantity,
            "is_active": True,
            "track_inventory": True,
            "barcode": final_barcode,  # Explicitly set barcode (None if not provided)
        },
    )

    if not created:
        # Update existing product
        if final_barcode and not product.barcode:
            # Only update barcode if product doesn't have one
            product.barcode = final_barcode

        # Update prices if provided
        if cost_price is not None:
            product.cost_price = cost_price
        if selling_price is not None:
            product.selling_price = selling_price

        # Add to stock
        if quantity > 0:
            product.quantity_in_stock = (product.quantity_in_stock or 0) + quantity

        product.save()

    return product


@transaction.atomic
def create_or_update_generic_product(
    *,
    business,
    name: str,
    kind: BusinessKind,
    barcode: Optional[str] = None,
    category: Optional[str] = None,
    cost_price: Optional[Decimal] = None,
    selling_price: Optional[Decimal] = None,
    quantity: int = 0,
    base_unit: str = "pcs",
    **kwargs,
) -> MerchProduct:
    """
    Create or update a generic product (works for groceries, etc.).

    Args:
        business: Business instance
        name: Product name (required)
        kind: BusinessKind (required)
        barcode: Optional barcode (None if not provided)
        category: Optional category
        cost_price: Optional cost price
        selling_price: Optional selling price
        quantity: Initial stock quantity (default 0)
        base_unit: Base unit (default 'pcs')
        **kwargs: Additional fields to set on product

    Returns:
        MerchProduct instance (created or existing)

    Raises:
        ValidationError: If required fields are missing or invalid
    """
    if not name or not name.strip():
        raise ValidationError("Product name is required")

    # Normalize barcode (None if empty/whitespace)
    final_barcode = barcode.strip() if barcode and barcode.strip() else None

    # Build defaults dict
    # CRITICAL FIX: Ensure spec_label is always set (prevents NULL constraint)
    # If not provided in kwargs, default to empty string
    defaults = {
        "category": category,
        "spec_label": kwargs.pop("spec_label", ""),  # CRITICAL: Always set spec_label (prevents NULL constraint)
        "cost_price": cost_price,
        "selling_price": selling_price,
        "quantity_in_stock": quantity,
        "base_unit": base_unit,
        "is_active": True,
        "track_inventory": True,
        "barcode": final_barcode,
        **kwargs,  # Allow additional fields
    }

    # Get or create product
    product, created = MerchProduct.objects.get_or_create(
        business=business, name=name.strip(), kind=kind, defaults=defaults
    )

    if not created:
        # Update existing product
        if final_barcode and not product.barcode:
            product.barcode = final_barcode
            product.scan_required = True

        # Update prices if provided
        if cost_price is not None:
            product.cost_price = cost_price
        if selling_price is not None:
            product.selling_price = selling_price

        # Add to stock
        if quantity > 0:
            product.quantity_in_stock = (product.quantity_in_stock or 0) + quantity

        product.save()

    return product
