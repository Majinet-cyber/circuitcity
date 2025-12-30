# inventory/services/pharmacy_sale.py
"""
Pharmacy Sale Service - centralized business logic for all pharmacy operations.
Ensures all operations are atomic and safe against race conditions.

SIMPLIFICATION RULES:
- NO BARCODE required (barcode is ALWAYS optional)
- Enforce packaging rules (strip/box optional, never forced)
- Use shared conversion helper from pharmacy_config
- Support expiry/batch but NEVER block sales if missing
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import date
import logging
import uuid

from django.db import transaction, models
from django.db.models import F
from django.core.exceptions import ValidationError
from django.utils import timezone

from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.business_kinds import BusinessKind
from inventory.pharmacy_config import (
    to_base_units,
    validate_unit_for_category,
    get_default_base_unit,
    PharmacyCategory,
)

logger = logging.getLogger(__name__)


class OutOfStockError(Exception):
    """Raised when there's insufficient stock for a sale"""
    pass


@transaction.atomic
def stock_in_pharmacy(
    *,
    business,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
    category: str,
    user,
    quantity: int,
    unit: str,
    cost_price: Decimal,
    selling_price: Decimal,
    batch_number: Optional[str] = None,
    expiry_date: Optional[date] = None,
    barcode: Optional[str] = None,
    supplier: Optional[str] = None,
    location=None,
    notes: Optional[str] = None,
    # Packaging config (optional)
    strip_size: Optional[int] = None,
    box_size: Optional[int] = None,
    tablets_per_box: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Stock in pharmacy products with automatic batch creation.
    
    CRITICAL RULES:
    - Barcode is ALWAYS optional (no errors if missing)
    - Expiry date is optional (but recommended)
    - Batch number auto-generated if not provided
    - Can create new product OR add to existing
    - Packaging (strip/box) is optional
    
    Args:
        business: Business instance
        product_id: ID of existing MerchProduct (optional if creating new)
        product_name: Name for new product (required if product_id not provided)
        category: Pharmacy category (tablets_capsules, syrup, etc.)
        user: User performing the stock-in
        quantity: Quantity to add
        unit: Unit type ("tablet", "strip", "box", "bottle", etc.)
        cost_price: Cost per unit
        selling_price: Selling price per unit
        batch_number: Batch/lot number (auto-generated if not provided)
        expiry_date: Expiry date (optional)
        barcode: Product barcode (OPTIONAL - never required)
        supplier: Supplier name (optional)
        location: Location instance (optional)
        notes: Stock-in notes (optional)
        strip_size: Tablets per strip (optional)
        box_size: Strips per box (optional)
        tablets_per_box: Direct tablets per box (optional)
    
    Returns:
        Dict with:
            - ok: bool
            - message: str
            - product_id: int
            - batch_id: int
            - qty_base_units: int (base units added to stock)
            - error: str (if not ok)
    
    Raises:
        ValidationError: If validation fails
    """
    # Validate category
    if category not in PharmacyCategory.ALL:
        raise ValidationError(f"Invalid category: {category}")
    
    # Get or create product
    if product_id:
        # Lock existing product
        try:
            product = MerchProduct.objects.select_for_update().get(
                pk=product_id,
                business=business,
                kind=BusinessKind.PHARMACY,
                is_active=True
            )
        except MerchProduct.DoesNotExist:
            raise ValidationError("Product not found or not available")
    else:
        # Create new product
        if not product_name:
            raise ValidationError("Product name is required when creating new product")
        
        base_unit = get_default_base_unit(category)
        
        # Create product
        product = MerchProduct.objects.create(
            business=business,
            name=product_name,
            kind=BusinessKind.PHARMACY,
            category=category,
            base_unit=base_unit,
            cost_price=cost_price,
            selling_price=selling_price,
            barcode=barcode or "",  # Barcode is optional
            is_active=True,
            track_inventory=True,
            quantity_in_stock=0,
            # Packaging config (optional)
            strip_size=strip_size,
            box_size=box_size,
            tablets_per_box=tablets_per_box,
        )
        
        logger.info(f"Created new pharmacy product: {product.name} (ID: {product.id})")
    
    # Auto-generate batch number if not provided
    if not batch_number:
        batch_number = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    
    # Validate unit is allowed for this category
    has_strips = bool(strip_size or product.strip_size)
    has_boxes = bool(box_size or tablets_per_box or product.box_size or product.tablets_per_box)
    validate_unit_for_category(category, unit, has_strips=has_strips, has_boxes=has_boxes)
    
    # Create a temporary batch object for conversion (with packaging config)
    temp_batch = type('obj', (object,), {
        'category': category,
        'strip_size': strip_size or getattr(product, 'strip_size', None),
        'box_size': box_size or getattr(product, 'box_size', None),
        'tablets_per_box': tablets_per_box or getattr(product, 'tablets_per_box', None),
    })()
    
    # Convert to base units
    try:
        qty_base_units = to_base_units(quantity, unit, temp_batch)
    except ValidationError as e:
        raise ValidationError(f"Cannot stock in {product.name}: {str(e)}")
    
    # Calculate per-unit prices if stocking in by pack
    if unit.lower() in ("strip", "box"):
        # User entered price per strip/box, convert to per-base-unit price
        cost_per_base_unit = cost_price / Decimal(qty_base_units / quantity)
        selling_per_base_unit = selling_price / Decimal(qty_base_units / quantity)
    else:
        # User entered price per base unit
        cost_per_base_unit = cost_price
        selling_per_base_unit = selling_price
    
    # Create or update batch
    try:
        # Try to find existing batch with same batch_number and expiry_date
        batch = PharmacyBatch.objects.select_for_update().get(
            business=business,
            merch_product=product,
            batch_number=batch_number,
            expiry_date=expiry_date,
            is_archived=False
        )
        # Update existing batch
        batch.quantity += qty_base_units
        batch.cost_price = cost_per_base_unit  # Update cost
        batch.selling_price = selling_per_base_unit  # Update selling price
        batch.save()
        
        message = f"✅ Added to existing batch: {quantity} {unit}(s) = {qty_base_units} base units — {product.name}"
        
    except PharmacyBatch.DoesNotExist:
        # Create new batch
        batch = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number=batch_number,
            barcode=barcode or "",  # Batch-specific barcode (optional)
            expiry_date=expiry_date,
            quantity=qty_base_units,
            cost_price=cost_per_base_unit,
            selling_price=selling_per_base_unit,
            supplier=supplier or "",
            received_date=timezone.now().date(),
            is_archived=False,
        )
        
        message = f"✅ Stocked in: {quantity} {unit}(s) = {qty_base_units} base units — {product.name} (Batch: {batch_number})"
    
    # Update product total stock (aggregate across all batches)
    total_stock = PharmacyBatch.objects.filter(
        business=business,
        merch_product=product,
        is_archived=False
    ).aggregate(total=models.Sum('quantity'))['total'] or 0
    
    product.quantity_in_stock = total_stock
    
    # Update packaging config on product if provided
    if strip_size:
        product.strip_size = strip_size
    if box_size:
        product.box_size = box_size
    if tablets_per_box:
        product.tablets_per_box = tablets_per_box
    
    product.save()
    
    return {
        "ok": True,
        "message": message,
        "product_id": product.id,
        "batch_id": batch.id,
        "qty_base_units": qty_base_units,
    }


@transaction.atomic
def sell_pharmacy(
    *,
    business,
    batch_id: Optional[int] = None,
    barcode: Optional[str] = None,
    product_id: Optional[int] = None,
    user,
    quantity: int,
    unit: str,
    unit_price: Optional[Decimal] = None,
    payment_method: str = "CASH",
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    notes: Optional[str] = None,
    location=None,
) -> Dict[str, Any]:
    """
    Create a pharmacy sale atomically with FIFO batch selection.
    
    CRITICAL RULES:
    - Barcode is ALWAYS optional (can sell without barcode)
    - Must specify either batch_id OR product_id OR barcode
    - FIFO: sells from earliest expiry batch first
    - Atomic stock decrement with select_for_update
    - No race conditions possible
    
    Args:
        business: Business instance
        batch_id: ID of specific PharmacyBatch to sell from (optional)
        barcode: Product/batch barcode for lookup (optional)
        product_id: ID of MerchProduct (if batch_id not provided, uses FIFO)
        user: User making the sale
        quantity: Quantity to sell
        unit: Unit type ("tablet", "strip", "box", "bottle", etc.)
        unit_price: Price per unit (if None, uses batch selling_price)
        payment_method: Payment method ("CASH", "MOBILE_MONEY", "BANK", "CREDIT")
        customer_name: Customer name (optional)
        customer_phone: Customer phone (optional)
        notes: Sale notes (optional)
        location: Location instance (optional)
    
    Returns:
        Dict with:
            - ok: bool
            - sale_id: int (if ok)
            - message: str
            - error: str (if not ok)
    
    Raises:
        OutOfStockError: If insufficient stock
        ValidationError: If validation fails
    """
    from django.db import models
    
    # Find batch to sell from
    batch = None
    
    if batch_id:
        # Sell from specific batch
        try:
            batch = PharmacyBatch.objects.select_for_update().get(
                pk=batch_id,
                business=business,
                is_archived=False
            )
        except PharmacyBatch.DoesNotExist:
            raise ValidationError("Batch not found or not available")
    
    elif barcode:
        # Look up by barcode (check both product and batch barcodes)
        from inventory.utils_barcodes import normalize_barcode
        barcode_normalized = normalize_barcode(barcode)
        
        # Try batch barcode first
        batch = PharmacyBatch.objects.select_for_update().filter(
            business=business,
            barcode=barcode_normalized,
            is_archived=False,
            quantity__gt=0
        ).order_by('expiry_date', 'batch_number').first()
        
        # If not found, try product barcode with FIFO
        if not batch:
            product = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.PHARMACY,
                barcode=barcode_normalized,
                is_active=True
            ).first()
            
            if not product:
                raise ValidationError(f"No product or batch found with barcode: {barcode}")
            
            # FIFO: Get earliest expiring batch with stock
            batch = PharmacyBatch.objects.select_for_update().filter(
                business=business,
                merch_product=product,
                is_archived=False,
                quantity__gt=0
            ).order_by('expiry_date', 'batch_number').first()
    
    elif product_id:
        # FIFO: Sell from earliest expiring batch
        batch = PharmacyBatch.objects.select_for_update().filter(
            business=business,
            merch_product_id=product_id,
            is_archived=False,
            quantity__gt=0
        ).order_by('expiry_date', 'batch_number').first()
    
    else:
        raise ValidationError("Must provide batch_id, product_id, or barcode")
    
    if not batch:
        raise OutOfStockError("No batches with available stock found")
    
    # Get product info
    product = batch.merch_product
    category = getattr(product, 'category', PharmacyCategory.OTHER)
    
    # Validate unit is allowed
    has_strips = bool(getattr(product, 'strip_size', None))
    has_boxes = bool(getattr(product, 'box_size', None) or getattr(product, 'tablets_per_box', None))
    validate_unit_for_category(category, unit, has_strips=has_strips, has_boxes=has_boxes)
    
    # Convert to base units
    try:
        qty_base_units = to_base_units(quantity, unit, product)
    except ValidationError as e:
        raise ValidationError(f"Cannot sell {product.name}: {str(e)}")
    
    # Determine unit price
    if unit_price is None:
        unit_price = batch.selling_price
    
    if unit_price <= 0:
        raise ValidationError("Selling price must be greater than zero")
    
    # Calculate totals
    total_amount = Decimal(quantity) * unit_price
    unit_cost = batch.cost_price
    
    # CRITICAL: Atomic stock decrement with select_for_update
    # Check if we have enough stock
    if batch.quantity < qty_base_units:
        base_unit = get_default_base_unit(category)
        raise OutOfStockError(
            f"Insufficient stock in batch {batch.batch_number}: "
            f"Available: {batch.quantity} {base_unit}(s), "
            f"Requested: {qty_base_units} {base_unit}(s) ({quantity} {unit})"
        )
    
    # Decrement batch stock atomically
    updated = PharmacyBatch.objects.filter(
        pk=batch.pk,
        quantity__gte=qty_base_units
    ).update(
        quantity=F('quantity') - qty_base_units
    )
    
    if updated == 0:
        # Race condition: another request sold from this batch first
        batch.refresh_from_db()
        base_unit = get_default_base_unit(category)
        raise OutOfStockError(
            f"Insufficient stock (concurrent sale): {product.name}. "
            f"Available: {batch.quantity} {base_unit}(s), "
            f"Requested: {qty_base_units} {base_unit}(s)"
        )
    
    # Create sale record
    sale = PharmacySale.objects.create(
        business=business,
        batch=batch,
        quantity=quantity,  # Store quantity as entered by user
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_amount=total_amount,
        payment_method=payment_method,
        customer_name=customer_name or "",
        customer_phone=customer_phone or "",
        sold_by=user,
        notes=notes or "",
        sold_at=timezone.now(),
    )
    
    # Update product total stock (aggregate across all batches)
    total_stock = PharmacyBatch.objects.filter(
        business=business,
        merch_product=product,
        is_archived=False
    ).aggregate(total=models.Sum('quantity'))['total'] or 0
    
    product.quantity_in_stock = total_stock
    product.save(update_fields=['quantity_in_stock'])
    
    # Auto-archive batch if depleted
    batch.refresh_from_db()
    if batch.quantity == 0 and not batch.is_archived:
        batch.is_archived = True
        batch.save(update_fields=['is_archived'])
    
    return {
        "ok": True,
        "sale_id": sale.id,
        "message": f"✅ Sold {quantity} {unit}(s) of {product.name} (Batch: {batch.batch_number})",
    }

