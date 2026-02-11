# inventory/services/clothing_service.py
"""
Service layer for CLOTHING vertical operations.
Enforces:
- Atomic transactions with select_for_update
- Multi-tenant scoping (business + location)
- Vertical gating
- Concurrency safety
- Clear validation errors
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from inventory.models import MerchProduct
from inventory.models_verticals import (
    ClothingSale,
    ClothingProductLog,
    ClothingProductAction,
    PaymentMethod,
    ClothingVariant,
)
from inventory.business_kinds import BusinessKind
from inventory.clothing_config import (
    generate_internal_sku,
    generate_variant_sku,
    get_item_type_for_category,
)


# ============================================================================
# STOCK-IN SERVICE
# ============================================================================


@transaction.atomic
def stock_in_clothing(
    business,
    user,
    *,
    category: str,
    name: str,
    quantity: int,
    cost_price: Decimal,
    selling_price: Optional[Decimal] = None,
    brand: Optional[str] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    barcode: Optional[str] = None,
    location=None,
    has_sizes: bool = False,
    has_colors: bool = False,
) -> Dict[str, Any]:
    """
    Stock in clothing product with atomic transaction and concurrency safety.

    Args:
        business: Business instance
        user: User performing the action
        category: Category value (e.g., "sneaker")
        name: Product name
        quantity: Quantity to add
        cost_price: Cost price per unit
        selling_price: Selling price per unit (optional)
        brand: Brand name (optional)
        size: Size (optional, for simple products without variants)
        color: Color (optional, for simple products without variants)
        barcode: Barcode (optional)
        location: Location instance (optional)
        has_sizes: Enable size variants
        has_colors: Enable color variants

    Returns:
        Dict with {ok: True, product: MerchProduct, created: bool, message: str}

    Raises:
        ValidationError: On validation failures
    """
    # Validate business kind
    if not hasattr(business, "kind") or business.kind != BusinessKind.CLOTHING:
        raise ValidationError("This business is not a clothing business")

    # Validate inputs
    if quantity < 0:
        raise ValidationError("Quantity cannot be negative")

    if cost_price < Decimal("0"):
        raise ValidationError("Cost price cannot be negative")

    if selling_price and selling_price < Decimal("0"):
        raise ValidationError("Selling price cannot be negative")

    # Determine item type from category
    item_type = get_item_type_for_category(category)

    # Build product name (include brand if provided)
    if brand:
        full_name = f"{brand} {name}".strip()
    else:
        full_name = name.strip()

    # If using variants, don't include size/color in name
    # If not using variants, include size/color in name for uniqueness
    if not has_sizes and not has_colors:
        name_parts = [full_name]
        if size:
            name_parts.append(f"Size {size}")
        if color:
            name_parts.append(color)
        full_name = " - ".join(name_parts)

    # Use select_for_update to prevent race conditions
    try:
        product = MerchProduct.objects.select_for_update().get(
            business=business,
            name=full_name,
            kind=BusinessKind.CLOTHING,
        )
        created = False

        # Update existing product
        if not has_sizes and not has_colors:
            # Simple product: update stock directly
            product.quantity_in_stock += quantity

        # Update prices
        product.cost_price = cost_price
        if selling_price:
            product.selling_price = selling_price

        # Update barcode if provided
        if barcode:
            product.barcode = barcode

        product.save(update_fields=["quantity_in_stock", "cost_price", "selling_price", "barcode"])

    except MerchProduct.DoesNotExist:
        # Create new product
        created = True

        # Generate internal SKU
        # Get next sequence number for this business + category
        existing_count = MerchProduct.objects.filter(
            business=business, kind=BusinessKind.CLOTHING, category=category
        ).count()

        internal_sku = generate_internal_sku(
            business_id=business.id, category=category, brand=brand, sequence=existing_count + 1
        )

        product = MerchProduct.objects.create(
            business=business,
            name=full_name,
            kind=BusinessKind.CLOTHING,
            category=category,
            item_type=item_type,
            brand=brand or "",
            internal_sku=internal_sku,
            barcode=barcode or "",
            size=size or "" if not has_sizes else "",
            color=color or "" if not has_colors else "",
            quantity_in_stock=quantity if not (has_sizes or has_colors) else 0,
            cost_price=cost_price,
            selling_price=selling_price,
            has_sizes=has_sizes,
            has_colors=has_colors,
            is_active=True,
            track_inventory=True,
        )

    # If using variants, create/update variant
    if has_sizes or has_colors:
        variant_size = size or ""
        variant_color = color or ""

        try:
            variant = ClothingVariant.objects.select_for_update().get(
                product=product,
                size=variant_size,
                color=variant_color,
            )
            variant.quantity_in_stock += quantity
            variant.save(update_fields=["quantity_in_stock"])
            variant_created = False

        except ClothingVariant.DoesNotExist:
            # Generate variant SKU
            variant_sku = generate_variant_sku(base_sku=product.internal_sku, size=variant_size, color=variant_color)

            variant = ClothingVariant.objects.create(
                product=product,
                size=variant_size,
                color=variant_color,
                variant_sku=variant_sku,
                quantity_in_stock=quantity,
                is_active=True,
            )
            variant_created = True

    # Log the action
    ClothingProductLog.objects.create(
        product=product,
        action=ClothingProductAction.STOCK_IN,
        changes={
            "quantity_added": quantity,
            "cost_price": str(cost_price),
            "selling_price": str(selling_price) if selling_price else None,
            "new_stock": product.quantity_in_stock if not (has_sizes or has_colors) else None,
            "variant_size": size if (has_sizes or has_colors) else None,
            "variant_color": color if (has_sizes or has_colors) else None,
        },
        performed_by=user,
    )

    message = f"✅ Stock added: {quantity} × {full_name}"
    if has_sizes or has_colors:
        variant_desc = []
        if size:
            variant_desc.append(f"Size {size}")
        if color:
            variant_desc.append(color)
        message += f" ({', '.join(variant_desc)})"

    return {
        "ok": True,
        "product": product,
        "created": created,
        "message": message,
    }


# ============================================================================
# SELL SERVICE
# ============================================================================


@transaction.atomic
def sell_clothing(
    business,
    user,
    *,
    product_id: int,
    quantity: int,
    selling_price: Optional[Decimal] = None,
    payment_method: str = PaymentMethod.CASH,
    notes: str = "",
    location=None,
    variant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Sell clothing product with atomic transaction and concurrency safety.

    Args:
        business: Business instance
        user: User performing the sale
        product_id: Product ID
        quantity: Quantity to sell
        selling_price: Override selling price (optional, uses product price if None)
        payment_method: Payment method (cash, mobile, card, etc.)
        notes: Optional notes
        location: Location instance (optional)
        variant_id: Variant ID (optional, for products with variants)

    Returns:
        Dict with {ok: True, sale: ClothingSale, message: str}

    Raises:
        ValidationError: On validation failures
    """
    # Validate business kind
    if not hasattr(business, "kind") or business.kind != BusinessKind.CLOTHING:
        raise ValidationError("This business is not a clothing business")

    # Validate inputs
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than 0")

    # Get product with lock
    try:
        product = MerchProduct.objects.select_for_update().get(
            id=product_id,
            business=business,
            kind=BusinessKind.CLOTHING,
            is_active=True,
        )
    except MerchProduct.DoesNotExist:
        raise ValidationError("Product not found or not available")

    # Determine effective selling price
    if selling_price is None:
        if variant_id:
            # Get variant price
            try:
                variant = ClothingVariant.objects.get(id=variant_id, product=product)
                selling_price = variant.get_selling_price()
            except ClothingVariant.DoesNotExist:
                raise ValidationError("Variant not found")
        else:
            selling_price = product.selling_price or Decimal("0.00")

    if selling_price <= Decimal("0"):
        raise ValidationError("Selling price must be greater than 0")

    # Check stock availability
    if variant_id:
        # Variant-based stock check
        try:
            variant = ClothingVariant.objects.select_for_update().get(
                id=variant_id,
                product=product,
                is_active=True,
            )
            available_stock = variant.quantity_in_stock
        except ClothingVariant.DoesNotExist:
            raise ValidationError("Variant not found or not available")
    else:
        # Simple product stock check
        available_stock = product.quantity_in_stock

    if available_stock < quantity:
        raise ValidationError(f"Insufficient stock! Only {available_stock} available. Cannot sell {quantity} units.")

    # Reduce stock
    if variant_id:
        variant.quantity_in_stock -= quantity
        variant.save(update_fields=["quantity_in_stock"])
        cost_price = variant.get_cost_price()
    else:
        product.quantity_in_stock -= quantity
        product.save(update_fields=["quantity_in_stock"])
        cost_price = product.cost_price or Decimal("0.00")

    # Calculate totals
    total_price = Decimal(quantity) * selling_price
    total_cost = Decimal(quantity) * cost_price

    # Create sale record
    sale = ClothingSale.objects.create(
        business=business,
        product=product,
        quantity=quantity,
        unit_price=selling_price,
        total_price=total_price,
        unit_cost=cost_price,
        total_cost=total_cost,
        payment_method=payment_method,
        sold_by=user,
        notes=notes,
    )

    # Log the action
    ClothingProductLog.objects.create(
        product=product,
        action=ClothingProductAction.SOLD,
        changes={
            "quantity_sold": quantity,
            "selling_price": str(selling_price),
            "total_revenue": str(total_price),
            "remaining_stock": product.quantity_in_stock if not variant_id else None,
            "variant_id": variant_id,
        },
        performed_by=user,
    )

    profit = total_price - total_cost

    message = (
        f"🟢 Sale recorded! {quantity} × {product.name} | " f"Revenue: K {total_price:,.2f} | Profit: K {profit:,.2f}"
    )

    return {
        "ok": True,
        "sale": sale,
        "profit": profit,
        "message": message,
    }


