# inventory/models_car_hire.py
"""
Car Hire Service vertical models.
Tracks vehicles (fleet), trips/bookings, and maintenance.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business


User = settings.AUTH_USER_MODEL


# ==============================================================================
# VEHICLE STATUS
# ==============================================================================


class VehicleStatus(models.TextChoices):
    """Status of a vehicle"""
    AVAILABLE = "available", "Available"
    ON_TRIP = "on_trip", "On Trip"
    MAINTENANCE = "maintenance", "Maintenance"


# ==============================================================================
# TRIP STATUS
# ==============================================================================


class TripStatus(models.TextChoices):
    """Status of a trip/booking"""
    UPCOMING = "upcoming", "Upcoming"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class TripType(models.TextChoices):
    """Type of trip"""
    PASSENGER = "passenger", "Passenger"
    CARGO = "cargo", "Cargo"
    EMPTY = "empty", "Empty/Repositioning"


# ==============================================================================
# VEHICLE MAKE CHOICES (Malawi-relevant)
# ==============================================================================


class VehicleMake(models.TextChoices):
    """Common vehicle makes in Malawi"""
    TOYOTA = "toyota", "Toyota"
    FORD = "ford", "Ford"
    MAZDA = "mazda", "Mazda"
    HONDA = "honda", "Honda"
    NISSAN = "nissan", "Nissan"
    ISUZU = "isuzu", "Isuzu"
    MITSUBISHI = "mitsubishi", "Mitsubishi"
    HYUNDAI = "hyundai", "Hyundai"
    SUZUKI = "suzuki", "Suzuki"
    OTHER = "other", "Other"


# ==============================================================================
# VEHICLE MODEL
# ==============================================================================


class Vehicle(models.Model):
    """
    A vehicle in the car hire fleet.
    Each vehicle belongs to a business and can be tracked individually.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="car_hire_vehicles",
        db_index=True,
    )
    
    # Vehicle identification
    name = models.CharField(
        max_length=150,
        help_text="Display name, e.g. 'Toyota Fortuner 2019'",
    )
    make = models.CharField(
        max_length=30,
        choices=VehicleMake.choices,
        default=VehicleMake.TOYOTA,
        db_index=True,
    )
    model = models.CharField(
        max_length=100,
        help_text="Model name, e.g. 'Fortuner', 'Ranger', 'Hiace', 'Bongo'",
    )
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Year of manufacture",
    )
    plate_number = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Vehicle registration/plate number",
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=VehicleStatus.choices,
        default=VehicleStatus.AVAILABLE,
        db_index=True,
    )
    
    # Pricing
    daily_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Daily rental rate in MWK",
    )
    
    # Odometer and maintenance tracking
    current_odometer = models.PositiveIntegerField(
        default=0,
        help_text="Current odometer reading in km",
    )
    next_maintenance_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer reading for next scheduled maintenance",
    )
    
    # Optional vehicle details
    color = models.CharField(max_length=50, blank=True, default="")
    seats = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of seats",
    )
    fuel_type = models.CharField(
        max_length=20,
        choices=[
            ("petrol", "Petrol"),
            ("diesel", "Diesel"),
            ("hybrid", "Hybrid"),
            ("electric", "Electric"),
        ],
        default="petrol",
    )
    
    # Photo (optional)
    photo = models.ImageField(
        upload_to="car_hire/vehicles/",
        null=True,
        blank=True,
    )
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default="")
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_hire_vehicles_created",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "is_active"]),
            models.Index(fields=["business", "make"]),
        ]
        # Plate number unique within a business
        unique_together = [("business", "plate_number")]
        verbose_name = "Vehicle"
        verbose_name_plural = "Vehicles"
    
    def __str__(self):
        return f"{self.name} ({self.plate_number})"
    
    @property
    def display_name(self) -> str:
        """Get a formatted display name."""
        parts = [self.get_make_display(), self.model]
        if self.year:
            parts.append(str(self.year))
        return " ".join(parts)
    
    @property
    def is_maintenance_due(self) -> bool:
        """Check if maintenance is due based on odometer."""
        if not self.next_maintenance_km:
            return False
        return self.current_odometer >= self.next_maintenance_km
    
    @property
    def km_until_maintenance(self) -> int | None:
        """Get km until next maintenance."""
        if not self.next_maintenance_km:
            return None
        return max(0, self.next_maintenance_km - self.current_odometer)
    
    @property
    def status_color(self) -> str:
        """Get Bootstrap color class for status badge."""
        colors = {
            VehicleStatus.AVAILABLE: "success",
            VehicleStatus.ON_TRIP: "primary",
            VehicleStatus.MAINTENANCE: "warning",
        }
        return colors.get(self.status, "secondary")


