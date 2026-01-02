"""
PHASE 4: Price Correction Services
Safe, audited price corrections for managers.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone


def edit_unsold_item_prices(
    *,
    item,
    new_order_price: Optional[Decimal] = None,
    new_selling_price: Optional[Decimal] = None,
    reason: str,
    edited_by,
    business,
) -> Dict[str, Any]:
    """
    Edit prices on an unsold inventory item (MANAGER ONLY).

    Args:
        item: InventoryItem instance
        new_order_price: New cost (None = no change)
        new_selling_price: New selling price (None = no change)
        reason: Why this edit is being made (required)
        edited_by: User making the change (must be manager)
        business: Business context

    Returns:
        Dict with success status and audit record

    Raises:
        ValueError: If item is sold or inputs invalid
        PermissionError: If user is not manager
    """
    from audit.models_price_audit import UnsoldPriceEdit
    from inventory.models import InventoryItem

    # Safety checks
    if item.status == "SOLD":
        raise ValueError("Cannot edit prices on sold items using this method. Use adjust_sold_item_price instead.")

    if new_order_price is None and new_selling_price is None:
        raise ValueError("Must specify at least one price to change")

    if new_order_price is not None and new_order_price < 0:
        raise ValueError("Order price cannot be negative")

    if new_selling_price is not None and new_selling_price < 0:
        raise ValueError("Selling price cannot be negative")

    if not reason or len(reason.strip()) < 5:
        raise ValueError("Reason must be at least 5 characters")

    # Check manager permission (caller should do this, but defense in depth)
    if not hasattr(edited_by, "profile"):
        raise PermissionError("User must have profile to edit prices")

    if not edited_by.profile.is_manager and not edited_by.is_staff:
        raise PermissionError("Only managers can edit prices")

    # Capture old values
    old_order = item.order_price
    old_selling = item.selling_price

    # Determine what changed
    if new_order_price is not None and new_selling_price is not None:
        field_changed = "both"
    elif new_order_price is not None:
        field_changed = "order_price"
    else:
        field_changed = "selling_price"

    with transaction.atomic():
        # Update item
        if new_order_price is not None:
            item.order_price = new_order_price
        if new_selling_price is not None:
            item.selling_price = new_selling_price
        item.save(
            update_fields=["order_price", "selling_price"]
            if field_changed == "both"
            else ["order_price"]
            if field_changed == "order_price"
            else ["selling_price"]
        )

        # Create audit record
        audit = UnsoldPriceEdit.objects.create(
            item=item,
            field_changed=field_changed,
            old_order_price=old_order,
            old_selling_price=old_selling,
            new_order_price=new_order_price if new_order_price is not None else old_order,
            new_selling_price=new_selling_price if new_selling_price is not None else old_selling,
            reason=reason.strip(),
            edited_by=edited_by,
            business=business,
        )

    return {
        "success": True,
        "audit_id": audit.id,
        "old_order_price": old_order,
        "old_selling_price": old_selling,
        "new_order_price": item.order_price,
        "new_selling_price": item.selling_price,
    }


def adjust_sold_item_price(
    *,
    sale,
    new_selling_price: Optional[Decimal] = None,
    new_cost_price: Optional[Decimal] = None,
    reason: str,
    adjusted_by,
    business,
) -> Dict[str, Any]:
    """
    Create price adjustment for a SOLD item (MANAGER ONLY).

    Uses adjustment layer - original Sale record is NOT modified.
    Reporting must use get_effective_sale_price() to see adjusted values.

    If commission already posted, creates compensating wallet transaction.

    Args:
        sale: Sale instance
        new_selling_price: Corrected selling price (None = no change)
        new_cost_price: Corrected cost (None = no change)
        reason: Why adjustment is needed (required)
        adjusted_by: Manager making adjustment
        business: Business context

    Returns:
        Dict with success status, adjustment record, commission delta

    Raises:
        ValueError: If inputs invalid
        PermissionError: If user not manager
    """
    from audit.models_price_audit import PriceAdjustment
    from wallet.models import WalletTransaction, TxnType, Ledger

    # Safety checks
    if new_selling_price is None and new_cost_price is None:
        raise ValueError("Must specify at least one price to adjust")

    if new_selling_price is not None and new_selling_price < 0:
        raise ValueError("Selling price cannot be negative")

    if new_cost_price is not None and new_cost_price < 0:
        raise ValueError("Cost price cannot be negative")

    if not reason or len(reason.strip()) < 10:
        raise ValueError("Reason must be at least 10 characters for sold item adjustments")

    # Manager permission check
    if not hasattr(adjusted_by, "profile"):
        raise PermissionError("User must have profile")

    if not adjusted_by.profile.is_manager and not adjusted_by.is_staff:
        raise PermissionError("Only managers can adjust sold item prices")

    # Get original values
    original_selling = sale.price
    original_cost = sale.item.order_price if sale.item else None

    # Determine adjustment type
    if new_selling_price is not None and new_cost_price is not None:
        adj_type = "BOTH"
    elif new_selling_price is not None:
        adj_type = "PRICE_CORRECTION"
    else:
        adj_type = "COST_CORRECTION"

    with transaction.atomic():
        # Create immutable adjustment record
        adjustment = PriceAdjustment.objects.create(
            sale=sale,
            adjustment_type=adj_type,
            original_selling_price=original_selling,
            original_cost_price=original_cost,
            new_selling_price=new_selling_price,
            new_cost_price=new_cost_price,
            reason=reason.strip(),
            adjusted_by=adjusted_by,
            business=business,
        )

        # Calculate commission impact
        commission_delta = Decimal("0.00")
        commission_txn_id = None

        if new_selling_price is not None and sale.agent:
            # Commission changes if selling price changes
            old_commission = (original_selling * sale.commission_pct) / Decimal("100.00")
            new_commission = (new_selling_price * sale.commission_pct) / Decimal("100.00")
            commission_delta = new_commission - old_commission

            if commission_delta != 0:
                # Create compensating wallet adjustment
                txn = WalletTransaction.objects.create(
                    ledger=Ledger.AGENT,
                    agent=sale.agent,
                    type=TxnType.ADJUSTMENT,
                    amount=abs(commission_delta),
                    note=f"Commission adjustment for Sale #{sale.id} price correction: {original_selling} → {new_selling_price}",
                    reference=f"ADJUSTMENT-{adjustment.id}",
                    effective_date=sale.sold_at,
                    created_by=adjusted_by,
                    business=business,
                    meta={
                        "adjustment_id": adjustment.id,
                        "sale_id": sale.id,
                        "original_price": str(original_selling),
                        "new_price": str(new_selling_price),
                        "commission_delta": str(commission_delta),
                    },
                )
                commission_txn_id = txn.id

                # Mark adjustment as having commission correction
                adjustment.commission_adjusted = True
                adjustment.commission_adjustment_txn_id = commission_txn_id
                adjustment.save(update_fields=["commission_adjusted", "commission_adjustment_txn_id"])

    return {
        "success": True,
        "adjustment_id": adjustment.id,
        "original_selling_price": original_selling,
        "new_selling_price": new_selling_price or original_selling,
        "original_cost_price": original_cost,
        "new_cost_price": new_cost_price or original_cost,
        "commission_delta": commission_delta,
        "commission_txn_id": commission_txn_id,
    }


def get_effective_sale_price(sale) -> Dict[str, Decimal]:
    """
    Get the effective (adjusted) prices for a sale.

    Reporting and dashboards MUST use this instead of raw sale.price
    to respect price adjustments.

    Returns:
        Dict with effective_selling_price, effective_cost_price, effective_profit
    """
    from audit.models_price_audit import PriceAdjustment

    # Get latest adjustment (if any)
    try:
        latest = PriceAdjustment.objects.filter(sale=sale).latest("adjusted_at")
        selling = latest.effective_selling_price
        cost = latest.effective_cost_price
    except PriceAdjustment.DoesNotExist:
        # No adjustments - use original values
        selling = sale.price
        cost = sale.item.order_price if sale.item else Decimal("0.00")

    profit = selling - cost if cost else selling

    return {
        "effective_selling_price": selling,
        "effective_cost_price": cost,
        "effective_profit": profit,
    }
