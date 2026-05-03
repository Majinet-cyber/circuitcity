from __future__ import annotations

from decimal import Decimal, InvalidOperation


WELDING_MARKETPLACE_CATEGORIES = (
    ("gate", "Gate"),
    ("trellidor", "Trellidor"),
    ("window", "Window"),
    ("table", "Table"),
    ("bed", "Bed"),
    ("roofing", "Roofing"),
    ("custom", "Custom"),
)


def safe_money(value):
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount >= 0 else None


def build_welding_listing_defaults(business, source=None, source_type: str = "") -> dict[str, object]:
    title = ""
    description = ""
    price = None
    location = ""
    phone = ""
    category = "custom"
    source_id = getattr(source, "pk", None)

    if source_type == "quote" and source is not None:
        title = f"{getattr(source, 'customer_name', 'Customer')} welding quote"
        description = getattr(source, "notes", "") or "Custom welding job quotation."
        price = getattr(source, "total", None) or None
        location = getattr(source, "customer_address", "") or ""
        phone = getattr(source, "customer_phone", "") or ""
        template = getattr(source, "template", None)
        category = getattr(template, "code", "") or "custom"
    elif source_type == "job" and source is not None:
        title = getattr(source, "product_description", "") or getattr(source, "job_number", "") or "Completed welding job"
        description = getattr(source, "notes", "") or "Completed welding work."
        price = getattr(source, "final_price", None) or getattr(source, "quoted_price", None) or None
        phone = getattr(source, "customer_phone", "") or ""
        template = getattr(source, "template", None)
        category = getattr(template, "code", "") or "custom"
    elif source_type == "notebook" and source is not None:
        title = f"{source.get_job_type_display()} for {source.site_customer_name}"
        description = "\n\n".join(
            part for part in [source.measurements, source.materials_needed, source.notes] if part
        )
        price = source.estimated_budget
        location = source.customer_address
        phone = source.customer_phone
        category = source.job_type

    return {
        "title": title[:200] or "Welding job",
        "description": description,
        "price": price,
        "location_text": location,
        "address": location,
        "contact_phone": phone,
        "contact_email": getattr(business, "email", "") or "",
        "category": category if category in dict(WELDING_MARKETPLACE_CATEGORIES) else "custom",
        "source_type": source_type,
        "source_id": source_id,
        "business_name": getattr(business, "name", "") or "",
    }


def create_welding_marketplace_listing(
    *,
    business,
    user,
    title: str,
    description: str,
    price,
    category: str,
    location_text: str,
    contact_phone: str,
    contact_email: str,
    status: str,
    media_file=None,
    images=None,
    source_type: str = "",
    source_id=None,
):
    from inventory.models_marketplace import ListingStatus, MarketplaceListing, MarketplaceListingImage

    status = status if status in dict(ListingStatus.choices) else ListingStatus.DRAFT
    category = category if category in dict(WELDING_MARKETPLACE_CATEGORIES) else "custom"
    image_files = list(images or [])
    if not media_file and image_files:
        media_file = image_files[0]
    listing = MarketplaceListing.objects.create(
        business=business,
        vertical="welding",
        title=(title or "Welding job")[:200],
        description=description or "",
        price=safe_money(price),
        media_file=media_file,
        contact_phone=contact_phone or "",
        contact_email=contact_email or "",
        address=location_text or "",
        location_text=location_text or "",
        status=status,
        vertical_metadata={
            "welding_category": category,
            "source_type": source_type or "",
            "source_id": str(source_id or ""),
            "business_name": getattr(business, "name", "") or "",
        },
        created_by=user,
    )
    if image_files and hasattr(image_files[0], "seek"):
        try:
            image_files[0].seek(0)
        except Exception:
            pass
    for index, image in enumerate(image_files):
        if hasattr(image, "seek"):
            try:
                image.seek(0)
            except Exception:
                pass
        MarketplaceListingImage.objects.create(listing=listing, image=image, sort_order=index)
    return listing
