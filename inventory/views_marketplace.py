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

import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from inventory.models_marketplace import (
    ListingStatus,
    MarketplaceEnquiry,
    MarketplaceListing,
    MarketplaceListingImage,
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
    """
    vertical_filter = request.GET.get("vertical", "").strip()
    search_q = request.GET.get("q", "").strip()

    listings_qs = (
        MarketplaceListing.objects
        .filter(status=ListingStatus.LIVE)
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
        MarketplaceListing.objects
        .filter(status=ListingStatus.LIVE)
        .exclude(vertical="")
        .values_list("vertical", flat=True)
        .distinct()
        .order_by("vertical")
    )

    # Get businesses with live listings (for featured section)
    from django.db.models import Count
    featured_businesses = (
        Business.objects
        .filter(
            marketplace_listings__status=ListingStatus.LIVE,
            status="ACTIVE",
        )
        .annotate(listing_count=Count("marketplace_listings"))
        .order_by("-listing_count")[:12]
    )

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
            "vertical_config": vertical_config,
            "hide_nav": True,
        },
    )


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
        messages.success(
            request,
            f"Your enquiry has been sent to {listing.business.name}. They will contact you soon!",
        )
    except Exception as e:
        log.exception("Enquiry creation failed: %s", e)
        messages.error(request, "Could not submit enquiry. Please try again.")

    return redirect(request.META.get("HTTP_REFERER", "/marketplace/"))


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
        },
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