# ==============================================================================
# TRIP / BOOKING MODEL
# ==============================================================================


class Trip(models.Model):
    """
    A trip/booking record for a vehicle.
    Tracks customer info, dates, destination, and pricing.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="car_hire_trips",
        db_index=True,
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    
    # Customer info
    customer_name = models.CharField(
        max_length=150,
        help_text="Customer's name",
    )
    customer_phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Customer's phone number",
    )
    customer_id_number = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Customer's ID/passport number",
    )
    
    # Trip timing
    start_datetime = models.DateTimeField(
        db_index=True,
        help_text="Trip start date and time",
    )
    end_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Trip end date and time",
    )
    
    # Trip details
    destination = models.CharField(
        max_length=255,
        help_text="Destination or route",
    )
    trip_type = models.CharField(
        max_length=20,
        choices=TripType.choices,
        default=TripType.PASSENGER,
        db_index=True,
    )
    
    # Pricing
    price_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total price for the trip in MWK",
    )
    deposit_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Deposit amount paid",
    )
    
    # Odometer tracking
    start_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer at trip start",
    )
    end_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer at trip end",
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.UPCOMING,
        db_index=True,
    )
    
    # Notes
    notes = models.TextField(blank=True, default="")
    
    # Driver/Agent assigned to this trip (optional)
    driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_hire_trips_driven",
        help_text="Driver/agent assigned to this trip",
    )
    
    # Enhanced booking fields (Part 6 requirements)
    pickup_location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Pickup location/address",
    )
    dropoff_location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Dropoff location/address (if different from pickup)",
    )
    daily_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Daily rental rate (for reference/calculation)",
    )
    num_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of rental days (for multi-day bookings)",
    )
    fuel_policy = models.CharField(
        max_length=50,
        choices=[
            ("full_to_full", "Full to Full"),
            ("same_level", "Same Level Return"),
            ("prepaid", "Prepaid Fuel"),
            ("no_fuel", "No Fuel (Driver provides)"),
        ],
        default="full_to_full",
        help_text="Fuel policy for this booking",
    )
    fuel_level_out = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Fuel level at pickup (e.g., 'Full', '3/4', '1/2')",
    )
    fuel_level_in = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Fuel level at return",
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_hire_trips_created",
    )
    
    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["business", "-start_datetime"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["vehicle", "-start_datetime"]),
        ]
        verbose_name = "Trip"
        verbose_name_plural = "Trips"
    
    def __str__(self):
        return f"{self.customer_name} → {self.destination} ({self.start_datetime.strftime('%b %d')})"
    
    @property
    def distance_km(self) -> int | None:
        """Calculate trip distance from odometer readings."""
        if self.start_odometer is not None and self.end_odometer is not None:
            return self.end_odometer - self.start_odometer
        return None
    
    @property
    def duration_days(self) -> int | None:
        """Calculate trip duration in days."""
        if self.start_datetime and self.end_datetime:
            delta = self.end_datetime - self.start_datetime
            return max(1, delta.days + 1)  # At least 1 day
        return None
    
    @property
    def balance_due(self) -> Decimal:
        """Calculate remaining balance."""
        return self.price_total - self.deposit_paid
    
    @property
    def status_color(self) -> str:
        """Get Bootstrap color class for status badge."""
        colors = {
            TripStatus.UPCOMING: "info",
            TripStatus.ACTIVE: "primary",
            TripStatus.COMPLETED: "success",
            TripStatus.CANCELLED: "secondary",
        }
        return colors.get(self.status, "secondary")
    
    def start_trip(self):
        """Mark trip as active and update vehicle status."""
        self.status = TripStatus.ACTIVE
        self.start_odometer = self.vehicle.current_odometer
        self.save(update_fields=["status", "start_odometer"])
        
        # Update vehicle status
        self.vehicle.status = VehicleStatus.ON_TRIP
        self.vehicle.save(update_fields=["status"])
    
    def complete_trip(self, end_odometer: int | None = None):
        """Mark trip as completed and update vehicle."""
        self.status = TripStatus.COMPLETED
        self.end_datetime = timezone.now()
        if end_odometer:
            self.end_odometer = end_odometer
        self.save(update_fields=["status", "end_datetime", "end_odometer"])
        
        # Update vehicle
        if end_odometer:
            self.vehicle.current_odometer = end_odometer
        self.vehicle.status = VehicleStatus.AVAILABLE
        self.vehicle.save(update_fields=["status", "current_odometer"])
    
    def cancel_trip(self):
        """Cancel the trip."""
        self.status = TripStatus.CANCELLED
        self.save(update_fields=["status"])
        
        # If trip was active, release vehicle
        if self.vehicle.status == VehicleStatus.ON_TRIP:
            self.vehicle.status = VehicleStatus.AVAILABLE
            self.vehicle.save(update_fields=["status"])


# ==============================================================================
# MAINTENANCE RECORD (optional, for tracking)
# ==============================================================================


class MaintenanceType(models.TextChoices):
    """Types of maintenance"""
    SERVICE = "service", "Scheduled Service"
    REPAIR = "repair", "Repair"
    TYRES = "tyres", "Tyre Replacement"
    BRAKES = "brakes", "Brake Service"
    OIL_CHANGE = "oil_change", "Oil Change"
    OTHER = "other", "Other"


class MaintenanceRecord(models.Model):
    """
    Tracks maintenance history for vehicles.
    """
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="maintenance_records",
    )
    
    # Maintenance details
    maintenance_type = models.CharField(
        max_length=20,
        choices=MaintenanceType.choices,
        default=MaintenanceType.SERVICE,
        db_index=True,
    )
    date = models.DateField(
        default=timezone.now,
        db_index=True,
    )
    description = models.TextField(
        help_text="Description of work done",
    )
    odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer reading at maintenance",
    )
    
    # Cost tracking
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total maintenance cost in MWK",
    )
    
    # Vendor/garage info
    vendor = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Garage or service provider",
    )
    
    # Next maintenance schedule
    next_maintenance_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Odometer for next maintenance (auto-updates vehicle)",
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_hire_maintenance_created",
    )
    
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["vehicle", "-date"]),
        ]
        verbose_name = "Maintenance Record"
        verbose_name_plural = "Maintenance Records"
    
    def __str__(self):
        return f"{self.vehicle.name} - {self.get_maintenance_type_display()} ({self.date})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Update vehicle's next maintenance km if specified
        if self.next_maintenance_km:
            self.vehicle.next_maintenance_km = self.next_maintenance_km
            self.vehicle.save(update_fields=["next_maintenance_km"])


# ==============================================================================
# REVENUE & COSTS TRACKING
# ==============================================================================


class CarHireRevenue(models.Model):
    """
    Tracks additional revenue entries for Car Hire business (beyond trip-based revenue).
    E.g. extra charges, insurance claims, late fees, etc.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="car_hire_revenues",
        db_index=True,
    )
    
    # Revenue details
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Revenue amount in MWK",
    )
    category = models.CharField(
        max_length=50,
        choices=[
            ("trip", "Trip/Booking"),
            ("extra_charges", "Extra Charges"),
            ("insurance", "Insurance Claim"),
            ("late_fee", "Late Return Fee"),
            ("damage", "Damage Recovery"),
            ("other", "Other"),
        ],
        default="other",
        db_index=True,
    )
    description = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")
    
    # Optional vehicle reference
    vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revenues",
    )
    
    # Optional trip reference
    trip = models.ForeignKey(
        Trip,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="additional_revenues",
    )
    
    # Date tracking
    received_on = models.DateField(
        default=timezone.now,
        db_index=True,
        help_text="Date when revenue was received",
    )
    
    # Audit
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="car_hire_revenues_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-received_on", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-received_on"]),
            models.Index(fields=["business", "category", "-received_on"]),
        ]
        verbose_name = "Car Hire Revenue"
        verbose_name_plural = "Car Hire Revenues"
    
    def __str__(self):
        return f"{self.get_category_display()} - MWK {self.amount:,.0f} ({self.received_on})"


