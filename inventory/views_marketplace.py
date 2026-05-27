# inventory/views_marketplace.py
"""
Marketplace views — public listing pages + workspace management UI.

Public routes (no login):
  marketplace_home       GET  /marketplace/
  business_public_page   GET  /marketplace/<slug>/
  listing_detail         GET  /marketplace/<slug>/<listing_slug>/
  submit_enquiry         POST /inventory/marketplace/enquiry/<id>/

Manager routes (login + business required):
  manage_listings        GET  /inventory/marketplace/manage/
  create_listing         GET/POST /inventory/marketplace/create/
  edit_listing           GET/POST /inventory/marketplace/edit/<id>/
  delete_listing         POST /inventory/marketplace/delete/<id>/
  toggle_listing_status  POST /inventory/marketplace/toggle-status/<id>/
  upload_listing_image   POST /inventory/marketplace/image/upload/<id>/
  view_enquiries         GET  /inventory/marketplace/enquiries/
  mark_enquiry_read      POST /inventory/marketplace/enquiry/<id>/read/
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Sum
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from inventory.models_marketplace import (
    ListingStatus,
    MarketplaceCommissionStatus,
    MarketplaceEnquiry,
    MarketplaceLead,
    MarketplaceLeadSource,
    MarketplaceLeadStatus,
    MarketplaceListing,
    MarketplaceListingImage,
    MarketplaceOrder,
    MarketplaceOrderStatus,
    MarketplaceStorefrontProfile,
)
from inventory.services import marketplace_checkout
from inventory.services.marketplace_leads import (
    contact_redirect_url,
    create_quote_request_lead,
    mark_lead_outcome,
    money_decimal,
    record_contact_click_lead,
    source_from_click_kind,
)
from tenants.decorators import require_business
from tenants.models import Business
from tenants.utils import get_active_business as _get_active_business


def _biz(request) -> "Business | None":
    """
    Resolve the active business from request — works regardless of which
    middleware/decorator populated the attribute.
    Order: request.business (middleware) → request.active_business (legacy) → util lookup.
    """
    return (
        getattr(request, "business", None)
        or getattr(request, "active_business", None)
        or _get_active_business(request)
    )

log = logging.getLogger(__name__)


def _empty_order_metrics() -> dict:
    return {
        "total": 0,
        "paid": 0,
        "pending": 0,
        "failed": 0,
        "gross_sales": Decimal("0.00"),
        "seller_earnings": Decimal("0.00"),
    }


def _seller_order_summary(business):
    """Return seller order stats without taking down listing management during migration gaps."""
    try:
        order_qs = MarketplaceOrder.objects.filter(seller_business=business)
        paid_qs = order_qs.filter(payment_status=MarketplaceOrderStatus.PAID)
        return {
            "total_orders": order_qs.count(),
            "paid_orders": paid_qs.count(),
            "gross_sales": paid_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00"),
            "seller_earnings": paid_qs.aggregate(total=Sum("seller_net_earnings"))["total"] or Decimal("0.00"),
            "recent_orders": list(order_qs.select_related("listing").order_by("-created_at")[:5]),
        }
    except (OperationalError, ProgrammingError) as exc:
        log.warning("Marketplace order summary unavailable; migration may be pending: %s", exc)
        return {
            "total_orders": 0,
            "paid_orders": 0,
            "gross_sales": Decimal("0.00"),
            "seller_earnings": Decimal("0.00"),
            "recent_orders": [],
        }


def _seller_orders_dataset(business, status_filter: str = ""):
    """Return scoped seller orders and metrics, falling back cleanly if the order table is absent."""
    try:
        orders_qs = (
            MarketplaceOrder.objects
            .filter(seller_business=business)
            .select_related("listing")
            .order_by("-created_at")
        )
        if status_filter:
            orders_qs = orders_qs.filter(payment_status=status_filter)
        base_qs = MarketplaceOrder.objects.filter(seller_business=business)
        paid_qs = base_qs.filter(payment_status=MarketplaceOrderStatus.PAID)
        metrics = {
            "total": base_qs.count(),
            "paid": paid_qs.count(),
            "pending": base_qs.filter(payment_status=MarketplaceOrderStatus.PENDING).count(),
            "failed": base_qs.filter(payment_status=MarketplaceOrderStatus.FAILED).count(),
            "gross_sales": paid_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00"),
            "seller_earnings": paid_qs.aggregate(total=Sum("seller_net_earnings"))["total"] or Decimal("0.00"),
        }
        return orders_qs, metrics
    except (OperationalError, ProgrammingError) as exc:
        log.warning("Marketplace orders page unavailable; migration may be pending: %s", exc)
        return [], _empty_order_metrics()


def _storefront_profile_or_none(business):
    try:
        return MarketplaceStorefrontProfile.objects.filter(business=business).first()
    except (OperationalError, ProgrammingError) as exc:
        log.warning("Marketplace storefront profile unavailable; migration may be pending: %s", exc)
        return None


_STOREFRONT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_STOREFRONT_CURRENCIES = ["MWK", "USD", "ZAR", "GBP", "EUR", "TZS", "ZMW"]


def _default_storefront_profile(business):
    return SimpleNamespace(
        logo=None,
        banner_image=None,
        owner=None,
        store_name=getattr(business, "name", "") or "",
        description="",
        phone=getattr(business, "phone", "") or "",
        email=getattr(business, "email", "") or "",
        whatsapp_number="",
        address=getattr(business, "address", "") or "",
        currency="MWK",
        opening_hours="",
        categories="",
        trust_badges=[],
        social_links={},
        verified_status=False,
        featured_status=False,
    )


def _storefront_profile_for_settings(business, user=None):
    try:
        profile, _ = MarketplaceStorefrontProfile.objects.get_or_create(
            business=business,
            defaults={
                "owner": user if getattr(user, "is_authenticated", False) else None,
                "store_name": getattr(business, "name", "") or "",
                "email": getattr(business, "email", "") or "",
                "currency": "MWK",
            },
        )
        return profile, True
    except (OperationalError, ProgrammingError) as exc:
        log.warning("Marketplace storefront settings unavailable; migration may be pending: %s", exc)
        return _default_storefront_profile(business), False


def _attach_storefront_profiles(businesses):
    attached = list(businesses)
    for business in attached:
        business.safe_storefront = _storefront_profile_or_none(business)
    return attached


def _assign_storefront_upload(profile, field_name: str, upload: UploadedFile | None) -> None:
    if not upload:
        return
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type and content_type not in _STOREFRONT_IMAGE_TYPES:
        raise ValueError("Storefront images must be JPG, PNG, or WebP files.")
    setattr(profile, field_name, upload)


def _storefront_currency(profile) -> str:
    currency = (getattr(profile, "currency", "") or "MWK").upper()
    return currency if currency in _STOREFRONT_CURRENCIES else "MWK"


def _normalize_external_url(value: str, service: str = "") -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if service in {"facebook", "instagram"}:
        handle = value.lstrip("@").strip("/")
        domain = "facebook.com" if service == "facebook" else "instagram.com"
        return f"https://{domain}/{handle}"
    return f"https://{value}"


def _normalize_whatsapp(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return ""
    return f"https://wa.me/{digits}"


def _storefront_social_links(profile) -> dict[str, str]:
    links = {"facebook": "", "instagram": "", "website": ""}
    raw = getattr(profile, "social_links", None)
    if isinstance(raw, dict):
        for key in links:
            links[key] = raw.get(key, "") or ""
    return links


def _storefront_contact_links(profile) -> dict[str, str]:
    social = _storefront_social_links(profile)
    email = getattr(profile, "display_email", "") or ""
    phone = getattr(profile, "display_phone", "") or ""
    whatsapp = getattr(profile, "whatsapp_number", "") or phone
    return {
        "website": _normalize_external_url(social.get("website", "")),
        "facebook": _normalize_external_url(social.get("facebook", ""), "facebook"),
        "instagram": _normalize_external_url(social.get("instagram", ""), "instagram"),
        "whatsapp": _normalize_whatsapp(whatsapp),
        "phone": phone,
        "email": email,
    }


def _collect_vertical_metadata_from_post(request: HttpRequest, business: Business) -> dict[str, str]:
    """Gather vertical_metadata keys from POST (meta_<field>)."""
    try:
        from inventory.marketplace_vertical_config import get_vertical_config

        cfg = get_vertical_config(getattr(business, "business_kind", "") or "") or {}
    except Exception:
        cfg = {}
    meta: dict[str, str] = {}
    for fn in cfg.get("listing_fields") or []:
        val = request.POST.get(f"meta_{fn}", "").strip()
        if val:
            meta[fn] = val
    return meta


def _vertical_meta_input_rows(business: Business, listing=None, form_data: dict | None = None):
    """Template-friendly rows for listing-specific metadata fields."""
    try:
        from inventory.marketplace_vertical_config import get_vertical_config

        cfg = get_vertical_config(getattr(business, "business_kind", "") or "") or {}
    except Exception:
        cfg = {}
    ml = cfg.get("metadata_labels") or {}
    merged_listing_meta = (listing.vertical_metadata if listing else {}) or {}
    fd = form_data or {}
    rows = []
    for fn in cfg.get("listing_fields") or []:
        fd_key = f"meta_{fn}"
        raw = fd.get(fd_key)
        val = merged_listing_meta.get(fn, "") if raw is None else raw
        rows.append(
            {
                "field": fn,
                "label": ml.get(fn, fn.replace("_", " ").title()),
                "value": val if val is not None else "",
            }
        )
    return rows


# =============================================================================
# PUBLIC VIEWS
# =============================================================================

@never_cache
def marketplace_home(request: HttpRequest) -> HttpResponse:
    """
    Top-level public marketplace: shows all live listings + live businesses.
    /marketplace/
    Must never depend on tenant-vertical session — safe when visited from any workspace.
    """
    vertical_filter = request.GET.get("vertical", "").strip()
    search_q = request.GET.get("q", "").strip()

    try:
        _public_listing_filter = {"status": ListingStatus.LIVE, "is_visible_publicly": True}
        listings_qs = (
            MarketplaceListing.objects
            .filter(**_public_listing_filter)
            .select_related("business")
            .prefetch_related("images")
        )
        if vertical_filter:
            listings_qs = listings_qs.filter(vertical=vertical_filter)
        if search_q:
            from django.db.models import Q

            listings_qs = listings_qs.filter(
                Q(title__icontains=search_q)
                | Q(description__icontains=search_q)
                | Q(business__name__icontains=search_q)
            )
        listings_qs = listings_qs.order_by("-created_at")

        paginator = Paginator(listings_qs, 24)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        available_verticals = (
            MarketplaceListing.objects.filter(**_public_listing_filter)
            .exclude(vertical="")
            .values_list("vertical", flat=True)
            .distinct()
            .order_by("vertical")
        )

        from django.db.models import Count

        featured_businesses = (
            Business.objects.filter(
                marketplace_listings__status=ListingStatus.LIVE,
                marketplace_listings__is_visible_publicly=True,
                status="ACTIVE",
            )
            .annotate(listing_count=Count("marketplace_listings"))
            .order_by("-listing_count")[:12]
        )
        featured_businesses = _attach_storefront_profiles(featured_businesses)
    except Exception as exc:
        log.exception("marketplace_home query failed: %s", exc)
        paginator = Paginator([], 24)
        page_obj = paginator.get_page(1)
        available_verticals = []
        featured_businesses = []

    return render(
        request,
        "marketplace/public_home.html",
        {
            "page_obj": page_obj,
            "vertical_filter": vertical_filter,
            "search_q": search_q,
            "available_verticals": available_verticals,
            "featured_businesses": featured_businesses,
            "hide_nav": True,
        },
    )


@never_cache
def marketplace_public(request: HttpRequest) -> HttpResponse:
    """Legacy alias for marketplace_home (backwards compat)."""
    return marketplace_home(request)


@never_cache
def business_public_page(request: HttpRequest, business_slug: str) -> HttpResponse:
    """
    Public-facing marketplace page for a specific business.
    /marketplace/<business_slug>/  (new clean URL)
    /inventory/public/<business_slug>/  (legacy)
    """
    business = get_object_or_404(Business, slug=business_slug, status="ACTIVE")
    storefront = _storefront_profile_or_none(business)

    listings_qs = (
        MarketplaceListing.objects
        .filter(business=business, status=ListingStatus.LIVE)
        .prefetch_related("images")
        .order_by("-created_at")
    )

    paginator = Paginator(listings_qs, 12)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    try:
        from inventory.marketplace_vertical_config import get_vertical_config
        vertical_config = get_vertical_config(business.business_kind)
    except Exception:
        vertical_config = {}

    return render(
        request,
        "marketplace/business_page.html",
        {
            "business": business,
            "storefront": storefront,
            "storefront_currency": _storefront_currency(storefront),
            "storefront_contact_links": _storefront_contact_links(storefront or _default_storefront_profile(business)),
            "page_obj": page_obj,
            "vertical_config": vertical_config,
            "hide_nav": True,
        },
    )


@never_cache
def listing_detail(
    request: HttpRequest, business_slug: str, listing_slug: str
) -> HttpResponse:
    """
    Single listing detail page with photo gallery.
    /marketplace/<business_slug>/<listing_slug>/
    """
    business = get_object_or_404(Business, slug=business_slug, status="ACTIVE")
    listing = get_object_or_404(
        MarketplaceListing,
        business=business,
        listing_slug=listing_slug,
        status=ListingStatus.LIVE,
    )

    images = listing.all_images
    storefront = _storefront_profile_or_none(business)
    other_listings = (
        MarketplaceListing.objects
        .filter(business=business, status=ListingStatus.LIVE)
        .exclude(pk=listing.pk)
        .order_by("-created_at")[:6]
    )

    try:
        from inventory.marketplace_vertical_config import get_vertical_config
        vertical_config = get_vertical_config(listing.vertical or business.business_kind)
    except Exception:
        vertical_config = {}

    return render(
        request,
        "marketplace/listing_detail.html",
        {
            "business": business,
            "listing": listing,
            "images": images,
            "other_listings": other_listings,
            "storefront": storefront,
            "vertical_config": vertical_config,
            "hide_nav": True,
        },
    )


@never_cache
def storefront_public_page(request: HttpRequest, business_slug: str) -> HttpResponse:
    """Explicit customer-facing storefront route."""
    return business_public_page(request, business_slug)


@never_cache
@require_http_methods(["GET", "POST"])
def marketplace_checkout_start(request: HttpRequest, business_slug: str, listing_slug: str) -> HttpResponse:
    """Public checkout form and PayChangu initiation for a live marketplace listing."""
    business = get_object_or_404(Business, slug=business_slug, status="ACTIVE")
    listing = get_object_or_404(
        MarketplaceListing,
        business=business,
        listing_slug=listing_slug,
        status=ListingStatus.LIVE,
    )
    if not marketplace_checkout.can_checkout_listing(listing):
        messages.error(request, "This listing is not available for checkout.")
        return redirect("marketplace:listing", business_slug=business.slug, listing_slug=listing.listing_slug)
    storefront = _storefront_profile_or_none(business)

    if request.method == "POST":
        try:
            order = marketplace_checkout.create_pending_order(
                listing=listing,
                buyer_name=request.POST.get("buyer_name", ""),
                buyer_phone=request.POST.get("buyer_phone", ""),
                buyer_email=request.POST.get("buyer_email", ""),
                delivery_notes=request.POST.get("delivery_notes", ""),
                quantity=request.POST.get("quantity", 1),
            )
            result = marketplace_checkout.initiate_paychangu_checkout(request, order)
            if result.get("status") == "success" and result.get("checkout_url"):
                return redirect(result["checkout_url"])
            messages.error(request, result.get("message", "Could not start payment."))
        except ValueError as exc:
            messages.error(request, str(exc))
        except (OperationalError, ProgrammingError):
            messages.error(request, "Checkout is being prepared. Please try again shortly.")
        except Exception as exc:
            log.exception("Marketplace checkout failed for listing %s: %s", listing.pk, exc)
            messages.error(request, "Could not start checkout. Please try again.")

    return render(
        request,
        "marketplace/checkout.html",
        {
            "business": business,
            "storefront": storefront,
            "listing": listing,
            "quantity": marketplace_checkout.clean_quantity(request.POST.get("quantity", 1)),
            "hide_nav": True,
        },
    )


@never_cache
def marketplace_checkout_return(request: HttpRequest, tx_ref: str) -> HttpResponse:
    try:
        order = get_object_or_404(
            MarketplaceOrder.objects.select_related("listing", "seller_business"),
            paychangu_reference=tx_ref,
        )
    except (OperationalError, ProgrammingError):
        messages.error(request, "Checkout records are being prepared. Please try again shortly.")
        return redirect("marketplace:home")
    return render(request, "marketplace/checkout_return.html", {"order": order, "hide_nav": True})


@csrf_exempt
@require_POST
def marketplace_checkout_webhook(request: HttpRequest) -> HttpResponse:
    """PayChangu webhook endpoint for marketplace checkout orders."""
    from billing import paychangu_service

    payload = request.body
    signature = (
        request.headers.get("Signature", "")
        or request.META.get("HTTP_SIGNATURE", "")
        or request.headers.get("X-Signature", "")
        or request.META.get("HTTP_X_SIGNATURE", "")
        or request.headers.get("X-PayChangu-Signature", "")
        or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
    ).strip()
    if not signature or not paychangu_service.verify_webhook_signature(payload, signature):
        return HttpResponse("Invalid signature", status=401)
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    tx_ref = (
        data.get("tx_ref")
        or data.get("reference")
        or data.get("transaction_id")
        or data.get("payment_reference")
        or data.get("transaction_reference")
    )
    if not tx_ref:
        return HttpResponse("OK", status=200)
    try:
        verify_result = paychangu_service.verify_payment(tx_ref)
        verified_status = (verify_result.get("status") or "").upper()
        event_status = (data.get("event") or data.get("status") or "").lower()
        if verified_status == "SUCCESS" or event_status in {"payment.success", "successful", "success", "completed"}:
            marketplace_checkout.mark_order_paid_from_paychangu(
                tx_ref,
                payload=verify_result.get("raw_response") or data,
                transaction_id=str(data.get("transaction_id") or data.get("charge_id") or ""),
            )
        elif verified_status == "FAILED" or event_status in {"payment.failed", "failed", "cancelled", "canceled"}:
            marketplace_checkout.mark_order_failed_from_paychangu(tx_ref, payload=verify_result.get("raw_response") or data)
    except Exception as exc:
        log.exception("Marketplace PayChangu webhook processing failed for %s: %s", tx_ref, exc)
    return HttpResponse("OK", status=200)


@require_http_methods(["POST"])
def submit_enquiry(request: HttpRequest, listing_id: int) -> HttpResponse:
    """
    Submit an enquiry about a listing. Public endpoint.
    """
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, status=ListingStatus.LIVE)

    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    name = request.POST.get("name", "").strip()
    msg = request.POST.get("message", "").strip()

    if not email:
        messages.error(request, "Email is required.")
        return redirect(request.META.get("HTTP_REFERER", "/marketplace/"))

    try:
        MarketplaceEnquiry.objects.create(
            listing=listing,
            business=listing.business,
            email=email,
            phone=phone,
            name=name,
            message=msg,
        )
        create_quote_request_lead(
            listing=listing,
            name=name,
            phone=phone,
            email=email,
            message=msg,
        )
        messages.success(
            request,
            f"Your enquiry has been sent to {listing.business.name}. They will contact you soon!",
        )
    except Exception as e:
        log.exception("Enquiry creation failed: %s", e)
        messages.error(request, "Could not submit enquiry. Please try again.")

    return redirect(request.META.get("HTTP_REFERER", "/marketplace/"))


@never_cache
def track_listing_contact(request: HttpRequest, listing_id: int, kind: str) -> HttpResponse:
    """
    Public contact-click tracker. Records a deduped lead and redirects to the
    intended contact target.
    """
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, status=ListingStatus.LIVE)
    source_type = source_from_click_kind(kind)
    if not source_type:
        raise Http404("Unknown contact type")

    try:
        record_contact_click_lead(request, listing, source_type)
    except Exception as exc:
        log.warning("Marketplace contact click tracking failed for listing %s: %s", listing.pk, exc)

    response = HttpResponse(status=302)
    response["Location"] = contact_redirect_url(listing, kind)
    return response


# =============================================================================
# MANAGER VIEWS
# =============================================================================

@login_required
@require_business
def manage_listings(request: HttpRequest) -> HttpResponse:
    """
    Manager marketplace dashboard — all listings with status tabs.
    """
    business = _biz(request)

    status_filter = request.GET.get("status", "all")

    listings_qs = MarketplaceListing.objects.filter(business=business).prefetch_related("images")
    counts = {
        "all": listings_qs.count(),
        "live": listings_qs.filter(status=ListingStatus.LIVE).count(),
        "draft": listings_qs.filter(status=ListingStatus.DRAFT).count(),
        "offline": listings_qs.filter(status=ListingStatus.OFFLINE).count(),
        "sold": listings_qs.filter(status=ListingStatus.SOLD).count(),
        "out_of_stock": listings_qs.filter(status=ListingStatus.OUT_OF_STOCK).count(),
    }

    if status_filter and status_filter != "all":
        listings_qs = listings_qs.filter(status=status_filter)

    listings_qs = listings_qs.order_by("-created_at")
    paginator = Paginator(listings_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    unread_count = MarketplaceEnquiry.objects.filter(business=business, is_read=False).count()
    lead_qs = MarketplaceLead.objects.filter(seller_business=business)
    lead_count = lead_qs.count()
    new_lead_count = lead_qs.filter(status=MarketplaceLeadStatus.NEW).count()
    won_lead_count = lead_qs.filter(status=MarketplaceLeadStatus.WON).count()
    order_summary = _seller_order_summary(business)
    storefront = _storefront_profile_or_none(business)

    try:
        from inventory.marketplace_vertical_config import get_vertical_config
        vertical_config = get_vertical_config(business.business_kind)
    except Exception:
        vertical_config = {}

    return render(
        request,
        "marketplace/manage/listings.html",
        {
            "page_obj": page_obj,
            "counts": counts,
            "status_filter": status_filter,
            "unread_count": unread_count,
            "business": business,
            "vertical_config": vertical_config,
            "ListingStatus": ListingStatus,
            "lead_count": lead_count,
            "new_lead_count": new_lead_count,
            "won_lead_count": won_lead_count,
            "storefront": storefront,
            "total_orders": order_summary["total_orders"],
            "paid_orders": order_summary["paid_orders"],
            "gross_sales": order_summary["gross_sales"],
            "seller_earnings": order_summary["seller_earnings"],
            "recent_orders": order_summary["recent_orders"],
            "show_search": False,
            "active_tab": "marketplace",
        },
    )


@login_required
def marketplace_media_diagnostics(request: HttpRequest, listing_id: int) -> JsonResponse:
    """Staff-only media diagnostics for production upload troubleshooting."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied

    listing = get_object_or_404(
        MarketplaceListing.objects.select_related("business").prefetch_related("images"),
        pk=listing_id,
    )

    def inspect_field(field_file):
        name = getattr(field_file, "name", "") or ""
        storage = getattr(field_file, "storage", None)
        data = {
            "name": name,
            "url": "",
            "storage_backend": f"{storage.__class__.__module__}.{storage.__class__.__name__}" if storage else "",
            "exists": None,
            "can_open": False,
            "error": "",
        }
        if not name:
            return data
        try:
            data["url"] = field_file.url
        except Exception as exc:
            data["error"] = f"url_error: {exc}"
        try:
            data["exists"] = bool(storage.exists(name)) if storage else None
        except Exception as exc:
            data["error"] = f"{data['error']} exists_error: {exc}".strip()
        try:
            with storage.open(name, "rb") as fh:
                fh.read(1)
            data["can_open"] = True
        except Exception as exc:
            data["error"] = f"{data['error']} open_error: {exc}".strip()
        return data

    return JsonResponse(
        {
            "listing_id": listing.id,
            "title": listing.title,
            "business_id": listing.business_id,
            "business_name": getattr(listing.business, "name", ""),
            "media_file": inspect_field(listing.media_file),
            "gallery_images": [
                {
                    "id": image.id,
                    "image": inspect_field(image.image),
                    "sort_order": image.sort_order,
                }
                for image in listing.images.all()
            ],
        }
    )


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def create_listing(request: HttpRequest) -> HttpResponse:
    """Create a new marketplace listing."""
    business = _biz(request)
    if not business:
        messages.error(request, "No active business found. Please select a business first.")
        return redirect("/")

    try:
        from inventory.marketplace_vertical_config import get_vertical_config
        vertical_config = get_vertical_config(business.business_kind) or {}
    except Exception:
        vertical_config = {}

    # form_data is ALWAYS a plain dict pre-populated with ALL expected template keys.
    # Django template filter args (e.g. form_data.title) raise VariableDoesNotExist
    # when the key is missing from a dict — pre-populated defaults prevent that 500.
    # GET → defaults dict; POST → copy of submitted data merged with defaults.
    _FORM_DEFAULTS: dict = {
        "title": "",
        "description": "",
        "price": "",
        "contact_phone": "",
        "contact_email": "",
        "location_text": "",
        "address": "",
        "status": ListingStatus.DRAFT,
        "vertical": getattr(business, "business_kind", "") or "",
    }
    form_data: dict = dict(_FORM_DEFAULTS)

    def _re_render(extra_form_data: dict | None = None):
        """Helper: re-render the create form, merging any extra POST data."""
        fd = extra_form_data or form_data
        return render(
            request,
            "marketplace/manage/create_edit.html",
            {
                "form_data": fd,
                "business": business,
                "vertical_config": vertical_config,
                "ListingStatus": ListingStatus,
                "editing": False,
                "vertical_meta_rows": _vertical_meta_input_rows(business, listing=None, form_data=fd),
            },
        )

    if request.method == "POST":
        # Merge POST data with defaults so ALL template keys are always present
        form_data = {**_FORM_DEFAULTS, **request.POST.dict()}

        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip()
        price_raw = form_data.get("price", "").strip()
        vertical = form_data.get("vertical", "").strip() or getattr(business, "business_kind", "") or ""
        contact_phone = form_data.get("contact_phone", "").strip()
        contact_email = form_data.get("contact_email", "").strip()
        address = form_data.get("address", "").strip()
        location_text = form_data.get("location_text", "").strip()
        status = form_data.get("status", ListingStatus.DRAFT)
        media_file = request.FILES.get("media_file")

        if not title:
            messages.error(request, "Title is required.")
            return _re_render(form_data)

        price = None
        if price_raw:
            try:
                price = Decimal(price_raw)
            except InvalidOperation:
                messages.error(request, "Invalid price — please enter a valid number.")
                return _re_render(form_data)

        vm = _collect_vertical_metadata_from_post(request, business)
        try:
            listing = MarketplaceListing.objects.create(
                business=business,
                title=title,
                description=description,
                price=price,
                vertical=vertical,
                media_file=media_file,
                contact_phone=contact_phone,
                contact_email=contact_email,
                address=address,
                location_text=location_text,
                status=status if status in dict(ListingStatus.choices) else ListingStatus.DRAFT,
                vertical_metadata=vm,
                created_by=request.user,
            )

            for img_file in request.FILES.getlist("images"):
                try:
                    MarketplaceListingImage.objects.create(listing=listing, image=img_file)
                except Exception as img_err:
                    log.warning("Listing image upload failed for listing %s: %s", listing.pk, img_err)

            messages.success(request, f"Listing '{title}' created successfully.")
            return redirect("inventory:manage_listings")
        except Exception as e:
            log.exception("Listing creation error for business %s: %s", business.pk, e)
            messages.error(request, f"Could not create listing: {e}")
            return _re_render(form_data)

    # GET — render with default form_data so ALL template keys are present.
    return _re_render(dict(_FORM_DEFAULTS))


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def edit_listing(request: HttpRequest, listing_id: int) -> HttpResponse:
    """Edit an existing listing."""
    business = _biz(request)
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, business=business)

    try:
        from inventory.marketplace_vertical_config import get_vertical_config
        vertical_config = get_vertical_config(business.business_kind) or {}
    except Exception:
        vertical_config = {}

    # Pre-populate form_data with listing values so all template keys are always present.
    _edit_defaults: dict = {
        "title": listing.title or "",
        "description": listing.description or "",
        "price": str(listing.price) if listing.price is not None else "",
        "contact_phone": listing.contact_phone or "",
        "contact_email": listing.contact_email or "",
        "location_text": listing.location_text or "",
        "address": listing.address or "",
        "status": listing.status or ListingStatus.DRAFT,
        "vertical": listing.vertical or getattr(business, "business_kind", "") or "",
    }

    def _re_render(fd: dict | None = None):
        merged_fd = {**_edit_defaults, **(fd or {})}
        return render(
            request,
            "marketplace/manage/create_edit.html",
            {
                "listing": listing,
                "form_data": merged_fd,
                "business": business,
                "vertical_config": vertical_config,
                "ListingStatus": ListingStatus,
                "editing": True,
                "vertical_meta_rows": _vertical_meta_input_rows(
                    business, listing=listing, form_data=merged_fd
                ),
            },
        )

    if request.method == "POST":
        form_data = {**_edit_defaults, **request.POST.dict()}
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip()
        price_raw = form_data.get("price", "").strip()
        contact_phone = form_data.get("contact_phone", "").strip()
        contact_email = form_data.get("contact_email", "").strip()
        address = form_data.get("address", "").strip()
        location_text = form_data.get("location_text", "").strip()
        status = form_data.get("status", listing.status)
        media_file = request.FILES.get("media_file")

        if not title:
            messages.error(request, "Title is required.")
            return _re_render(form_data)

        price = listing.price
        if price_raw:
            try:
                price = Decimal(price_raw)
            except InvalidOperation:
                messages.error(request, "Invalid price — please enter a valid number.")
                return _re_render(form_data)

        vm_post = _collect_vertical_metadata_from_post(request, business)
        try:
            prev_title = listing.title
            listing.title = title
            listing.description = description
            listing.price = price
            listing.contact_phone = contact_phone
            listing.contact_email = contact_email
            listing.address = address
            listing.location_text = location_text
            merged_vm = dict(listing.vertical_metadata or {})
            merged_vm.update(vm_post)
            listing.vertical_metadata = merged_vm
            if status in dict(ListingStatus.choices):
                listing.status = status
            if media_file:
                listing.media_file = media_file
            if title != prev_title:
                listing.listing_slug = ""
            listing.save()

            for img_file in request.FILES.getlist("images"):
                try:
                    MarketplaceListingImage.objects.create(listing=listing, image=img_file)
                except Exception as img_err:
                    log.warning("Edit-listing image upload failed: %s", img_err)

            messages.success(request, f"Listing '{title}' updated successfully.")
            return redirect("inventory:manage_listings")
        except Exception as e:
            log.exception("Listing update error for listing %s: %s", listing_id, e)
            messages.error(request, f"Could not update listing: {e}")
            return _re_render(form_data)

    # GET — render with listing defaults
    return _re_render(dict(_edit_defaults))


