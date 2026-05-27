from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.utils import timezone

from inventory.models_marketplace import (
    MarketplaceCommissionStatus,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
)


DEFAULT_COMMISSION_PERCENTAGE = Decimal("5.00")
CLICK_DEDUPE_WINDOW = timedelta(minutes=30)
PLACEHOLDER_BUSINESS_NAMES = {
    "marketplace",
    "marketplace leads",
    "marketplace lead agent",
    "marketplace module",
}


def is_placeholder_marketplace_business(business) -> bool:
    if not business:
        return True
    name = (getattr(business, "name", "") or "").strip().lower()
    slug = (getattr(business, "slug", "") or "").strip().lower()
    return name in PLACEHOLDER_BUSINESS_NAMES or slug in {
        "marketplace",
        "marketplace-leads",
        "marketplace-lead-agent",
        "marketplace-module",
    }


def seller_business_for_listing(listing):
    business = getattr(listing, "business", None)
    if is_placeholder_marketplace_business(business):
        return None
    return business


def money_decimal(value, default=None):
    if value in (None, ""):
        return default
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default
    if amount < 0:
        return default
    return amount.quantize(Decimal("0.01"))


def percent_decimal(value, default=DEFAULT_COMMISSION_PERCENTAGE):
    percent = money_decimal(value, default=default)
    return default if percent is None else percent


def format_mwk(value) -> str:
    amount = money_decimal(value, Decimal("0.00")) or Decimal("0.00")
    return f"MWK {amount:,.0f}"


def visitor_identity(request):
    session_key = getattr(request.session, "session_key", "") or ""
    if not session_key:
        try:
            request.session.save()
            session_key = request.session.session_key or ""
        except Exception:
            session_key = ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")) or None
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:255]
    return session_key, ip, ua


def source_from_click_kind(kind: str) -> str:
    mapping = {
        "whatsapp": MarketplaceLeadSource.WHATSAPP_CLICK,
        "phone": MarketplaceLeadSource.PHONE_CLICK,
        "email": MarketplaceLeadSource.EMAIL_CLICK,
    }
    return mapping.get((kind or "").strip().lower(), "")


def contact_redirect_url(listing, kind: str) -> str:
    kind = (kind or "").strip().lower()
    if kind == "phone" and listing.contact_phone:
        return f"tel:{listing.contact_phone}"
    if kind == "email" and listing.contact_email:
        return f"mailto:{listing.contact_email}?subject=Marketplace enquiry: {listing.title}"
    if kind == "whatsapp" and listing.contact_phone:
        digits = re.sub(r"\D+", "", listing.contact_phone)
        if digits:
            text = f"Hi, I'm interested in {listing.title} on Emajinet Marketplace."
            return f"https://wa.me/{digits}?text={quote(text)}"
    return f"/marketplace/{listing.business.slug}/{listing.listing_slug}/"


def create_quote_request_lead(*, listing, name="", phone="", email="", message="") -> MarketplaceLead:
    seller_business = seller_business_for_listing(listing)
    return MarketplaceLead.objects.create(
        listing=listing,
        seller_business=seller_business,
        customer_name=(name or "").strip(),
        customer_phone=(phone or "").strip(),
        customer_email=(email or "").strip(),
        customer_message=(message or "").strip(),
        source_type=MarketplaceLeadSource.QUOTE_REQUEST,
        status=MarketplaceLeadStatus.NEW,
        commission_percentage=DEFAULT_COMMISSION_PERCENTAGE,
    )


def record_contact_click_lead(request, listing, source_type: str) -> MarketplaceLead:
    seller_business = seller_business_for_listing(listing)
    session_key, ip, ua = visitor_identity(request)
    cutoff = timezone.now() - CLICK_DEDUPE_WINDOW
    qs = MarketplaceLead.objects.filter(
        listing=listing,
        seller_business=seller_business,
        source_type=source_type,
        created_at__gte=cutoff,
    )
    if session_key:
        qs = qs.filter(visitor_session_key=session_key)
    elif ip:
        qs = qs.filter(visitor_ip=ip, user_agent=ua)
    else:
        qs = qs.none()

    existing = qs.order_by("-created_at").first()
    if existing:
        return existing

    return MarketplaceLead.objects.create(
        listing=listing,
        seller_business=seller_business,
        source_type=source_type,
        status=MarketplaceLeadStatus.NEW,
        commission_percentage=DEFAULT_COMMISSION_PERCENTAGE,
        visitor_session_key=session_key,
        visitor_ip=ip,
        user_agent=ua,
    )


def mark_lead_outcome(
    lead: MarketplaceLead,
    *,
    status: str,
    deal_amount=None,
    commission_percentage=None,
    commission_amount=None,
    commission_status=None,
    notes: str | None = None,
    hq_notes: str | None = None,
) -> MarketplaceLead:
    valid_statuses = dict(MarketplaceLeadStatus.choices)
    if status not in valid_statuses:
        raise ValueError("Invalid lead status.")

    lead.status = status

    if notes is not None:
        lead.notes = notes.strip()
    if hq_notes is not None:
        lead.hq_notes = hq_notes.strip()

    if commission_percentage not in (None, ""):
        lead.commission_percentage = percent_decimal(commission_percentage)

    if deal_amount not in (None, ""):
        amount = money_decimal(deal_amount)
        if amount is None:
            raise ValueError("Deal amount must be a positive number.")
        lead.deal_amount = amount

    if status == MarketplaceLeadStatus.WON:
        if not lead.deal_amount or lead.deal_amount <= 0:
            raise ValueError("Deal amount is required when marking a lead as won.")
        if commission_status in dict(MarketplaceCommissionStatus.choices):
            lead.commission_status = commission_status
        elif lead.commission_status in ("", MarketplaceCommissionStatus.NOT_APPLICABLE):
            lead.commission_status = MarketplaceCommissionStatus.DUE
    elif status in {MarketplaceLeadStatus.LOST, MarketplaceLeadStatus.INVALID}:
        lead.commission_status = MarketplaceCommissionStatus.NOT_APPLICABLE

    if commission_amount not in (None, ""):
        amount = money_decimal(commission_amount)
        if amount is None:
            raise ValueError("Commission amount must be a positive number.")
        lead.commission_amount = amount
        lead.commission_amount_overridden = True
    else:
        lead.commission_amount_overridden = False

    lead.save()
    return lead