class CarHireCost(models.Model):
    """
    Tracks costs/expenses for Car Hire business (fuel, maintenance, driver wages, insurance, etc.)
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="car_hire_costs",
        db_index=True,
    )
    
    # Cost details
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cost amount in MWK",
    )
    category = models.CharField(
        max_length=50,
        choices=[
            ("fuel", "Fuel"),
            ("maintenance", "Maintenance/Repairs"),
            ("driver", "Driver Wages"),
            ("insurance", "Insurance"),
            ("cleaning", "Cleaning/Wash"),
            ("taxes", "Taxes/Licenses"),
            ("parking", "Parking/Tolls"),
            ("rent", "Office/Parking Rent"),
            ("utilities", "Utilities"),
            ("other", "Other"),
        ],
        default="other",
        db_index=True,
    )
    description = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")
    
    # Optional vehicle reference
    vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="costs",
    )
    
    # Date tracking
    incurred_on = models.DateField(
        default=timezone.now,
        db_index=True,
        help_text="Date when cost was incurred",
    )
    
    # Audit
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="car_hire_costs_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-incurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-incurred_on"]),
            models.Index(fields=["business", "category", "-incurred_on"]),
        ]
        verbose_name = "Car Hire Cost"
        verbose_name_plural = "Car Hire Costs"
    
    def __str__(self):
        return f"{self.get_category_display()} - MWK {self.amount:,.0f} ({self.incurred_on})"
