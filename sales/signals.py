# sales/signals.py
from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from sales.models import Sale
from inventory.models import InventoryAudit

# --- Optional wallet imports (safe if wallet app isn't present yet) ---
try:
    from wallet.services import record_sale_commission, add_txn  # preferred path
    from wallet.models import WalletTransaction, TxnType, Ledger
except Exception:  # wallet not installed / migrated yet
    record_sale_commission = None
    add_txn = None
    WalletTransaction = None
    TxnType = None
    Ledger = None


@receiver(post_save, sender=Sale)
def mark_item_sold(sender, instance: Sale, created: bool, **kwargs):
    """
    Always keep the related inventory item in sync and write a lightweight audit.
    Runs on every save; safe to re-run if the sale is updated.
    """
    item = getattr(instance, "item", None)
    if item is not None:
        created_at = getattr(instance, "created_at", None) or timezone.now()
        # Set item.sold_at if missing or if this sale predates the current value
        if not item.sold_at or (created_at and item.sold_at < created_at):
            item.sold_at = created_at
        if item.status != "SOLD":
            item.status = "SOLD"
        item.save(update_fields=["sold_at", "status"])

        # Lightweight audit record
        price = getattr(instance, "price", None)
        commission_pct = getattr(instance, "commission_pct", None)
        location = getattr(instance, "location", "") or ""
        InventoryAudit.objects.create(
            item=item,
            action="SOLD",
            by_user=getattr(instance, "agent", None),
            details=f"Sold at {location} for MK{price} (commission {commission_pct}%).",
        )

    # On creation only, attempt to post commission to the agent's Wallet
    if created:
        _post_wallet_commission(instance)


def _post_wallet_commission(sale: Sale) -> None:
    """
    Posts a commission transaction into the agent's wallet.
    Prefers wallet.services.record_sale_commission (idempotent via 'created'),
    falls back to local computation if wallet.services isn't available.
    """
    # If wallet service is available, use it (it already guards on 'created')
    if record_sale_commission is not None:
        try:
            record_sale_commission(sale, created=True)
            return
        except Exception:
            # fall through to local path
            pass

    # Local fallback: only proceed if minimal pieces exist
    if add_txn is None or TxnType is None or sale.agent is None:
        return

    # Idempotency guard: don't double-post if a txn with this reference exists
    ref = f"SALE-{sale.pk}"
    try:
        if WalletTransaction is not None and WalletTransaction.objects.filter(
            agent=sale.agent, type=TxnType.COMMISSION, reference=ref
        ).exists():
            return
    except Exception:
        # If the table doesn't exist yet, just skip quietly
        return

    # Compute commission
    # Priority: explicit commission_pct (as percent) -> commission_rate (0..1) -> default
    default_rate = getattr(settings, "SALES_DEFAULT_COMMISSION_RATE", Decimal("0.03"))
    price = getattr(sale, "price", None) or getattr(sale, "amount", None) or Decimal("0")
    pct = getattr(sale, "commission_pct", None)
    rate_field = getattr(sale, "commission_rate", None)

    try:
        if pct is not None:
            rate = (Decimal(str(pct)) / Decimal("100"))
        elif rate_field is not None:
            rate = Decimal(str(rate_field))
        else:
            rate = Decimal(default_rate)
    except Exception:
        rate = Decimal(default_rate)

    commission = (Decimal(str(price)) * rate).quantize(Decimal("0.01"))

    if commission <= 0:
        return

    eff_date = getattr(sale, "date", None)
    # If sale.date is a datetime, prefer its date(); else, use created_at or today
    if hasattr(eff_date, "date"):
        eff_date = eff_date.date()
    if eff_date is None:
        eff_date = getattr(sale, "created_at", None)
        if hasattr(eff_date, "date"):
            eff_date = eff_date.date()
    if eff_date is None:
        eff_date = timezone.now().date()

    note = f"Commission for Sale #{sale.pk} at {getattr(sale, 'location', '') or ''}"
    try:
        add_txn(
            agent=sale.agent,
            amount=commission,
            type=TxnType.COMMISSION,
            note=note,
            reference=ref,
            effective_date=eff_date,
            created_by=None,
            meta={"sale_id": sale.pk, "rate": str(rate)},
            ledger=Ledger.AGENT,
        )
    except Exception:
        # Silent fail—wallet may not be fully set up yet
        return
