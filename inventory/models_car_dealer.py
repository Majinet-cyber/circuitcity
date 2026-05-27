# inventory/models_car_dealer.py
"""
Car Dealer vertical models.

Provides a production-grade vehicle inventory system for car dealerships.
Models:
  - CarMake              : brand/manufacturer reference data (Toyota, Mazda, etc.)
  - CarModel             : model reference data (Corolla, Axio, etc.)
  - CarDealerVehicle     : the actual vehicle in stock
  - CarDealerVehicleImage: one of many photos for a vehicle (gallery)
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Reference / seed data models
# ---------------------------------------------------------------------------

class CarMake(models.Model):
    """
    Vehicle brand/manufacturer.
    Global reference data — not tenant-scoped.
    """

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    logo = models.ImageField(upload_to="car_dealer/makes/", null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    is_popular = models.BooleanField(
        default=False,
        help_text="Show prominently in dropdowns (for common makes)",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Car Make"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class CarModel(models.Model):
    """
    Vehicle model within a brand (e.g. Toyota Corolla).
    Global reference data — not tenant-scoped.
    """

    BODY_TYPES = [
        ("sedan", "Sedan"),
        ("hatchback", "Hatchback"),
        ("suv", "SUV / Crossover"),
        ("pickup", "Pickup / Truck"),
        ("minivan", "Minivan / MPV"),
        ("wagon", "Station Wagon"),
        ("coupe", "Coupe"),
        ("convertible", "Convertible"),
        ("bus", "Bus / Minibus"),
        ("van", "Van"),
        ("other", "Other"),
    ]

    make = models.ForeignKey(CarMake, on_delete=models.CASCADE, related_name="models")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, blank=True)
    body_type = models.CharField(max_length=20, choices=BODY_TYPES, blank=True, default="")
    common_years = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="e.g. '2010-2020' or '2015+'",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = [("make", "name")]
        verbose_name = "Car Model"

    def __str__(self):
        return f"{self.make.name} {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Vehicle inventory
# ---------------------------------------------------------------------------

class CarDealerVehicle(models.Model):
    """
    A vehicle in a car dealer's inventory.
    Tenant-scoped (per Business).
    """

    class VehicleStatus(models.TextChoices):
        IN_STOCK = "in_stock", "In Stock"
        RESERVED = "reserved", "Reserved"
        SOLD = "sold", "Sold"
        OFFLINE = "offline", "Offline / Hidden"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        USED = "used", "Used"
        CERTIFIED = "certified", "Certified Pre-Owned"

    class Transmission(models.TextChoices):
        AUTO = "auto", "Automatic"
        MANUAL = "manual", "Manual"
        CVT = "cvt", "CVT"
        OTHER = "other", "Other"

    class FuelType(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybrid"
        ELECTRIC = "electric", "Electric"
        OTHER = "other", "Other"

    class Drivetrain(models.TextChoices):
        FWD = "fwd", "Front-Wheel Drive"
        RWD = "rwd", "Rear-Wheel Drive"
        AWD = "awd", "All-Wheel Drive"
        FOUR_WD = "4wd", "4-Wheel Drive"

    # Tenant scope
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="car_dealer_vehicles",
        db_index=True,
    )

    # Vehicle identity
    make = models.ForeignKey(
        CarMake,
        on_delete=models.PROTECT,
        related_name="vehicles",
        null=True,
        blank=True,
    )
    model = models.ForeignKey(
        CarModel,
        on_delete=models.PROTECT,
        related_name="vehicles",
        null=True,
        blank=True,
    )
    # Free-text fallback when make/model are not in reference catalog
    make_text = models.CharField(max_length=80, blank=True, default="")
    model_text = models.CharField(max_length=80, blank=True, default="")

    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Model year (e.g. 2019)",
    )
    trim = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Trim/grade (e.g. GL, SE, GLS, Touring)",
    )

    # Specifications
    body_type = models.CharField(
        max_length=20,
        choices=CarModel.BODY_TYPES,
        blank=True,
        default="",
    )
    transmission = models.CharField(
        max_length=10,
        choices=Transmission.choices,
        blank=True,
        default="",
    )
    fuel_type = models.CharField(
        max_length=10,
        choices=FuelType.choices,
        blank=True,
        default="",
    )
    drivetrain = models.CharField(
        max_length=5,
        choices=Drivetrain.choices,
        blank=True,
        default="",
    )
    engine_size = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="e.g. '1.5L', '2000cc'",
    )
    mileage = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer reading in km",
    )
    color = models.CharField(max_length=40, blank=True, default="")
    interior_color = models.CharField(max_length=40, blank=True, default="")

    # IDs
    chassis_no = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Chassis / VIN number",
    )
    stock_ref = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Internal stock reference number",
        db_index=True,
    )

    # Pricing
    buying_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Purchase / cost price",
    )
    selling_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Asking / selling price",
    )

    # Condition & status
    condition = models.CharField(
        max_length=15,
        choices=Condition.choices,
        default=Condition.USED,
    )
    status = models.CharField(
        max_length=10,
        choices=VehicleStatus.choices,
        default=VehicleStatus.IN_STOCK,
        db_index=True,
    )

    # Location / description
    location_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Physical location of the vehicle",
    )
    description = models.TextField(blank=True, default="")
    features_notes = models.TextField(
        blank=True,
        default="",
        help_text="Key features, highlights, or import notes",
    )
    import_source_notes = models.TextField(
        blank=True,
        default="",
        help_text="Import source details (e.g. 'Japan direct, Be Forward')",
    )

    # Dates
    date_stocked = models.DateField(
        default=timezone.localdate,
        help_text="When this vehicle was stocked in",
    )
    sold_at = models.DateTimeField(null=True, blank=True)
    sold_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_dealer_sales",
    )

    # Buyer info (set when sold)
    buyer_name = models.CharField(max_length=200, blank=True, default="")
    buyer_phone = models.CharField(max_length=30, blank=True, default="")
    sale_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Actual price at point of sale",
    )
    payment_method = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="e.g. CASH, BANK_TRANSFER, INSTALLMENT",
    )

    # Marketplace link
    marketplace_listing = models.ForeignKey(
        "inventory.MarketplaceListing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_dealer_vehicles",
        help_text="Linked marketplace listing (auto-managed)",
    )

    # Audit
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    stocked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_dealer_stocked",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["make", "model"]),
        ]
        verbose_name = "Car Dealer Vehicle"

    def __str__(self):
        make_label = (
            self.make.name if self.make else self.make_text or "Unknown"
        )
        model_label = (
            self.model.name if self.model else self.model_text or "Model"
        )
        year_label = f" ({self.year})" if self.year else ""
        return f"{make_label} {model_label}{year_label}"

    @property
    def display_name(self) -> str:
        """Full display name: Year Make Model Trim."""
        parts = []
        if self.year:
            parts.append(str(self.year))
        parts.append(self.make.name if self.make else self.make_text or "")
        parts.append(self.model.name if self.model else self.model_text or "")
        if self.trim:
            parts.append(self.trim)
        return " ".join(p for p in parts if p).strip() or "Vehicle"

    @property
    def is_available(self) -> bool:
        return self.status == self.VehicleStatus.IN_STOCK

    def mark_sold(
        self,
        buyer_name: str = "",
        buyer_phone: str = "",
        sale_price=None,
        payment_method: str = "",
        sold_by=None,
    ) -> None:
        """Mark this vehicle as sold and update marketplace listing."""
        self.status = self.VehicleStatus.SOLD
        self.sold_at = timezone.now()
        self.buyer_name = buyer_name or ""
        self.buyer_phone = buyer_phone or ""
        self.payment_method = payment_method or ""
        if sale_price is not None:
            self.sale_price = sale_price
        if sold_by:
            self.sold_by = sold_by
        self.save()

        # Auto-update linked marketplace listing
        if self.marketplace_listing_id:
            try:
                from inventory.models_marketplace import ListingStatus
                self.marketplace_listing.status = ListingStatus.SOLD
                self.marketplace_listing.save(update_fields=["status", "updated_at"])
            except Exception:
                pass

    @property
    def cover_image(self):
        """Return the primary/cover gallery image, or None."""
        return self.gallery_images.filter(is_cover=True).first() or self.gallery_images.order_by("sort_order", "uploaded_at").first()

    @property
    def has_photos(self) -> bool:
        return self.gallery_images.exists()

    @property
    def photo_count(self) -> int:
        return self.gallery_images.count()


# ---------------------------------------------------------------------------
# Vehicle gallery images
# ---------------------------------------------------------------------------

def _car_dealer_vehicle_image_path(instance, filename):
    """car_dealer/<business_id>/vehicles/<vehicle_id>/<filename>"""
    filename = os.path.basename(filename)
    business_id = instance.vehicle.business_id
    vehicle_id = instance.vehicle_id
    return f"car_dealer/{business_id}/vehicles/{vehicle_id}/{filename}"


class CarDealerVehicleImage(models.Model):
    """
    One of (potentially many) photos for a CarDealerVehicle.
    Supports a primary/cover flag and sort ordering.
    """

    vehicle = models.ForeignKey(
        CarDealerVehicle,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        db_index=True,
    )
    image = models.ImageField(
        upload_to=_car_dealer_vehicle_image_path,
    )
    caption = models.CharField(max_length=200, blank=True, default="")
    is_cover = models.BooleanField(
        default=False,
        help_text="Mark as the primary/cover image shown on cards and marketplace",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_index=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-is_cover", "sort_order", "uploaded_at"]
        verbose_name = "Vehicle Image"
        verbose_name_plural = "Vehicle Images"

    def __str__(self):
        return f"Photo for {self.vehicle.display_name} (#{self.sort_order})"

    def save(self, *args, **kwargs):
        # Ensure only one cover per vehicle
        if self.is_cover and self.vehicle_id:
            CarDealerVehicleImage.objects.filter(
                vehicle_id=self.vehicle_id, is_cover=True
            ).exclude(pk=self.pk or 0).update(is_cover=False)
        super().save(*args, **kwargs)
