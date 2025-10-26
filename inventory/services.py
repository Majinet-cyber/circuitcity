# inventory/services.py
from django.db import transaction
from django.utils import timezone

def commission_amount(item):
    # adjust this to your rule (flat %, product field, etc.)
    rate = getattr(item.product, "commission_rate", None)
    if rate:
        return round((item.price or 0) * rate, 2)
    return 0

@transaction.atomic
def create_sale_and_wallet_for_item(item, sold_by):
    """
    Idempotently create Sale and WalletTxn when an InventoryItem becomes SOLD.
    """
    from sales.models import Sale  # import here to avoid tight coupling
    from inventory.models import WalletTxn  # adjust path if WalletTxn is elsewhere

    sale, created = Sale.objects.get_or_create(
        inventory_item=item,
        defaults=dict(
            product=item.product,
            price=item.price,
            cost=item.cost,
            sold_by=sold_by,
            sold_at=getattr(item, "sold_at", None) or timezone.now(),
            location=getattr(item, "location", None),
        ),
    )

    # Wallet credit (only once)
    ref = f"SALE:{item.pk}"
    if not WalletTxn.objects.filter(ref=ref).exists():
        WalletTxn.objects.create(
            ref=ref,
            # change 'agent' to your field (agent/user/staff); using sold_by
            agent=sold_by,
            amount=commission_amount(item),
            kind="CREDIT",  # or WalletTxn.Kind.CREDIT
            memo=f"Commission for {item.product} {getattr(item,'imei', '')}",
            happened_at=getattr(item, "sold_at", None) or timezone.now(),
        )
    return sale


