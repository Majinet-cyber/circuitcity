# inventory/models_marketplace.py
"""
Marketplace models for public business listings and enquiries.

Each business can create public listings (products/services) with:
- Multiple photos
- Status workflow (draft → live → offline / sold / out_of_stock)
- Vertical-aware metadata
- Contact info and location
- Optional link to inventory item for stock-sync

Security:
- All media uploads are validated (size, type)
- Only live listings are shown publicly
- Permissions enforced: only managers/admins can create/edit listings
- No private business data exposed
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, EmailValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Listing status choices
# ---------------------------------------------------------------------------
class ListingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    LIVE = "live", "Live"
    OFFLINE = "offline", "Offline"
    SOLD = "sold", "Sold"
    OUT_OF_STOCK = "out_of_stock", "Out of Stock"


class MarketplaceLeadSource(models.TextChoices):
    QUOTE_REQUEST = "quote_request", "Quote Request"
    WHATSAPP_CLICK = "whatsapp_click", "WhatsApp Click"
    PHONE_CLICK = "phone_click", "Phone Click"
    EMAIL_CLICK = "email_click", "Email Click"
    MARKETPLACE_FORM = "marketplace_form", "Marketplace Form"


class MarketplaceLeadStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    NEGOTIATING = "negotiating", "Negotiating"
    WON = "won", "Won"
    LOST = "lost", "Lost"
    INVALID = "invalid", "Invalid"


class MarketplaceCommissionStatus(models.TextChoices):
    NOT_APPLICABLE = "not_applicable", "Not Applicable"
    PENDING = "pending", "Pending"
    DUE = "due", "Due"
    PAID = "paid", "Paid"
    WAIVED = "waived", "Waived"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_marketplace_media_size(file):
    """Max 10 MB."""
    MAX_SIZE = 10 * 1024 * 1024
    if file.size > MAX_SIZE:
        raise ValidationError(
            f"File size exceeds 10 MB limit. Current size: {file.size / (1024 * 1024):.1f} MB"
        )


def validate_marketplace_media_type(file):
    """Allow JPEG, PNG, WEBP, MP4, WEBM only."""
    ALLOWED_TYPES = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
        "video/webm",
    }
    content_type = getattr(file, "content_type", "")
    if not content_type:
        # Fallback: infer from extension
        name = getattr(file, "name", "") or ""
        ext = os.path.splitext(name)[1].lower()
        ext_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
        }
        content_type = ext_map.get(ext, "")
    if content_type not in ALLOWED_TYPES:
        raise ValidationError(
            f"Unsupported file type: {content_type or 'unknown'}. "
            "Allowed: JPEG, PNG, WEBP images or MP4, WEBM videos."
        )


def marketplace_media_upload_path(instance, filename):
    """marketplace/<business_id>/<year>/<month>/<filename>"""
    filename = os.path.basename(filename)
    now = timezone.now()
    business_id = getattr(instance, "business_id", None) or getattr(
        getattr(instance, "listing", None), "business_id", "0"
    )
    return f"marketplace/{business_id}/{now.year}/{now.month:02d}/{filename}"


def _unique_listing_slug(business, base: str, exclude_pk=None) -> str:
    """Generate a slug that is unique within the given business."""
    slug = slugify(base)[:80] or "listing"
    qs = MarketplaceListing.objects.filter(business=business, listing_slug=slug)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if not qs.exists():
        return slug
    for i in range(2, 9999):
        candidate = f"{slug}-{i}"
        if not MarketplaceListing.objects.filter(business=business, listing_slug=candidate).exclude(
            pk=exclude_pk or 0
        ).exists():
            return candidate
    return f"{slug}-{timezone.now().timestamp():.0f}"


# ---------------------------------------------------------------------------
# MarketplaceListing
# ---------------------------------------------------------------------------

class MarketplaceListing(models.Model):
    """
    A public listing (product/service) that appears on the marketplace.

    Businesses create listings to showcase their offerings.
    Public users can view listings and submit enquiries.
    """

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="marketplace_listings",
        db_index=True,
    )

    # Vertical tag (auto-set from business.business_kind if blank)
    vertical = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="Business vertical (phones, gym, pharmacy, etc.)",
    )

    # URL-friendly identifier unique per business
    listing_slug = models.SlugField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Unique URL slug for this listing within the business",
    )

    # Content
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    # Pricing
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # Primary / legacy single media file (kept for backward compatibility)
    media_file = models.FileField(
        upload_to=marketplace_media_upload_path,
        null=True,
        blank=True,
        validators=[validate_marketplace_media_size, validate_marketplace_media_type],
        help_text="Primary product photo or video (max 10 MB)",
    )

    # Status workflow (replaces is_active bool)
    status = models.CharField(
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.DRAFT,
        db_index=True,
        help_text="Listing status (draft/live/offline/sold/out_of_stock)",
    )

    # Contact info
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    address = models.CharField(max_length=200, blank=True, default="")
    location_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Human-readable location (e.g. Area 25, Lilongwe)",
    )

    # Vertical-specific metadata stored as JSON
    vertical_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vertical-specific extra fields (e.g. specs, condition, size)",
    )

    # Optional link to an inventory item for stock sync
    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_listings",
        help_text="Linked inventory item (optional; for stock-based businesses)",
    )

    # Metadata
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_listings_created",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["vertical", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["business", "listing_slug"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.business.name})"

    # ---------- backward-compat property ----------

    @property
    def is_active(self) -> bool:
        """Backward compat: is_active == status is 'live'."""
        return self.status == ListingStatus.LIVE

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.status = ListingStatus.LIVE if value else ListingStatus.OFFLINE

    # ---------- media helpers ----------

    @property
    def primary_image(self):
        """Return the first MarketplaceListingImage, or None."""
        return self.images.order_by("sort_order", "uploaded_at").first()

    @property
    def all_images(self):
        return self.images.order_by("sort_order", "uploaded_at")

    @property
    def is_image(self) -> bool:
        if not self.media_file:
            return False
        ct = getattr(self.media_file, "content_type", "") or ""
        if ct:
            return ct.startswith("image/")
        ext = os.path.splitext(str(self.media_file.name))[1].lower()
        return ext in {".jpg", ".jpeg", ".png", ".webp"}

    @property
    def is_video(self) -> bool:
        if not self.media_file:
            return False
        ct = getattr(self.media_file, "content_type", "") or ""
        if ct:
            return ct.startswith("video/")
        ext = os.path.splitext(str(self.media_file.name))[1].lower()
        return ext in {".mp4", ".webm"}

    # ---------- status helpers ----------

    @property
    def is_live(self) -> bool:
        return self.status == ListingStatus.LIVE

    @property
    def is_sold(self) -> bool:
        return self.status == ListingStatus.SOLD

    @property
    def is_out_of_stock(self) -> bool:
        return self.status == ListingStatus.OUT_OF_STOCK

    # ---------- save ----------

    def save(self, *args, **kwargs):
        # Auto-set vertical from business
        if not self.vertical and self.business_id:
            try:
                self.vertical = self.business.business_kind or ""
            except Exception:
                pass
        # Auto-generate listing_slug
        if not self.listing_slug and self.title:
            self.listing_slug = _unique_listing_slug(
                self.business, self.title, exclude_pk=self.pk
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# MarketplaceListingImage
# ---------------------------------------------------------------------------

class MarketplaceListingImage(models.Model):
    """
    One of (potentially many) images for a MarketplaceListing.
    """

    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name="images",
        db_index=True,
    )
    image = models.ImageField(
        upload_to=marketplace_media_upload_path,
        validators=[validate_marketplace_media_size],
    )
    caption = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["sort_order", "uploaded_at"]

    def __str__(self):
        return f"Image for {self.listing.title} (#{self.sort_order})"


# ---------------------------------------------------------------------------
# MarketplaceEnquiry
# ---------------------------------------------------------------------------

class MarketplaceEnquiry(models.Model):
    """
    An enquiry submitted by a public user about a marketplace listing.
    """

    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name="enquiries",
        db_index=True,
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="marketplace_enquiries",
        db_index=True,
        help_text="Business receiving this enquiry (denormalized for easy queries)",
    )
    email = models.EmailField(validators=[EmailValidator()])
    phone = models.CharField(max_length=20, blank=True, default="")
    name = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")

    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Marketplace enquiries"
        indexes = [
            models.Index(fields=["business", "is_read"]),
            models.Index(fields=["listing", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"Enquiry from {self.email} about {self.listing.title}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class MarketplaceLead(models.Model):
    """
    Conversion-tracking record for marketplace enquiries and contact clicks.

    MarketplaceEnquiry remains the legacy public enquiry record. This model is
    the measurable sales/commission layer used by sellers and HQ.
    """

    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name="leads",
        db_index=True,
    )
    seller_business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="marketplace_leads",
        null=True,
        blank=True,
        db_index=True,
    )

    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=40, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")
    customer_message = models.TextField(blank=True, default="")

    source_type = models.CharField(
        max_length=30,
        choices=MarketplaceLeadSource.choices,
        default=MarketplaceLeadSource.MARKETPLACE_FORM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=MarketplaceLeadStatus.choices,
        default=MarketplaceLeadStatus.NEW,
        db_index=True,
    )

    deal_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    commission_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    commission_amount_overridden = models.BooleanField(default=False)
    commission_status = models.CharField(
        max_length=24,
        choices=MarketplaceCommissionStatus.choices,
        default=MarketplaceCommissionStatus.NOT_APPLICABLE,
        db_index=True,
    )

    converted_at = models.DateTimeField(null=True, blank=True)
    commission_paid_at = models.DateTimeField(null=True, blank=True)
    commission_paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_commissions_paid",
    )
    commission_waived_at = models.DateTimeField(null=True, blank=True)
    commission_waived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_commissions_waived",
    )
    notes = models.TextField(blank=True, default="")
    hq_notes = models.TextField(blank=True, default="")

    welding_quote = models.ForeignKey(
        "inventory.WeldingQuote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_leads",
    )
    welding_job = models.ForeignKey(
        "inventory.WeldingJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_leads",
    )
    welding_notebook_entry = models.ForeignKey(
        "inventory.WeldingNotebookEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_leads",
    )

    visitor_session_key = models.CharField(max_length=80, blank=True, default="", db_index=True)
    visitor_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller_business", "status"]),
            models.Index(fields=["seller_business", "commission_status"]),
            models.Index(fields=["source_type", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_source_type_display()} lead for {self.listing.title}"

    @property
    def is_won(self) -> bool:
        return self.status == MarketplaceLeadStatus.WON

    def calculate_commission_amount(self) -> Decimal:
        if self.status != MarketplaceLeadStatus.WON or not self.deal_amount:
            return Decimal("0.00")
        amount = Decimal(self.deal_amount) * Decimal(self.commission_percentage) / Decimal("100")
        return amount.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        now = timezone.now()
        if self.status == MarketplaceLeadStatus.WON:
            if not self.converted_at:
                self.converted_at = now
            if not self.commission_status or self.commission_status == MarketplaceCommissionStatus.NOT_APPLICABLE:
                self.commission_status = MarketplaceCommissionStatus.DUE
            if not self.commission_amount_overridden:
                self.commission_amount = self.calculate_commission_amount()
        else:
            self.converted_at = None
            self.commission_amount = Decimal("0.00")
            self.commission_amount_overridden = False
            self.commission_status = MarketplaceCommissionStatus.NOT_APPLICABLE
        super().save(*args, **kwargs)