@login_required
@require_business
@require_POST
def delete_listing(request: HttpRequest, listing_id: int) -> HttpResponse:
    business = _biz(request)
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, business=business)
    title = listing.title
    listing.delete()
    messages.success(request, f"Listing '{title}' deleted.")
    return redirect("inventory:manage_listings")


@login_required
@require_business
@require_POST
def toggle_listing_status(request: HttpRequest, listing_id: int) -> HttpResponse:
    """
    Quick status toggle. POST with ?status=live|offline|sold|out_of_stock|draft
    Returns JSON for AJAX callers; redirects for normal form callers.
    """
    business = _biz(request)
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, business=business)

    new_status = request.POST.get("status", "").strip()
    valid_statuses = dict(ListingStatus.choices)

    if new_status in valid_statuses:
        listing.status = new_status
        listing.save(update_fields=["status", "updated_at"])

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "status": listing.status, "label": valid_statuses[new_status]})

        messages.success(request, f"Listing status set to '{valid_statuses[new_status]}'.")
    else:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Invalid status."}, status=400)
        messages.error(request, "Invalid status.")

    return redirect("inventory:manage_listings")


@login_required
@require_business
@require_POST
def upload_listing_image(request: HttpRequest, listing_id: int) -> HttpResponse:
    """AJAX endpoint to add images to a listing."""
    business = _biz(request)
    listing = get_object_or_404(MarketplaceListing, pk=listing_id, business=business)

    uploaded = []
    for img_file in request.FILES.getlist("images"):
        try:
            img = MarketplaceListingImage.objects.create(listing=listing, image=img_file)
            uploaded.append({"id": img.pk, "url": img.image.url})
        except Exception as e:
            log.warning("Image upload failed: %s", e)

    return JsonResponse({"ok": True, "uploaded": uploaded, "count": len(uploaded)})


