# inventory/services/farm_marketplace.py
"""Sync farm livestock batches and crop lines to MarketplaceListing."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    from tenants.models import Business

    from inventory.models_farm import FarmCrop, FarmLivestockBatch

log = logging.getLogger(__name__)


def _biz_contact(biz: "Business") -> tuple[str, str]:
    phone = getattr(biz, "phone", None) or ""
    email = getattr(biz, "email", None) or ""
    return str(phone), str(email)


def build_livestock_listing_title(batch: "FarmLivestockBatch") -> str:
    st = (
        batch.get_animal_subtype_display()
        if batch.animal_subtype and batch.animal_subtype != "unspecified"
        else batch.get_animal_type_display()
    )
    base = f"{st}: {batch.name}" if st else batch.name
    if batch.breed_text:
        return f"{base} ({batch.breed_text})"
    return base


def build_livestock_vertical_metadata(batch: "FarmLivestockBatch") -> dict:
    meta = {
        "species": batch.get_animal_type_display(),
        "subtype": batch.get_animal_subtype_display(),
        "breed": batch.breed_text or "",
        "quantity": str(batch.count_current),
        "unit": "head",
        "gender": batch.get_gender_display() if batch.gender else "",
        "age_months": str(batch.age_months) if batch.age_months is not None else "",
        "health_note": batch.get_health_status_display(),
        "vaccination": batch.get_vaccination_status_display(),
        "feed_stage": batch.feed_growth_stage,
        "egg_status": batch.egg_production_status,
        "dairy_note": batch.dairy_output_note,
        "availability_note": batch.get_sale_availability_display(),
        "cost_per_head_mwk": str(batch.cost_basis_per_head_mwk)
        if batch.cost_basis_per_head_mwk is not None
        else "",
        "margin_band": batch.margin_band,
        "product_labels": ", ".join(_livestock_marketplace_labels(batch)),
    }
    loc = None
    if batch.location:
        loc = batch.location.name
    elif batch.business:
        loc = getattr(batch.business, "city", None) or ""
    if loc:
        meta["farm_location"] = loc
    return {k: v for k, v in meta.items() if v not in (None, "", [])}


def _livestock_marketplace_labels(batch: "FarmLivestockBatch") -> list[str]:
    labels: list[str] = []
    at = batch.animal_type
    if at in ("cattle", "pigs", "goats", "chickens", "sheep", "fish", "ducks", "rabbits"):
        labels.append("Live livestock")
    if batch.vaccination_status == "current":
        labels.append("Vaccination current")
    if batch.count_current and batch.count_current >= 5:
        labels.append("Bulk available")
    if batch.egg_production_status:
        labels.append("Eggs / production tracked")
    if batch.animal_subtype == "cattle_dairy":
        labels.append("Dairy cattle")
    return list(dict.fromkeys(labels))[:8]


def build_crop_listing_title(crop: "FarmCrop") -> str:
    return f"{crop.name} — {crop.get_category_display()}"


def build_crop_vertical_metadata(crop: "FarmCrop") -> dict:
    meta = {
        "species": crop.get_category_display(),
        "subtype": crop.name,
        "produce_type": crop.get_category_display(),
        "quantity": str(crop.quantity_available),
        "quantity_available": str(crop.quantity_available),
        "unit": crop.get_unit_display() if hasattr(crop, "get_unit_display") else str(crop.unit),
        "availability_note": crop.get_sale_availability_display()
        if hasattr(crop, "get_sale_availability_display")
        else "",
        "farm_location": "",
        "margin_band": crop.margin_band,
    }
    return {k: v for k, v in meta.items() if v not in (None, "", [])}


def sync_livestock_batch_to_marketplace(batch: "FarmLivestockBatch", user, biz: "Business"):
    from inventory.models_marketplace import (
        ListingStatus,
        MarketplaceListing,
        MarketplaceListingImage,
    )

    title = build_livestock_listing_title(batch)
    ask = batch.effective_asking_price_per_head_mwk
    price: Decimal | None = ask
    if price is None and batch.valuation_enabled:
        price = batch.price_per_animal_mwk

    desc_parts = []
    if batch.notes:
        desc_parts.append(batch.notes)
    if batch.feed_growth_stage:
        desc_parts.append(f"Feed / stage: {batch.feed_growth_stage}")
    if batch.egg_production_status:
        desc_parts.append(f"Production: {batch.egg_production_status}")
    description = "\n\n".join(desc_parts) if desc_parts else title

    phone, email = _biz_contact(biz)
    loc = ""
    if batch.location:
        loc = batch.location.name
    elif getattr(biz, "address_line1", None):
        loc = biz.address_line1 or ""

    metadata = build_livestock_vertical_metadata(batch)

    if batch.marketplace_listing_id:
        listing = batch.marketplace_listing
        listing.title = title
        listing.price = price
        listing.description = description
        listing.location_text = loc
        listing.vertical = "farm"
        listing.vertical_metadata = metadata
        listing.contact_phone = phone
        listing.contact_email = email
        listing.address = loc
        if batch.sale_availability == "preorder":
            listing.status = ListingStatus.DRAFT
        elif batch.sale_availability == "reserved":
            listing.status = ListingStatus.OUT_OF_STOCK
        else:
            listing.status = ListingStatus.LIVE
        listing.save()
    else:
        listing = MarketplaceListing.objects.create(
            business=biz,
            vertical="farm",
            title=title,
            price=price,
            description=description,
            location_text=loc,
            vertical_metadata=metadata,
            contact_phone=phone,
            contact_email=email,
            address=loc,
            status=ListingStatus.DRAFT
            if batch.sale_availability == "preorder"
            else (ListingStatus.OUT_OF_STOCK if batch.sale_availability == "reserved" else ListingStatus.LIVE),
            created_by=user,
        )
        batch.marketplace_listing = listing
        batch.save(update_fields=["marketplace_listing"])

    # Images: primary + gallery
    listing = batch.marketplace_listing
    assert listing is not None
    listing.images.all().delete()
    order = 0
    if batch.primary_image:
        try:
            MarketplaceListingImage.objects.create(
                listing=listing, image=batch.primary_image, sort_order=order, caption="Primary"
            )
            order += 1
        except Exception as e:
            log.warning("Primary image sync: %s", e)
    for g in batch.gallery_images.order_by("sort_order", "uploaded_at"):
        try:
            MarketplaceListingImage.objects.create(
                listing=listing, image=g.image, sort_order=order, caption=g.caption
            )
            order += 1
        except Exception as e:
            log.warning("Gallery image sync: %s", e)

    batch.last_marketplace_sync_at = timezone.now()
    batch.save(update_fields=["last_marketplace_sync_at"])


def sync_farm_crop_to_marketplace(crop: "FarmCrop", user, biz: "Business"):
    from inventory.models_marketplace import (
        ListingStatus,
        MarketplaceListing,
        MarketplaceListingImage,
    )

    title = build_crop_listing_title(crop)
    price = crop.list_price_per_unit_mwk
    desc = f"{crop.name} — {crop.quantity_available} {crop.get_unit_display()} on hand. Category: {crop.get_category_display()}."
    if crop.is_featured_listing:
        desc = "Featured. " + desc
    phone, email = _biz_contact(biz)
    metadata = build_crop_vertical_metadata(crop)

    if crop.marketplace_listing_id:
        listing = crop.marketplace_listing
        listing.title = title
        listing.price = price
        listing.description = desc
        listing.vertical_metadata = metadata
        listing.vertical = "farm"
        listing.contact_phone = phone
        listing.contact_email = email
        listing.status = ListingStatus.LIVE if crop.quantity_available and crop.quantity_available > 0 else ListingStatus.OUT_OF_STOCK
        listing.save()
    else:
        listing = MarketplaceListing.objects.create(
            business=biz,
            vertical="farm",
            title=title,
            price=price,
            description=desc,
            vertical_metadata=metadata,
            contact_phone=phone,
            contact_email=email,
            status=ListingStatus.LIVE
            if crop.quantity_available and crop.quantity_available > 0
            else ListingStatus.OUT_OF_STOCK,
            created_by=user,
        )
        crop.marketplace_listing = listing
        crop.save(update_fields=["marketplace_listing"])

    listing = crop.marketplace_listing
    assert listing is not None
    listing.images.all().delete()
    if crop.primary_image:
        try:
            MarketplaceListingImage.objects.create(listing=listing, image=crop.primary_image, sort_order=0)
        except Exception as e:
            log.warning("Crop image sync: %s", e)

    crop.last_marketplace_sync_at = timezone.now()
    crop.save(update_fields=["last_marketplace_sync_at"])


def unpublish_livestock_batch_listing(batch: "FarmLivestockBatch"):
    from inventory.models_marketplace import ListingStatus

    if not batch.marketplace_listing_id:
        return
    listing = batch.marketplace_listing
    listing.status = ListingStatus.OFFLINE
    listing.save(update_fields=["status", "updated_at"])


def unpublish_farm_crop_listing(crop: "FarmCrop"):
    from inventory.models_marketplace import ListingStatus

    if not crop.marketplace_listing_id:
        return
    listing = crop.marketplace_listing
    listing.status = ListingStatus.OFFLINE
    listing.save(update_fields=["status", "updated_at"])
