# inventory/verticals/car_dealer.py
"""
Car Dealer vertical: views for dashboard, stock in, sell, inventory list,
vehicle detail, photo management, and marketplace publishing.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from inventory.services.media_safety import object_image_url
from tenants.utils import require_business, get_active_business
from tenants.utils_roles import is_manager

log = logging.getLogger(__name__)


def _get_car_models():
    try:
        from inventory.models_car_dealer import CarMake, CarModel, CarDealerVehicle
        return CarMake, CarModel, CarDealerVehicle
    except ImportError:
        return None, None, None


def _get_image_model():
    try:
        from inventory.models_car_dealer import CarDealerVehicleImage
        return CarDealerVehicleImage
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def car_dealer_dashboard(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()

    now = timezone.now()
    today = now.date()

    stats = {
        "total": 0,
        "in_stock": 0,
        "sold_this_month": 0,
        "reserved": 0,
        "revenue_this_month": Decimal("0"),
        "cost_this_month": Decimal("0"),
        "profit_this_month": Decimal("0"),
        "avg_selling_price": Decimal("0"),
        "inventory_value": Decimal("0"),
        "inventory_cost_basis": Decimal("0"),
        "aging_30": 0,
        "aging_60": 0,
        "aging_90_plus": 0,
        "marketplace_live": 0,
        "low_photo_vehicles": 0,
    }
    recent_vehicles = []
    vehicles_by_make = []
    vehicles_by_fuel = []
    recent_sold = []

    if CarDealerVehicle:
        from django.db.models import Count, Sum

        qs = CarDealerVehicle.objects.filter(business=biz)
        stats["total"] = qs.count()

        in_stock_qs = qs.filter(status="in_stock")
        stats["in_stock"] = in_stock_qs.count()
        stats["reserved"] = qs.filter(status="reserved").count()

        # Revenue and sales this month
        sold_this_month = qs.filter(
            status="sold",
            sold_at__year=now.year,
            sold_at__month=now.month,
        )
        stats["sold_this_month"] = sold_this_month.count()
        stats["revenue_this_month"] = sum(
            (v.sale_price or v.selling_price or Decimal("0"))
            for v in sold_this_month
        )

        # Average selling price on current stock
        in_stock_prices = [v.selling_price for v in in_stock_qs if v.selling_price]
        if in_stock_prices:
            stats["avg_selling_price"] = sum(in_stock_prices) / len(in_stock_prices)

        stats["inventory_value"] = sum(in_stock_prices)

        in_stock_costs = [v.buying_price for v in in_stock_qs if v.buying_price]
        stats["inventory_cost_basis"] = sum(in_stock_costs) if in_stock_costs else Decimal("0")

        cost_this_month = sum(
            (v.buying_price or Decimal("0")) for v in sold_this_month
        )
        stats["cost_this_month"] = cost_this_month
        stats["profit_this_month"] = stats["revenue_this_month"] - cost_this_month

        # Stock aging
        from datetime import timedelta
        cutoff_30 = today - timedelta(days=30)
        cutoff_60 = today - timedelta(days=60)
        cutoff_90 = today - timedelta(days=90)
        stats["aging_30"] = in_stock_qs.filter(created_at__date__lte=cutoff_30, created_at__date__gt=cutoff_60).count()
        stats["aging_60"] = in_stock_qs.filter(created_at__date__lte=cutoff_60, created_at__date__gt=cutoff_90).count()
        stats["aging_90_plus"] = in_stock_qs.filter(created_at__date__lte=cutoff_90).count()

        # Marketplace live listings
        stats["marketplace_live"] = qs.filter(marketplace_listing__status="live").count()

        # Low-photo vehicles (no gallery images)
        CarDealerVehicleImage = _get_image_model()
        if CarDealerVehicleImage:
            vehicles_with_photos = (
                CarDealerVehicleImage.objects.filter(vehicle__business=biz)
                .values_list("vehicle_id", flat=True)
                .distinct()
            )
            stats["low_photo_vehicles"] = in_stock_qs.exclude(pk__in=vehicles_with_photos).count()

        # Vehicles by make
        vehicles_by_make = (
            in_stock_qs
            .values("model__make__name", "make_text")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        vehicles_by_fuel = (
            in_stock_qs
            .exclude(fuel_type="")
            .values("fuel_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        recent_vehicles = in_stock_qs.select_related("model__make", "make").prefetch_related("gallery_images").order_by("-created_at")[:12]

        recent_sold = (
            qs.filter(status="sold")
            .select_related("model__make", "make")
            .order_by("-sold_at")[:5]
        )

        total_profit = Decimal("0")
        for v in qs.filter(status="sold"):
            sp = v.sale_price or v.selling_price or Decimal("0")
            bp = v.buying_price or Decimal("0")
            total_profit += (sp - bp)

        monthly_revenue = []
        monthly_labels = []
        for months_ago in range(5, -1, -1):
            m_date = today.replace(day=1)
            for _ in range(months_ago):
                m_date = (m_date - timedelta(days=1)).replace(day=1)
            sold_in_month = qs.filter(
                status="sold",
                sold_at__year=m_date.year,
                sold_at__month=m_date.month,
            )
            rev = sum((v.sale_price or v.selling_price or Decimal("0")) for v in sold_in_month)
            monthly_revenue.append(float(rev))
            monthly_labels.append(m_date.strftime("%b %Y"))

        stats["total_profit"] = total_profit

        vehicles_by_body = (
            in_stock_qs
            .exclude(body_type="")
            .values("body_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        aged_vehicles = (
            in_stock_qs.filter(created_at__date__lte=cutoff_90)
            .select_related("model__make", "make")
            .order_by("created_at")[:5]
        )

    else:
        monthly_revenue = []
        monthly_labels = []
        vehicles_by_body = []
        aged_vehicles = []
        stats["total_profit"] = Decimal("0")

    return render(
        request,
        "car_dealer/dashboard.html",
        {
            "stats": stats,
            "recent_vehicles": recent_vehicles,
            "recent_sold": recent_sold,
            "vehicles_by_make": vehicles_by_make,
            "vehicles_by_fuel": vehicles_by_fuel,
            "vehicles_by_body": vehicles_by_body,
            "aged_vehicles": aged_vehicles,
            "monthly_revenue_json": json.dumps(monthly_revenue),
            "monthly_labels_json": json.dumps(monthly_labels),
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Vehicle list / inventory
# ---------------------------------------------------------------------------

@login_required
@require_business
def vehicle_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()

    status_filter = request.GET.get("status", "")
    search_q = request.GET.get("q", "").strip()
    make_filter = request.GET.get("make", "").strip()
    body_filter = request.GET.get("body_type", "").strip()

    vehicles = []
    counts = {}
    makes_for_filter = []
    if CarDealerVehicle:
        qs = CarDealerVehicle.objects.filter(business=biz).select_related("make", "model").prefetch_related("gallery_images")
        counts = {
            "all": qs.count(),
            "in_stock": qs.filter(status="in_stock").count(),
            "sold": qs.filter(status="sold").count(),
            "reserved": qs.filter(status="reserved").count(),
        }
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)
        if make_filter:
            from django.db.models import Q
            qs = qs.filter(Q(make__name__icontains=make_filter) | Q(make_text__icontains=make_filter))
        if body_filter:
            qs = qs.filter(body_type=body_filter)
        if search_q:
            from django.db.models import Q
            qs = qs.filter(
                Q(make__name__icontains=search_q)
                | Q(model__name__icontains=search_q)
                | Q(make_text__icontains=search_q)
                | Q(model_text__icontains=search_q)
                | Q(color__icontains=search_q)
                | Q(stock_ref__icontains=search_q)
                | Q(chassis_no__icontains=search_q)
            )
        vehicles = qs.order_by("-created_at")
        # Makes for filter bar
        CarMakeModel = CarMake
        if CarMakeModel:
            makes_for_filter = CarMakeModel.objects.order_by("name")

    return render(
        request,
        "car_dealer/vehicle_list.html",
        {
            "vehicles": vehicles,
            "counts": counts,
            "status_filter": status_filter,
            "search_q": search_q,
            "make_filter": make_filter,
            "body_filter": body_filter,
            "makes_for_filter": makes_for_filter,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Stock In / Add Vehicle
# ---------------------------------------------------------------------------

@login_required
@require_business
def stock_in_vehicle(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        messages.error(request, "Only managers can add vehicles.")
        return redirect("car_dealer:vehicle_list")

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    CarDealerVehicleImage = _get_image_model()
    makes = CarMake.objects.order_by("sort_order", "name") if CarMake else []
    popular_makes = CarMake.objects.filter(is_popular=True).order_by("sort_order", "name") if CarMake else []
    car_models = CarModel.objects.select_related("make").order_by("make__name", "name") if CarModel else []

    if request.method == "POST":
        data = request.POST
        try:
            make_id = data.get("make_id")
            model_id = data.get("model_id")
            make_obj = CarMake.objects.get(pk=make_id) if make_id and CarMake else None
            model_obj = CarModel.objects.get(pk=model_id) if model_id and CarModel else None

            buying_price = None
            selling_price = None
            try:
                bp = data.get("buying_price", "").strip()
                if bp:
                    buying_price = Decimal(bp)
            except (InvalidOperation, ValueError):
                pass
            try:
                sp = data.get("selling_price", "").strip()
                if sp:
                    selling_price = Decimal(sp)
            except (InvalidOperation, ValueError):
                pass

            year_str = data.get("year", "").strip()
            year = int(year_str) if year_str.isdigit() else None

            mileage_str = data.get("mileage", "").strip()
            mileage = int(mileage_str) if mileage_str.isdigit() else None

            vehicle = CarDealerVehicle.objects.create(
                business=biz,
                make=make_obj,
                model=model_obj,
                make_text=data.get("make_text", "").strip(),
                model_text=data.get("model_text", "").strip(),
                year=year,
                trim=data.get("trim", "").strip(),
                body_type=data.get("body_type", "").strip(),
                transmission=data.get("transmission", "").strip(),
                fuel_type=data.get("fuel_type", "").strip(),
                drivetrain=data.get("drivetrain", "").strip(),
                engine_size=data.get("engine_size", "").strip(),
                mileage=mileage,
                color=data.get("color", "").strip(),
                interior_color=data.get("interior_color", "").strip(),
                chassis_no=data.get("chassis_no", "").strip(),
                stock_ref=data.get("stock_ref", "").strip(),
                buying_price=buying_price,
                selling_price=selling_price,
                condition=data.get("condition", "used"),
                location_text=data.get("location_text", "").strip(),
                description=data.get("description", "").strip(),
                features_notes=data.get("features_notes", "").strip(),
                import_source_notes=data.get("import_source_notes", "").strip(),
                stocked_by=request.user,
                status="in_stock",
            )

            # Handle photo uploads
            if CarDealerVehicleImage:
                images = request.FILES.getlist("gallery_images")
                cover_set = False
                for i, img_file in enumerate(images[:20]):  # max 20 images
                    is_cover = (i == 0) and not cover_set
                    try:
                        CarDealerVehicleImage.objects.create(
                            vehicle=vehicle,
                            image=img_file,
                            sort_order=i,
                            is_cover=is_cover,
                            uploaded_by=request.user,
                        )
                        if is_cover:
                            cover_set = True
                    except Exception as img_err:
                        log.warning("Could not save vehicle image: %s", img_err)

            messages.success(request, f"Vehicle '{vehicle.display_name}' added to inventory.")

            # Auto-publish to marketplace if requested
            if data.get("publish_to_marketplace") == "1":
                try:
                    _create_or_update_marketplace_listing(vehicle, request.user, biz)
                    messages.success(request, "Vehicle published to marketplace.")
                except Exception as mp_err:
                    log.warning("Marketplace auto-publish failed: %s", mp_err)

            return redirect("car_dealer:vehicle_detail", pk=vehicle.pk)

        except Exception as e:
            log.exception("Error adding vehicle: %s", e)
            messages.error(request, f"Could not add vehicle: {e}")

    # Build car models JSON for JS
    car_models_by_make: dict[str, list] = {}
    for cm in car_models:
        key = str(cm.make_id)
        if key not in car_models_by_make:
            car_models_by_make[key] = []
        car_models_by_make[key].append({"id": cm.pk, "name": cm.name, "body_type": cm.body_type})

    return render(
        request,
        "car_dealer/stock_in.html",
        {
            "makes": makes,
            "popular_makes": popular_makes,
            "car_models_json": json.dumps(car_models_by_make),
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
            "current_year": timezone.now().year,
        },
    )


# ---------------------------------------------------------------------------
# Vehicle detail / quick edit
# ---------------------------------------------------------------------------

@login_required
@require_business
def vehicle_detail(request: HttpRequest, pk: int) -> HttpResponse:
    biz = get_active_business(request)
    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)

    if request.method == "POST" and is_manager(request.user, biz):
        action = request.POST.get("_action", "")

        if action == "upload_images":
            return _handle_vehicle_image_upload(request, vehicle)

        # Quick field updates
        for field in ["selling_price", "status", "location_text", "description", "features_notes"]:
            val = request.POST.get(field)
            if val is not None:
                if field == "selling_price":
                    try:
                        val = Decimal(val.strip()) if val.strip() else None
                    except (InvalidOperation, ValueError):
                        val = vehicle.selling_price
                setattr(vehicle, field, val)
        vehicle.save()
        messages.success(request, "Vehicle updated.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    gallery_images = (
        [
            image
            for image in vehicle.gallery_images.order_by("-is_cover", "sort_order", "uploaded_at")
            if object_image_url(image)
        ]
        if hasattr(vehicle, "gallery_images")
        else []
    )
    try:
        marketplace_listing = vehicle.marketplace_listing
    except Exception:
        # FK may point to a deleted listing — heal it
        vehicle.marketplace_listing = None
        vehicle.save(update_fields=["marketplace_listing"])
        marketplace_listing = None

    return render(
        request,
        "car_dealer/vehicle_detail.html",
        {
            "vehicle": vehicle,
            "gallery_images": gallery_images,
            "marketplace_listing": marketplace_listing,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
            "is_manager": is_manager(request.user, biz),
        },
    )


_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


def _handle_vehicle_image_upload(request, vehicle):
    """Handle photo upload POST from vehicle detail page."""
    CarDealerVehicleImage = _get_image_model()
    if not CarDealerVehicleImage:
        messages.error(request, "Image model not available.")
        return redirect("car_dealer:vehicle_detail", pk=vehicle.pk)

    images = request.FILES.getlist("gallery_images")
    if not images:
        messages.warning(request, "No images selected.")
        return redirect("car_dealer:vehicle_detail", pk=vehicle.pk)

    import os as _os
    existing_count = vehicle.gallery_images.count()
    added = 0
    skipped = 0
    for i, img_file in enumerate(images[:20]):
        # Validate extension
        ext = _os.path.splitext(img_file.name or "")[1].lower()
        if ext not in _ALLOWED_IMAGE_EXTS:
            messages.warning(request, f"Skipped '{img_file.name}': only JPEG, PNG, and WEBP are allowed.")
            skipped += 1
            continue
        # Validate size
        if img_file.size > _MAX_IMAGE_BYTES:
            messages.warning(request, f"Skipped '{img_file.name}': file exceeds 10 MB limit.")
            skipped += 1
            continue
        try:
            is_cover = existing_count == 0 and i == 0
            CarDealerVehicleImage.objects.create(
                vehicle=vehicle,
                image=img_file,
                sort_order=existing_count + i,
                is_cover=is_cover,
                uploaded_by=request.user,
            )
            added += 1
        except Exception as err:
            log.warning("Image upload error for vehicle %s: %s", vehicle.pk, err)
            messages.warning(request, f"Could not save '{img_file.name}': {err}")
            skipped += 1

    if added:
        messages.success(request, f"{added} photo{'s' if added != 1 else ''} added successfully.")
    if not added and not skipped:
        messages.error(request, "Could not save any photos. Please try again.")
    return redirect("car_dealer:vehicle_detail", pk=vehicle.pk)


# ---------------------------------------------------------------------------
# Delete vehicle image (AJAX or regular POST)
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def delete_vehicle_image(request: HttpRequest, pk: int, image_pk: int) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        return JsonResponse({"error": "Permission denied."}, status=403)

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    CarDealerVehicleImage = _get_image_model()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)
    img = get_object_or_404(CarDealerVehicleImage, pk=image_pk, vehicle=vehicle)

    was_cover = img.is_cover
    img.image.delete(save=False)
    img.delete()

    # If we deleted the cover, promote the next image
    if was_cover:
        next_img = vehicle.gallery_images.order_by("sort_order", "uploaded_at").first()
        if next_img:
            next_img.is_cover = True
            next_img.save(update_fields=["is_cover"])

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    messages.success(request, "Photo deleted.")
    return redirect("car_dealer:vehicle_detail", pk=pk)


# ---------------------------------------------------------------------------
# Set cover image
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def set_cover_image(request: HttpRequest, pk: int, image_pk: int) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        return JsonResponse({"error": "Permission denied."}, status=403)

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    CarDealerVehicleImage = _get_image_model()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)
    img = get_object_or_404(CarDealerVehicleImage, pk=image_pk, vehicle=vehicle)

    # Clear all cover flags
    vehicle.gallery_images.update(is_cover=False)
    img.is_cover = True
    img.save(update_fields=["is_cover"])

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    messages.success(request, "Cover photo updated.")
    return redirect("car_dealer:vehicle_detail", pk=pk)


# ---------------------------------------------------------------------------
# Publish / unpublish to Marketplace
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def publish_to_marketplace(request: HttpRequest, pk: int) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        messages.error(request, "Only managers can publish listings.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)
    action = request.POST.get("mp_action", "publish")

    try:
        if action == "unpublish":
            if vehicle.marketplace_listing_id:
                from inventory.models_marketplace import ListingStatus
                vehicle.marketplace_listing.status = ListingStatus.OFFLINE
                vehicle.marketplace_listing.save(update_fields=["status", "updated_at"])
                messages.success(request, "Listing taken offline.")
        elif action == "mark_draft":
            if vehicle.marketplace_listing_id:
                from inventory.models_marketplace import ListingStatus
                vehicle.marketplace_listing.status = ListingStatus.DRAFT
                vehicle.marketplace_listing.save(update_fields=["status", "updated_at"])
                messages.success(request, "Listing saved as draft.")
        else:
            listing = _create_or_update_marketplace_listing(vehicle, request.user, biz)
            messages.success(request, f"Vehicle published to marketplace as '{listing.title}'.")
    except Exception as e:
        log.exception("Marketplace publish error: %s", e)
        messages.error(request, f"Could not publish: {e}")

    return redirect("car_dealer:vehicle_detail", pk=pk)


def _create_or_update_marketplace_listing(vehicle, user, biz):
    """
    Create or update a MarketplaceListing for a CarDealerVehicle.
    Syncs: title, price, description, images, and vertical_metadata.
    """
    from inventory.models_marketplace import MarketplaceListing, MarketplaceListingImage, ListingStatus

    make_label = vehicle.make.name if vehicle.make else vehicle.make_text or "Vehicle"
    model_label = vehicle.model.name if vehicle.model else vehicle.model_text or ""
    year_label = str(vehicle.year) if vehicle.year else ""
    title_parts = [p for p in [year_label, make_label, model_label, vehicle.trim] if p]
    title = " ".join(title_parts) or vehicle.display_name

    metadata = {
        "make": make_label,
        "model": model_label,
        "year": str(vehicle.year) if vehicle.year else "",
        "mileage": str(vehicle.mileage) if vehicle.mileage is not None else "",
        "transmission": vehicle.get_transmission_display() if vehicle.transmission else "",
        "fuel_type": vehicle.get_fuel_type_display() if vehicle.fuel_type else "",
        "color": vehicle.color,
        "condition": vehicle.get_condition_display() if vehicle.condition else "",
        "chassis_no": vehicle.chassis_no,
        "body_type": vehicle.get_body_type_display() if vehicle.body_type else "",
        "engine_size": vehicle.engine_size,
        "drivetrain": vehicle.get_drivetrain_display() if vehicle.drivetrain else "",
        "stock_ref": vehicle.stock_ref,
        "status": vehicle.get_status_display(),
    }

    if vehicle.marketplace_listing_id:
        listing = vehicle.marketplace_listing
        listing.title = title
        listing.price = vehicle.selling_price
        listing.description = vehicle.description or vehicle.features_notes or ""
        listing.location_text = vehicle.location_text
        listing.vertical_metadata = metadata
        listing.status = ListingStatus.LIVE
        listing.save(update_fields=["title", "price", "description", "location_text", "vertical_metadata", "status", "updated_at"])
    else:
        listing = MarketplaceListing.objects.create(
            business=biz,
            vertical="car_dealer",
            title=title,
            price=vehicle.selling_price,
            description=vehicle.description or vehicle.features_notes or "",
            location_text=vehicle.location_text,
            contact_phone=getattr(biz, "phone", "") or "",
            contact_email=getattr(biz, "email", "") or "",
            address=vehicle.location_text,
            vertical_metadata=metadata,
            status=ListingStatus.LIVE,
            created_by=user,
        )
        vehicle.marketplace_listing = listing
        vehicle.save(update_fields=["marketplace_listing"])

    # Sync gallery images → MarketplaceListingImage
    _sync_vehicle_images_to_listing(vehicle, listing)

    return listing


def _sync_vehicle_images_to_listing(vehicle, listing):
    """Copy vehicle gallery images to the marketplace listing."""
    from inventory.models_marketplace import MarketplaceListingImage

    gallery = list(vehicle.gallery_images.order_by("-is_cover", "sort_order", "uploaded_at")[:10])
    if not gallery:
        return

    # Remove old listing images and re-add from vehicle gallery
    try:
        listing.images.all().delete()
    except Exception as e:
        log.warning("Could not clear old listing images: %s", e)

    for i, vimg in enumerate(gallery):
        try:
            MarketplaceListingImage.objects.create(
                listing=listing,
                image=vimg.image,
                caption=vimg.caption or "",
                sort_order=i,
            )
        except Exception as e:
            log.warning("Could not sync vehicle image to listing: %s", e)


# ---------------------------------------------------------------------------
# Sell Vehicle
# ---------------------------------------------------------------------------

@login_required
@require_business
def sell_vehicle(request: HttpRequest, pk: int) -> HttpResponse:
    biz = get_active_business(request)
    if not is_manager(request.user, biz):
        messages.error(request, "Only managers can process vehicle sales.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    CarMake, CarModel, CarDealerVehicle = _get_car_models()
    vehicle = get_object_or_404(CarDealerVehicle, pk=pk, business=biz)

    if vehicle.status == "sold":
        messages.info(request, "This vehicle has already been sold.")
        return redirect("car_dealer:vehicle_detail", pk=pk)

    if request.method == "POST":
        buyer_name = request.POST.get("buyer_name", "").strip()
        buyer_phone = request.POST.get("buyer_phone", "").strip()
        payment_method = request.POST.get("payment_method", "CASH").strip()
        sale_price_raw = request.POST.get("sale_price", "").strip()

        sale_price = vehicle.selling_price
        if sale_price_raw:
            try:
                sale_price = Decimal(sale_price_raw)
            except (InvalidOperation, ValueError):
                pass

        try:
            vehicle.mark_sold(
                buyer_name=buyer_name,
                buyer_phone=buyer_phone,
                sale_price=sale_price,
                payment_method=payment_method,
                sold_by=request.user,
            )
            messages.success(
                request,
                f"Vehicle '{vehicle.display_name}' sold successfully. "
                f"Sale price: {biz.currency} {sale_price}.",
            )
            return redirect("car_dealer:vehicle_detail", pk=pk)
        except Exception as e:
            log.exception("Error processing vehicle sale: %s", e)
            messages.error(request, f"Could not process sale: {e}")

    return render(
        request,
        "car_dealer/sell_vehicle.html",
        {
            "vehicle": vehicle,
            "business": biz,
            "BUSINESS_VERTICAL": "car_dealer",
        },
    )


# ---------------------------------------------------------------------------
# Seed reference data
# ---------------------------------------------------------------------------

@login_required
@require_business
def seed_car_data(request: HttpRequest) -> HttpResponse:
    """
    One-click seed of CarMake / CarModel reference catalog.
    Safe to run multiple times (idempotent).  Manager-only.
    """
    from tenants.utils_roles import is_manager as _is_manager
    biz = get_active_business(request)

    if not _is_manager(request.user, biz):
        messages.error(request, "Only managers can seed reference data.")
        return redirect("car_dealer:dashboard")

    try:
        from inventory.management.commands.seed_car_dealer_data import CAR_DATA
        from inventory.models_car_dealer import CarMake, CarModel

        created_makes  = 0
        created_models = 0

        for entry in CAR_DATA:
            make_obj, make_new = CarMake.objects.get_or_create(
                name=entry["make"],
                defaults={
                    "slug": entry["make"].lower().replace(" ", "-").replace("-benz", "benz"),
                    "sort_order": entry.get("sort_order", 99),
                    "is_popular": entry.get("popular", False),
                },
            )
            if make_new:
                created_makes += 1

            for m in entry.get("models", []):
                _, model_new = CarModel.objects.get_or_create(
                    make=make_obj,
                    name=m["name"],
                    defaults={
                        "slug": (make_obj.slug + "-" + m["name"].lower().replace(" ", "-"))[:80],
                        "body_type": m.get("body_type", ""),
                        "common_years": m.get("common_years", ""),
                    },
                )
                if model_new:
                    created_models += 1

        if created_makes or created_models:
            messages.success(
                request,
                f"Seeded {created_makes} make(s) and {created_models} model(s). "
                "Data is ready for use.",
            )
        else:
            messages.info(request, "Reference catalog already up to date — nothing new to add.")
    except Exception as e:
        log.exception("Car data seeding failed: %s", e)
        messages.error(request, f"Seeding failed: {e}")

    return redirect("car_dealer:stock_in")