@login_required
@require_business
def view_enquiries(request: HttpRequest) -> HttpResponse:
    """View all enquiries for this business."""
    business = _biz(request)
    enquiries_qs = (
        MarketplaceEnquiry.objects
        .filter(business=business)
        .select_related("listing")
        .order_by("-created_at")
    )
    paginator = Paginator(enquiries_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "inventory/view_enquiries.html", {"page_obj": page_obj, "business": business})


@login_required
@require_business
@require_POST
def mark_enquiry_read(request: HttpRequest, enquiry_id: int) -> HttpResponse:
    business = _biz(request)
    enquiry = get_object_or_404(MarketplaceEnquiry, pk=enquiry_id, business=business)
    enquiry.mark_as_read()
    return JsonResponse({"ok": True})


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def storefront_settings(request: HttpRequest) -> HttpResponse:
    """Seller-side storefront profile settings for the active business only."""
    business = _biz(request)
    profile, can_save = _storefront_profile_for_settings(business, request.user)
    if request.method == "POST":
        if not can_save:
            messages.error(request, "Storefront settings are being prepared. Run migrations, then try again.")
            return render(
                request,
                "marketplace/manage/storefront_settings.html",
                {
                    "business": business,
                    "profile": profile,
                    "show_search": False,
                    "active_tab": "marketplace_storefront",
                    "storefront_settings_unavailable": True,
                    "social_links": _storefront_social_links(profile),
                    "currency_choices": _STOREFRONT_CURRENCIES,
                    "selected_currency": _storefront_currency(profile),
                },
                status=503,
            )
        try:
            profile.store_name = request.POST.get("store_name", "").strip() or business.name
            profile.description = request.POST.get("description", "").strip()
            profile.phone = request.POST.get("phone", "").strip()
            profile.email = request.POST.get("email", "").strip()
            profile.whatsapp_number = request.POST.get("whatsapp_number", "").strip()
            profile.address = request.POST.get("address", "").strip()
            currency = (request.POST.get("currency") or getattr(profile, "currency", "") or "MWK").upper()
            profile.currency = currency if currency in _STOREFRONT_CURRENCIES else "MWK"
            profile.opening_hours = request.POST.get("opening_hours", "").strip()
            profile.categories = request.POST.get("categories", "").strip()
            profile.trust_badges = [
                part.strip()
                for part in request.POST.get("trust_badges", "").split(",")
                if part.strip()
            ]
            profile.social_links = {
                "facebook": request.POST.get("facebook", "").strip(),
                "instagram": request.POST.get("instagram", "").strip(),
                "website": request.POST.get("website", "").strip(),
            }
            _assign_storefront_upload(profile, "logo", request.FILES.get("logo"))
            _assign_storefront_upload(profile, "banner_image", request.FILES.get("banner_image"))
            if not profile.owner_id and request.user.is_authenticated:
                profile.owner = request.user
            profile.updated_by = request.user
            profile.save()
        except ValueError as exc:
            messages.error(request, str(exc))
        except (OperationalError, ProgrammingError):
            messages.error(request, "Storefront settings are being prepared. Run migrations, then try again.")
        else:
            messages.success(request, "Storefront profile saved.")
            return redirect("inventory:marketplace_storefront_settings")

    return render(
        request,
        "marketplace/manage/storefront_settings.html",
        {
            "business": business,
            "profile": profile,
            "show_search": False,
            "active_tab": "marketplace_storefront",
            "storefront_settings_unavailable": not can_save,
            "social_links": _storefront_social_links(profile),
            "currency_choices": _STOREFRONT_CURRENCIES,
            "selected_currency": _storefront_currency(profile),
        },
    )


