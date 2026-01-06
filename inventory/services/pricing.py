# inventory/services/pricing.py
"""
Global Pricing Service - Manager Price Edit Feature
Works across ALL verticals safely with full audit trail
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import MerchProduct
from inventory.models_price_audit import PriceChangeLog, PriceChangeScope
from inventory.models_verticals import CementSale, GrocerySale, LiquorSale

try:
    from inventory.models_pharmacy import PharmacySale
except ImportError:
    PharmacySale = None

try:
    from inventory.models_verticals import ClothingSale
except ImportError:
    ClothingSale = None


# Configuration: How many days back can we edit sale prices?
SALE_EDIT_WINDOW_DAYS = 7


def _validate_price(price: Decimal, field_name: str = "price") -> None:
    """Validate that price is a positive decimal"""
    if not isinstance(price, Decimal):
        raise ValidationError(f"{field_name} must be a Decimal")
    if price <= 0:
        raise ValidationError(f"{field_name} must be greater than 0")


def _check_manager_permission(user) -> None:
    """Check if user has manager permission"""
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required")

    # Check multiple permission sources
    is_manager = (
        user.is_staff
        or user.is_superuser
        or (hasattr(user, "profile") and getattr(user.profile, "is_manager", False))
        or user.groups.filter(name__in=["Manager", "Admin"]).exists()
    )

    if not is_manager:
        raise PermissionDenied("Manager permission required to edit prices")


def update_product_selling_price(
    *, business, product: MerchProduct, new_price: Decimal, user, reason: str, location=None
) -> Dict[str, Any]:
    """
    Update the current selling price of a product (affects future sales).

    Args:
        business: Business instance
        product: MerchProduct instance
        new_price: New selling price (Decimal)
        user: User making the change (must be manager)
        reason: Why is the price being changed (required)
        location: Optional location (for multi-location businesses)

    Returns:
        dict with old_price, new_price, and audit_log_id

    Raises:
        PermissionDenied: If user is not a manager
        ValidationError: If price is invalid or reason is missing
    """
    # Validate inputs
    _check_manager_permission(user)
    _validate_price(new_price, "new_price")

    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Reason must be at least 3 characters")

    if not product.is_active:
        raise ValidationError("Cannot edit prices for inactive products")

    old_price = product.selling_price or Decimal("0.00")

    # Don't allow setting the same price
    if old_price == new_price:
        raise ValidationError("New price must be different from current price")

    with transaction.atomic():
        # Update product
        product.selling_price = new_price
        product.save(update_fields=["selling_price"])

        # Create audit log
        audit_log = PriceChangeLog.objects.create(
            business=business,
            location=location,
            user=user,
            scope=PriceChangeScope.PRODUCT_PRICE,
            product=product,
            old_price=old_price,
            new_price=new_price,
            reason=reason.strip(),
        )

    return {
        "old_price": old_price,
        "new_price": new_price,
        "audit_log_id": audit_log.id,
        "product_id": product.id,
        "product_name": product.name,
    }


def _recompute_cement_sale_totals(sale: CementSale) -> None:
    """Recompute totals for a cement sale after unit price change"""
    sale.total_price = Decimal(sale.quantity) * sale.unit_price
    sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
    sale.save(update_fields=["total_price", "total_cost"])


def _recompute_liquor_sale_totals(sale: LiquorSale) -> None:
    """Recompute totals for a liquor sale after unit price change"""
    sale.total_price = Decimal(sale.quantity) * sale.unit_price
    sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
    sale.save(update_fields=["total_price", "total_cost"])


def _recompute_grocery_sale_totals(sale: GrocerySale) -> None:
    """Recompute totals for a grocery sale after unit price change"""
    sale.total_amount = Decimal(sale.quantity_sold) * sale.unit_price_sold
    sale.save(update_fields=["total_amount"])


def _recompute_pharmacy_sale_totals(sale) -> None:
    """Recompute totals for a pharmacy sale after unit price change"""
    if PharmacySale is None:
        return
    sale.total_amount = Decimal(sale.quantity) * sale.unit_price
    sale.save(update_fields=["total_amount"])


def _recompute_clothing_sale_totals(sale) -> None:
    """Recompute totals for a clothing sale after unit price change"""
    if ClothingSale is None:
        return
    sale.total_price = Decimal(sale.quantity) * sale.unit_price
    sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
    sale.save(update_fields=["total_price", "total_cost"])


def update_cement_sale_price(
    *, business, sale: CementSale, new_unit_price: Decimal, user, reason: str
) -> Dict[str, Any]:
    """
    Update the unit price on a cement sale (affects this sale's revenue/profit).

    Args:
        business: Business instance
        sale: CementSale instance
        new_unit_price: New unit selling price
        user: User making the change (must be manager)
        reason: Why is the price being changed (required)

    Returns:
        dict with old_price, new_price, audit_log_id, and updated totals

    Raises:
        PermissionDenied: If user is not a manager
        ValidationError: If price is invalid, reason is missing, or edit window expired
    """
    _check_manager_permission(user)
    _validate_price(new_unit_price, "new_unit_price")

    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Reason must be at least 3 characters")

    # Check if sale is voided
    if sale.is_void:
        raise ValidationError("Cannot edit prices on voided sales")

    # Check if sale is within edit window
    days_since_sale = (timezone.now() - sale.sold_at).days
    if days_since_sale > SALE_EDIT_WINDOW_DAYS:
        raise ValidationError(
            f"Cannot edit sales older than {SALE_EDIT_WINDOW_DAYS} days " f"(this sale is {days_since_sale} days old)"
        )

    old_unit_price = sale.unit_price

    if old_unit_price == new_unit_price:
        raise ValidationError("New price must be different from current price")

    with transaction.atomic():
        # Update sale unit price
        sale.unit_price = new_unit_price

        # Recompute totals
        _recompute_cement_sale_totals(sale)

        # Create audit log
        audit_log = PriceChangeLog.objects.create(
            business=business,
            user=user,
            scope=PriceChangeScope.SALE_LINE,
            cement_sale=sale,
            product=sale.product,
            old_price=old_unit_price,
            new_price=new_unit_price,
            reason=reason.strip(),
        )

    return {
        "old_unit_price": old_unit_price,
        "new_unit_price": new_unit_price,
        "old_total_price": old_unit_price * sale.quantity,
        "new_total_price": sale.total_price,
        "quantity": sale.quantity,
        "audit_log_id": audit_log.id,
        "sale_id": sale.id,
    }


def update_liquor_sale_price(
    *, business, sale: LiquorSale, new_unit_price: Decimal, user, reason: str
) -> Dict[str, Any]:
    """Update unit price on a liquor sale (similar to cement)"""
    _check_manager_permission(user)
    _validate_price(new_unit_price, "new_unit_price")

    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Reason must be at least 3 characters")

    # Check if sale is within edit window
    days_since_sale = (timezone.now() - sale.sold_at).days
    if days_since_sale > SALE_EDIT_WINDOW_DAYS:
        raise ValidationError(
            f"Cannot edit sales older than {SALE_EDIT_WINDOW_DAYS} days " f"(this sale is {days_since_sale} days old)"
        )

    old_unit_price = sale.unit_price

    if old_unit_price == new_unit_price:
        raise ValidationError("New price must be different from current price")

    with transaction.atomic():
        sale.unit_price = new_unit_price
        _recompute_liquor_sale_totals(sale)

        audit_log = PriceChangeLog.objects.create(
            business=business,
            user=user,
            scope=PriceChangeScope.SALE_LINE,
            liquor_sale=sale,
            product=sale.product,
            old_price=old_unit_price,
            new_price=new_unit_price,
            reason=reason.strip(),
        )

    return {
        "old_unit_price": old_unit_price,
        "new_unit_price": new_unit_price,
        "old_total_price": old_unit_price * sale.quantity,
        "new_total_price": sale.total_price,
        "quantity": sale.quantity,
        "audit_log_id": audit_log.id,
        "sale_id": sale.id,
    }


def update_grocery_sale_price(
    *, business, sale: GrocerySale, new_unit_price: Decimal, user, reason: str
) -> Dict[str, Any]:
    """Update unit price on a grocery sale"""
    _check_manager_permission(user)
    _validate_price(new_unit_price, "new_unit_price")

    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Reason must be at least 3 characters")

    days_since_sale = (timezone.now() - sale.sold_at).days
    if days_since_sale > SALE_EDIT_WINDOW_DAYS:
        raise ValidationError(
            f"Cannot edit sales older than {SALE_EDIT_WINDOW_DAYS} days " f"(this sale is {days_since_sale} days old)"
        )

    old_unit_price = sale.unit_price_sold

    if old_unit_price == new_unit_price:
        raise ValidationError("New price must be different from current price")

    with transaction.atomic():
        sale.unit_price_sold = new_unit_price
        _recompute_grocery_sale_totals(sale)

        audit_log = PriceChangeLog.objects.create(
            business=business,
            user=user,
            scope=PriceChangeScope.SALE_LINE,
            grocery_sale=sale,
            product=sale.product,
            old_price=old_unit_price,
            new_price=new_unit_price,
            reason=reason.strip(),
        )

    return {
        "old_unit_price": old_unit_price,
        "new_unit_price": new_unit_price,
        "old_total_amount": old_unit_price * sale.quantity_sold,
        "new_total_amount": sale.total_amount,
        "quantity": sale.quantity_sold,
        "audit_log_id": audit_log.id,
        "sale_id": sale.id,
    }


def get_price_change_history(business, *, product=None, user=None, limit=50):
    """
    Get price change history for a business.

    Args:
        business: Business instance
        product: Optional - filter by product
        user: Optional - filter by user who made changes
        limit: Max number of records to return

    Returns:
        QuerySet of PriceChangeLog entries
    """
    qs = PriceChangeLog.objects.filter(business=business)

    if product:
        qs = qs.filter(product=product)

    if user:
        qs = qs.filter(user=user)

    return qs.select_related("business", "user", "product", "location", "cement_sale", "liquor_sale", "grocery_sale")[
        :limit
    ]
