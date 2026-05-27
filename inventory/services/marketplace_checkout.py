from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.db import OperationalError, ProgrammingError
from django.urls import reverse
from django.utils import timezone

from billing import paychangu_service
from billing.models import PaymentTransaction
from inventory.models_marketplace import (
    ListingStatus,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
    MarketplaceListing,
    MarketplaceOrder,
    MarketplaceOrderStatus,
)
from inventory.services.marketplace_leads import DEFAULT_COMMISSION_PERCENTAGE, money_decimal, seller_business_for_listing


def can_checkout_listing(listing: MarketplaceListing) -> bool:
    return bool(listing and listing.status == ListingStatus.LIVE and listing.price and listing.price > 0)


def clean_quantity(value) -> int:
    try:
        qty = int(value or 1)
    except (TypeError, ValueError):
        qty = 1
    return max(1, min(qty, 99))


def create_pending_order(*, listing, buyer_name, buyer_phone, buyer_email="", delivery_notes="", quantity=1) -> MarketplaceOrder:
    if not can_checkout_listing(listing):
        raise ValueError("This listing is not available for checkout.")
    seller_business = seller_business_for_listing(listing)
    if not seller_business:
        raise ValueError("This listing is missing a valid seller business.")
    buyer_name = (buyer_name or "").strip()
    buyer_phone = (buyer_phone or "").strip()
    if not buyer_name:
        raise ValueError("Customer name is required.")
    if not buyer_phone:
        raise ValueError("Customer phone is required.")
    qty = clean_quantity(quantity)
    unit_price = money_decimal(listing.price)
    if unit_price is None or unit_price <= 0:
        raise ValueError("Listing price must be greater than zero.")

    tx_ref = f"mkt-{listing.pk}-{uuid.uuid4().hex[:12]}-{int(timezone.now().timestamp())}"
    return MarketplaceOrder.objects.create(
        listing=listing,
        seller_business=seller_business,
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        buyer_email=(buyer_email or "").strip(),
        delivery_notes=(delivery_notes or "").strip(),
        quantity=qty,
        unit_price=unit_price,
        total_amount=unit_price * Decimal(qty),
        platform_commission_percentage=DEFAULT_COMMISSION_PERCENTAGE,
        paychangu_reference=tx_ref,
    )


def initiate_paychangu_checkout(request, order: MarketplaceOrder) -> dict:
    """Create the shared PaymentTransaction record and request PayChangu checkout."""
    business = order.seller_business
    location = business.locations.first() if hasattr(business, "locations") else None
    tx_ref = order.paychangu_reference
    currency = getattr(business, "currency", "MWK") or "MWK"

    transaction, _ = PaymentTransaction.objects.get_or_create(
        provider="paychangu",
        tx_ref=tx_ref,
        defaults={
            "business": business,
            "location": location,
            "amount": order.total_amount,
            "currency": currency,
            "status": PaymentTransaction.Status.PENDING,
            "raw_init_payload": {"source": "marketplace_checkout", "order_id": order.pk},
        },
    )

    return_url = request.build_absolute_uri(reverse("marketplace:checkout_return", args=[tx_ref]))
    callback_url = request.build_absolute_uri(reverse("marketplace:checkout_webhook"))
    result = paychangu_service.create_checkout(
        business=business,
        location=location,
        amount=order.total_amount,
        currency=currency,
        tx_ref=tx_ref,
        return_url=return_url,
        callback_url=callback_url,
        meta={
            "source": "marketplace_checkout",
            "order_id": str(order.pk),
            "listing_id": str(order.listing_id),
            "seller_business_id": str(order.seller_business_id),
        },
        user_email=order.buyer_email or None,
        user_phone=order.buyer_phone,
        description=f"Marketplace checkout: {order.listing.title}",
    )
    if result.get("status") == "success":
        checkout_url = result.get("checkout_url", "")
        order.checkout_url = checkout_url
        order.save(update_fields=["checkout_url", "updated_at"])
        transaction.checkout_url = checkout_url
        transaction.raw_init_payload = result.get("raw_response", {})
        transaction.save(update_fields=["checkout_url", "raw_init_payload", "updated_at"])
    else:
        order.mark_failed(result.get("raw_response", {"message": result.get("message", "")}))
        transaction.mark_failed(result.get("raw_response", {}))
    return result


def mark_order_paid_from_paychangu(tx_ref: str, payload: dict | None = None, transaction_id: str = "") -> MarketplaceOrder | None:
    try:
        order = MarketplaceOrder.objects.select_related("listing", "seller_business").filter(paychangu_reference=tx_ref).first()
    except (OperationalError, ProgrammingError):
        return None
    if not order:
        return None
    order.mark_paid(payload or {}, transaction_id=transaction_id)
    PaymentTransaction.objects.filter(provider="paychangu", tx_ref=tx_ref).update(
        status=PaymentTransaction.Status.SUCCESS,
        raw_webhook_payload=payload or {},
    )
    lead, _ = MarketplaceLead.objects.get_or_create(
        listing=order.listing,
        seller_business=order.seller_business,
        source_type=MarketplaceLeadSource.MARKETPLACE_CHECKOUT,
        customer_phone=order.buyer_phone,
        defaults={
            "customer_name": order.buyer_name,
            "customer_email": order.buyer_email,
            "customer_message": order.delivery_notes,
            "status": MarketplaceLeadStatus.WON,
            "deal_amount": order.total_amount,
            "commission_percentage": order.platform_commission_percentage,
            "commission_amount": order.platform_commission_amount,
        },
    )
    if lead.status != MarketplaceLeadStatus.WON:
        lead.status = MarketplaceLeadStatus.WON
        lead.deal_amount = order.total_amount
        lead.commission_percentage = order.platform_commission_percentage
        lead.commission_amount = order.platform_commission_amount
        lead.save()
    if order.lead_id != lead.pk:
        order.lead = lead
        order.save(update_fields=["lead", "updated_at"])
    return order


def mark_order_failed_from_paychangu(tx_ref: str, payload: dict | None = None) -> MarketplaceOrder | None:
    try:
        order = MarketplaceOrder.objects.filter(paychangu_reference=tx_ref).first()
    except (OperationalError, ProgrammingError):
        return None
    if not order:
        return None
    order.mark_failed(payload or {})
    PaymentTransaction.objects.filter(provider="paychangu", tx_ref=tx_ref).update(
        status=PaymentTransaction.Status.FAILED,
        raw_webhook_payload=payload or {},
    )
    return order


def normalize_money(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