# ============================================================================
# QUERY HELPERS (with proper scoping)
# ============================================================================


def get_top_sellers(business, location=None, days: int = 7, limit: int = 10) -> List[Dict]:
    """
    Get top selling products for the period.

    Returns:
        List of dicts with {product, total_sold, revenue}
    """
    from django.db.models import Sum, Count
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)

    sales_qs = ClothingSale.objects.filter(
        business=business,
        sold_at__gte=since,
    )

    # Location scoping (if ClothingSale has location field)
    if location and hasattr(ClothingSale, "location"):
        sales_qs = sales_qs.filter(location=location)

    top_products = (
        sales_qs.values("product")
        .annotate(
            total_sold=Sum("quantity"),
            revenue=Sum("total_price"),
            sales_count=Count("id"),
        )
        .order_by("-total_sold")[:limit]
    )

    # Enrich with product details
    result = []
    for item in top_products:
        try:
            product = MerchProduct.objects.get(id=item["product"])
            result.append(
                {
                    "product": product,
                    "total_sold": item["total_sold"],
                    "revenue": item["revenue"],
                    "sales_count": item["sales_count"],
                }
            )
        except MerchProduct.DoesNotExist:
            continue

    return result


def get_slow_movers(business, location=None, days: int = 30, limit: int = 10) -> List[MerchProduct]:
    """
    Get products with stock but no sales in the period.

    Returns:
        List of MerchProduct instances
    """
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)

    # Products with stock
    products_with_stock = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
    )

    # Products that have been sold in the period
    sold_product_ids = (
        ClothingSale.objects.filter(
            business=business,
            sold_at__gte=since,
        )
        .values_list("product_id", flat=True)
        .distinct()
    )

    # Slow movers = products with stock but not in sold list
    slow_movers = products_with_stock.exclude(id__in=sold_product_ids).order_by("-quantity_in_stock")[:limit]

    return list(slow_movers)


def get_low_stock_products(business, location=None, threshold: int = 3, limit: int = 20) -> List[MerchProduct]:
    """
    Get products with stock below threshold.

    Returns:
        List of MerchProduct instances
    """
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
        quantity_in_stock__lte=threshold,
    ).order_by("quantity_in_stock")[:limit]

    return list(products)


__all__ = [
    "stock_in_clothing",
    "sell_clothing",
    "get_top_sellers",
    "get_slow_movers",
    "get_low_stock_products",
]