@login_required
@require_business
def marketplace_orders(request: HttpRequest) -> HttpResponse:
    """Seller-side marketplace order list scoped to active business."""
    business = _biz(request)
    status_filter = request.GET.get("status", "").strip()
    orders_qs, metrics = _seller_orders_dataset(business, status_filter)
    paginator = Paginator(orders_qs, 20)
    return render(
        request,
        "marketplace/manage/orders.html",
        {
            "business": business,
            "page_obj": paginator.get_page(request.GET.get("page", 1)),
            "metrics": metrics,
            "status_filter": status_filter,
            "order_statuses": MarketplaceOrderStatus.choices,
            "show_search": False,
            "active_tab": "marketplace_orders",
        },
    )


@login_required
@require_business
def marketplace_leads(request: HttpRequest) -> HttpResponse:
    """Seller-side lead management for the active business."""
    business = _biz(request)
    status_filter = request.GET.get("status", "").strip()
    source_filter = request.GET.get("source", "").strip()
    commission_filter = request.GET.get("commission_status", "").strip()

    leads_qs = (
        MarketplaceLead.objects
        .filter(seller_business=business)
        .select_related("listing", "seller_business")
        .order_by("-created_at")
    )
    if status_filter:
        leads_qs = leads_qs.filter(status=status_filter)
    if source_filter:
        leads_qs = leads_qs.filter(source_type=source_filter)
    if commission_filter:
        leads_qs = leads_qs.filter(commission_status=commission_filter)

    base_qs = MarketplaceLead.objects.filter(seller_business=business)
    counts = {
        "all": base_qs.count(),
        "new": base_qs.filter(status=MarketplaceLeadStatus.NEW).count(),
        "contacted": base_qs.filter(status=MarketplaceLeadStatus.CONTACTED).count(),
        "negotiating": base_qs.filter(status=MarketplaceLeadStatus.NEGOTIATING).count(),
        "won": base_qs.filter(status=MarketplaceLeadStatus.WON).count(),
        "lost": base_qs.filter(status=MarketplaceLeadStatus.LOST).count(),
    }

    paginator = Paginator(leads_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(
        request,
        "marketplace/manage/leads.html",
        {
            "business": business,
            "page_obj": page_obj,
            "counts": counts,
            "status_filter": status_filter,
            "source_filter": source_filter,
            "commission_filter": commission_filter,
            "lead_statuses": MarketplaceLeadStatus.choices,
            "source_types": MarketplaceLeadSource.choices,
            "commission_statuses": MarketplaceCommissionStatus.choices,
            "show_search": False,
            "active_tab": "marketplace_leads",
        },
    )


@login_required
@require_business
@require_POST
def update_marketplace_lead(request: HttpRequest, lead_id: int) -> HttpResponse:
    """Seller action to update status, notes, and initial won deal amount."""
    business = _biz(request)
    lead = get_object_or_404(MarketplaceLead, pk=lead_id, seller_business=business)
    status = request.POST.get("status", lead.status)
    requested_deal_amount = request.POST.get("deal_amount")
    deal_amount_for_update = requested_deal_amount
    requested_amount = money_decimal(requested_deal_amount) if requested_deal_amount not in (None, "") else None
    if (
        lead.status == MarketplaceLeadStatus.WON
        and status == MarketplaceLeadStatus.WON
        and lead.deal_amount
        and requested_amount is not None
        and requested_amount != lead.deal_amount
    ):
        messages.error(request, "Only HQ can override the deal amount after a lead is won.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("inventory:marketplace_leads"))
    if status != MarketplaceLeadStatus.WON:
        deal_amount_for_update = None
    try:
        mark_lead_outcome(
            lead,
            status=status,
            deal_amount=deal_amount_for_update,
            notes=request.POST.get("notes", lead.notes),
        )
        messages.success(request, "Marketplace lead updated.")
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        log.exception("Lead update failed for %s: %s", lead.pk, exc)
        messages.error(request, "Could not update marketplace lead.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("inventory:marketplace_leads"))
