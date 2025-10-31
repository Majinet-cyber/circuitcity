# inventory/services.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone


def _to_decimal(val) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def commission_amount(item) -> Decimal:
    """
    Compute commission from the item's selling price and an optional product rate.

    Looks for:
      • item.selling_price (preferred), else item.price
      • item.product.commission_rate (0..1) if present
    """
    price = None
    if hasattr(item, "selling_price") and item.selling_price is not None:
        price = item.selling_price
    elif hasattr(item, "price") and item.price is not None:
        price = item.price

    price = _to_decimal(price or 0)

    rate = getattr(getattr(item, "product", None), "commission_rate", None)
    if rate is None:
        return Decimal("0")

    try:
        rate = Decimal(str(rate))
    except Exception:
        return Decimal("0")

    if rate <= 0:
        return Decimal("0")
    return (price * rate).quantize(Decimal("0.01"))


@transaction.atomic
def create_sale_and_wallet_for_item(item, sold_by):
    """
    Idempotently create a Sale and a WalletTxn when an InventoryItem becomes SOLD.

    Behavior:
      • If a Sale already exists for this item (or IMEI), reuse it.
      • Otherwise create a new Sale with best-effort field mapping.
      • Creates a WalletTxn with reason='COMMISSION' exactly once per sale+user+memo.
    """
    # Lazy imports to avoid tight coupling at import-time
    try:
        from sales.models import Sale  # type: ignore
    except Exception:
        # Sales app not available; nothing to do
        return None

    try:
        from inventory.models import WalletTxn  # type: ignore
    except Exception:
        WalletTxn = None  # type: ignore

    # Resolve Sale model fields defensively
    try:
        sale_fields = {f.name for f in Sale._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        sale_fields = set()

    sold_at = getattr(item, "sold_at", None) or timezone.now()

    # ---------- Build a query to find an existing Sale (idempotency) ----------
    sale_qs = Sale.objects.all()
    existing = None

    # Prefer a hard link via inventory_item if model supports it
    if "inventory_item" in sale_fields:
        try:
            existing = sale_qs.filter(inventory_item=item).first()
        except Exception:
            existing = None

    # Else, fall back to IMEI if both Sale and item expose it
    if existing is None and "imei" in sale_fields:
        imei = getattr(item, "imei", None)
        if imei:
            try:
                existing = sale_qs.filter(imei=imei).first()
            except Exception:
                existing = None

    # If still none, try a soft match on product + same day sold_at
    if existing is None and "product" in sale_fields and "sold_at" in sale_fields:
        try:
            existing = (
                sale_qs.filter(
                    product=getattr(item, "product", None),
                    sold_at__date=sold_at.date(),
                )
                .order_by("id")
                .first()
            )
        except Exception:
            existing = None

    # ---------- If found, reuse it; else prepare defaults & create ----------
    if existing:
        sale = existing
        created = False
    else:
        defaults = {}

        # FK fields (wrapped in try/except so missing FKs don't explode)
        if "product" in sale_fields:
            defaults["product"] = getattr(item, "product", None)

        # Monetary fields (price / selling_price / cost)
        if "price" in sale_fields:
            defaults["price"] = getattr(item, "selling_price", None) or getattr(item, "price", None)
        if "selling_price" in sale_fields:
            defaults["selling_price"] = getattr(item, "selling_price", None)
        for cost_field in ("cost", "cost_price", "order_cost"):
            if cost_field in sale_fields:
                defaults[cost_field] = getattr(item, "order_price", None) or getattr(
                    getattr(item, "product", None), "cost_price", None
                )
                break

        # Who sold
        for who_field in ("sold_by", "agent", "user", "staff"):
            if who_field in sale_fields:
                defaults[who_field] = sold_by
                break

        # When
        for when_field in ("sold_at", "happened_at", "created_at"):
            if when_field in sale_fields:
                defaults[when_field] = sold_at
                break

        # Where
        loc_val = getattr(item, "current_location", None) or getattr(item, "location", None)
        if "location" in sale_fields:
            defaults["location"] = loc_val
        for biz_field in ("business", "tenant", "company", "org"):
            if biz_field in sale_fields:
                defaults[biz_field] = getattr(item, "business", None)
                break

        # Identity helpers (if model supports IMEI / inventory link)
        if "imei" in sale_fields:
            defaults["imei"] = getattr(item, "imei", None)
        if "inventory_item" in sale_fields:
            defaults["inventory_item"] = item

        # Create the Sale (best-effort). If unique constraints exist,
        # this can still race—atomic() guarantees consistency in this tx.
        sale = Sale.objects.create(**defaults)
        created = True

    # ---------- Commission wallet entry (idempotent by memo+user) ----------
    if WalletTxn:
        try:
            amt = commission_amount(item)
            if amt and amt != Decimal("0"):
                # Stable memo for idempotency (per sale+user)
                memo = f"Commission SALE:{getattr(sale, 'pk', None) or 'NA'} ITEM:{getattr(item, 'pk', None) or 'NA'} IMEI:{getattr(item, 'imei', '')}"
                exists = WalletTxn.objects.filter(
                    user=sold_by,
                    reason="COMMISSION",
                    memo=memo,
                ).exists()
                if not exists:
                    WalletTxn.objects.create(
                        user=sold_by,
                        amount=amt,
                        reason="COMMISSION",
                        created_at=sold_at,
                        memo=memo,
                    )
        except Exception:
            # Never fail the sale flow due to wallet logging errors
            pass

    return sale
