# inventory/models_energy.py
"""
Renewable Energy vertical models.

Entities:
  EnergySite           – a customer/commercial/household installation site
  EnergyAsset          – individual asset (panel, battery, inverter, etc.)
  AssetMaintenanceRecord – maintenance log entry
  EnergyReading        – periodic manual / IoT energy readings
  EnergyAlert          – auto-generated alert for site/asset events
  SavingsRecord        – monthly cost savings estimate

Future AI/IoT integration points are clearly marked with # [AI_HOOK] / # [IOT_HOOK].
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class SiteType(models.TextChoices):
    HOUSEHOLD    = "household",  "Household / Residential"
    COMMERCIAL   = "commercial", "Commercial / Business"
    COMMUNITY    = "community",  "Community / Mini-grid"
    AGRICULTURAL = "agricultural", "Agricultural"
    INDUSTRIAL   = "industrial", "Industrial"
    OTHER        = "other",      "Other"


class SiteStatus(models.TextChoices):
    ACTIVE       = "active",       "Active"
    INACTIVE     = "inactive",     "Inactive"
    UNDER_INSTALL = "installing",  "Under Installation"
    DECOMMISSIONED = "decommissioned", "Decommissioned"


class AssetType(models.TextChoices):
    SOLAR_PANEL       = "solar_panel",       "Solar Panel"
    BATTERY           = "battery",           "Battery Bank"
    INVERTER          = "inverter",          "Inverter"
    CHARGE_CONTROLLER = "charge_controller", "Charge Controller"
    METER             = "meter",             "Meter"
    GENERATOR         = "generator",         "Generator"
    SMART_APPLIANCE   = "smart_appliance",   "Smart Appliance"
    EV_CHARGER        = "ev_charger",        "EV Charger"
    BREAKER           = "breaker",           "Breaker / Switch"
    SENSOR            = "sensor",            "Sensor"
    OTHER             = "other",             "Other"


class AssetStatus(models.TextChoices):
    OPERATIONAL  = "operational",  "Operational"
    DEGRADED     = "degraded",     "Degraded"
    FAULTY       = "faulty",       "Faulty"
    MAINTENANCE  = "maintenance",  "Under Maintenance"
    REPLACED     = "replaced",     "Replaced / Retired"


class MaintenanceType(models.TextChoices):
    ROUTINE      = "routine",      "Routine Inspection"
    CLEANING     = "cleaning",     "Panel / Equipment Cleaning"
    REPLACEMENT  = "replacement",  "Part Replacement"
    REPAIR       = "repair",       "Repair"
    CALIBRATION  = "calibration",  "Calibration / Testing"
    EMERGENCY    = "emergency",    "Emergency Response"
    AUDIT        = "audit",        "Performance Audit"


class AlertSeverity(models.TextChoices):
    LOW      = "low",      "Low"
    MEDIUM   = "medium",   "Medium"
    HIGH     = "high",     "High"
    CRITICAL = "critical", "Critical"


class AlertType(models.TextChoices):
    MAINTENANCE_DUE     = "maintenance_due",     "Maintenance Due / Overdue"
    ASSET_DEGRADED      = "asset_degraded",      "Asset Health Deterioration"
    LOW_GENERATION      = "low_generation",      "Unusual Generation Drop"
    UNUSUAL_CONSUMPTION = "unusual_consumption", "Unusual Consumption"
    OVERLOAD_RISK       = "overload_risk",       "Overload Risk"
    LOW_BATTERY_HEALTH  = "low_battery_health",  "Low Battery Health"
    DEMAND_SPIKE        = "demand_spike",        "Demand Spike Detected"
    DATA_MISSING        = "data_missing",        "Data Missing / Stale"
    RECURRING_FAULT     = "recurring_fault",     "Recurring Site Incident"
    OTHER               = "other",              "Other"


# ---------------------------------------------------------------------------
# EnergySite
# ---------------------------------------------------------------------------

class EnergySite(models.Model):
    """
    Represents a single energy installation site.
    Linked to a tenant business (installer / EPC company).
    """

    business     = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_sites")
    name         = models.CharField(max_length=200, help_text="Site / customer name")
    site_type    = models.CharField(max_length=20, choices=SiteType.choices, default=SiteType.HOUSEHOLD)
    status       = models.CharField(max_length=20, choices=SiteStatus.choices, default=SiteStatus.ACTIVE, db_index=True)

    # Location
    location     = models.CharField(max_length=300, blank=True, default="", help_text="Physical address / GPS description")
    latitude     = models.FloatField(null=True, blank=True)  # [IOT_HOOK] GPS from field device
    longitude    = models.FloatField(null=True, blank=True)

    # Customer / owner details
    customer_name  = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")

    # Installation details
    installed_capacity_kw = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Total installed capacity in kW",
        validators=[MinValueValidator(Decimal("0"))]
    )
    commissioning_date = models.DateField(null=True, blank=True)

    # Energy source mix (multi-select via JSON array or comma list)
    energy_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g. ['solar', 'battery', 'grid', 'generator', 'hybrid']",
    )

    # Assignment
    assigned_technician = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_energy_sites",
        help_text="Primary technician responsible for this site",
    )

    # Economics
    installation_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Total installation cost (MWK)",
    )
    monthly_grid_bill_before = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Estimated monthly grid/fuel bill before solar (MWK)",
    )

    # Operational notes
    notes = models.TextField(blank=True, default="")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Energy Site"
        verbose_name_plural = "Energy Sites"

    def __str__(self):
        return f"{self.name} ({self.get_site_type_display()})"

    @property
    def asset_count(self) -> int:
        return self.assets.filter(status__in=["operational", "degraded"]).count()

    @property
    def months_operational(self) -> int | None:
        if not self.commissioning_date:
            return None
        delta = timezone.now().date() - self.commissioning_date
        return max(delta.days // 30, 0)

    @property
    def estimated_lifetime_savings(self) -> Decimal:
        """
        Simple lifetime savings estimate from monthly readings.
        [AI_HOOK] Replace with ML-based projection model.
        """
        monthly = (
            self.savings_records.aggregate(avg=models.Avg("estimated_savings"))["avg"]
            or Decimal("0")
        )
        months = self.months_operational or 0
        return Decimal(str(monthly)) * months


# ---------------------------------------------------------------------------
# EnergyAsset
# ---------------------------------------------------------------------------

class EnergyAsset(models.Model):
    """
    An individual physical asset installed at an energy site.
    Each asset has health scoring, maintenance scheduling, and IoT device placeholders.
    """

    site         = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="assets")
    business     = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_assets")

    asset_type   = models.CharField(max_length=30, choices=AssetType.choices, db_index=True)
    status       = models.CharField(max_length=20, choices=AssetStatus.choices, default=AssetStatus.OPERATIONAL, db_index=True)

    # Identity
    brand          = models.CharField(max_length=100, blank=True, default="")
    model_name     = models.CharField(max_length=100, blank=True, default="")
    serial_number  = models.CharField(max_length=100, blank=True, default="", db_index=True)

    # Physical specs
    capacity       = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Rated capacity (kW for panels/inverters, kWh for batteries, etc.)",
    )
    capacity_unit  = models.CharField(max_length=20, blank=True, default="kW")

    # Lifecycle
    install_date      = models.DateField(null=True, blank=True)
    warranty_expiry   = models.DateField(null=True, blank=True)
    expected_lifespan_years = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Expected operational lifespan in years",
    )
    maintenance_interval_days = models.PositiveSmallIntegerField(
        null=True, blank=True, default=180,
        help_text="Recommended maintenance interval in days",
    )

    # Health
    health_score = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0–100 health score (100=perfect, 0=failed). [AI_HOOK] ML-derived.",
    )

    # Cost
    asset_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Purchase cost of this asset (MWK)",
    )

    # [IOT_HOOK] Device registry — plug in MQTT/API device IDs when hardware is available
    iot_device_id  = models.CharField(max_length=200, blank=True, default="", help_text="IoT device ID (MQTT topic, API device ID, etc.)")
    telemetry_ready = models.BooleanField(default=False, help_text="True when this asset can receive live telemetry")

    # Notes
    notes = models.TextField(blank=True, default="")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["site", "asset_type", "brand"]
        verbose_name = "Energy Asset"
        verbose_name_plural = "Energy Assets"

    def __str__(self):
        parts = [self.get_asset_type_display()]
        if self.brand:
            parts.append(self.brand)
        if self.model_name:
            parts.append(self.model_name)
        return f"{self.site.name} – {' '.join(parts)}"

    @property
    def is_warranty_valid(self) -> bool:
        if not self.warranty_expiry:
            return False
        return self.warranty_expiry >= timezone.now().date()

    @property
    def age_years(self) -> float | None:
        if not self.install_date:
            return None
        return (timezone.now().date() - self.install_date).days / 365.25

    @property
    def next_maintenance_date(self):
        """
        Compute next due date based on last maintenance or install date.
        [AI_HOOK] Replace with predictive scheduling from ML model.
        """
        last_record = self.maintenance_records.order_by("-performed_at").first()
        baseline = None
        if last_record:
            baseline = last_record.performed_at.date() if hasattr(last_record.performed_at, "date") else last_record.performed_at
        elif self.install_date:
            baseline = self.install_date
        if baseline and self.maintenance_interval_days:
            from datetime import timedelta
            return baseline + timedelta(days=self.maintenance_interval_days)
        return None

    @property
    def is_maintenance_overdue(self) -> bool:
        due = self.next_maintenance_date
        if due is None:
            return False
        return due < timezone.now().date()

    @property
    def risk_score(self) -> int:
        """
        Rules-based risk score (0–100). Higher = more at risk.
        [AI_HOOK] Replace with ML model trained on failure history.
        """
        score = 0
        # Age factor
        age = self.age_years
        if age:
            expected = self.expected_lifespan_years or 10
            age_ratio = age / expected
            score += int(min(age_ratio * 30, 30))
        # Maintenance overdue
        if self.is_maintenance_overdue:
            score += 25
        # Health score factor (inverted)
        score += int((100 - self.health_score) * 0.45)
        # Degraded status
        if self.status == AssetStatus.DEGRADED:
            score += 15
        elif self.status == AssetStatus.FAULTY:
            score = 100
        return min(score, 100)

    @property
    def priority_label(self) -> str:
        r = self.risk_score
        if r >= 75:
            return "critical"
        if r >= 50:
            return "high"
        if r >= 25:
            return "medium"
        return "low"


# ---------------------------------------------------------------------------
# AssetMaintenanceRecord
# ---------------------------------------------------------------------------

class AssetMaintenanceRecord(models.Model):
    """
    Service / maintenance log for a specific asset.
    """

    asset            = models.ForeignKey(EnergyAsset, on_delete=models.CASCADE, related_name="maintenance_records")
    business         = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_maintenance_records")
    technician       = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="energy_maintenance_records"
    )

    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices, default=MaintenanceType.ROUTINE)
    performed_at     = models.DateField(default=timezone.now)

    # What was done
    description      = models.TextField(blank=True, default="", help_text="What was done / observed")
    parts_used       = models.TextField(blank=True, default="", help_text="Spare parts replaced")
    cost             = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Outcomes
    health_score_after = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    root_cause_notes = models.TextField(blank=True, default="")
    follow_up_date   = models.DateField(null=True, blank=True)
    resolved         = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Asset Maintenance Record"

    def __str__(self):
        return f"{self.asset} – {self.get_maintenance_type_display()} on {self.performed_at}"


# ---------------------------------------------------------------------------
# EnergyReading  (manual or IoT input)
# ---------------------------------------------------------------------------

class EnergyReading(models.Model):
    """
    Periodic energy reading for a site. Supports manual entry now,
    IoT streaming later.

    [IOT_HOOK] Future: ingest from MQTT/API via telemetry ingestion service.
    """

    site         = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="readings")
    business     = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_readings")

    reading_date = models.DateField(db_index=True)

    # Generation
    generation_kwh = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Energy generated (kWh) — from solar/generator",
    )
    # Consumption
    consumption_kwh = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Energy consumed (kWh) — from load",
    )
    # Battery state
    battery_soc_pct = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MaxValueValidator(100)],
        help_text="Battery state of charge (%)",
    )

    # Source of reading
    SOURCE_MANUAL = "manual"
    SOURCE_IOT    = "iot"
    SOURCE_CHOICES = [(SOURCE_MANUAL, "Manual Entry"), (SOURCE_IOT, "IoT / API")]
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)

    notes      = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reading_date"]
        unique_together = [("site", "reading_date")]
        verbose_name = "Energy Reading"

    def __str__(self):
        return f"{self.site.name} – {self.reading_date}"

    @property
    def net_kwh(self):
        if self.generation_kwh is not None and self.consumption_kwh is not None:
            return self.generation_kwh - self.consumption_kwh
        return None


# ---------------------------------------------------------------------------
# SavingsRecord
# ---------------------------------------------------------------------------

class SavingsRecord(models.Model):
    """
    Monthly savings estimate per site.
    Computed from monthly_grid_bill_before and actual usage.
    """

    site     = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="savings_records")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_savings")

    month    = models.DateField(help_text="First day of the month this record covers")

    estimated_savings  = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="MWK saved vs. baseline grid/fuel cost",
    )
    operational_cost   = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Maintenance + operational cost this month",
    )
    generation_kwh     = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]
        unique_together = [("site", "month")]
        verbose_name = "Savings Record"

    def __str__(self):
        return f"{self.site.name} – {self.month.strftime('%b %Y')}"

    @property
    def net_benefit(self) -> Decimal:
        return self.estimated_savings - self.operational_cost


# ---------------------------------------------------------------------------
# EnergyAlert
# ---------------------------------------------------------------------------

class EnergyAlert(models.Model):
    """
    Auto-generated (or manually created) alert for a site or asset.
    [AI_HOOK] Rules-based engine now; plug in ML anomaly detector later.
    """

    business  = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_alerts")
    site      = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="alerts", null=True, blank=True)
    asset     = models.ForeignKey(EnergyAsset, on_delete=models.CASCADE, related_name="alerts", null=True, blank=True)

    alert_type = models.CharField(max_length=30, choices=AlertType.choices, db_index=True)
    severity   = models.CharField(max_length=10, choices=AlertSeverity.choices, default=AlertSeverity.MEDIUM, db_index=True)

    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    suggested_action = models.TextField(blank=True, default="")

    # Resolution
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="energy_alerts_resolved"
    )
    resolution_notes = models.TextField(blank=True, default="")

    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Energy Alert"

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"

    def resolve(self, user=None, notes=""):
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save(update_fields=["is_resolved", "resolved_at", "resolved_by", "resolution_notes"])


# ---------------------------------------------------------------------------
# SystemSizingRun  (flagship system sizing module)
# ---------------------------------------------------------------------------

class SizingObjective(models.TextChoices):
    LOWEST_COST     = "lowest_cost",     "Lowest Cost"
    BALANCED        = "balanced",        "Balanced System"
    HIGH_RELIABILITY = "high_reliability", "High Reliability"
    BACKUP_FIRST    = "backup_first",    "Backup-First"
    SAVINGS_FIRST   = "savings_first",   "Savings-First"
    GROWTH_READY    = "growth_ready",    "Growth-Ready"
    OFF_GRID        = "off_grid",        "Off-Grid"
    HYBRID          = "hybrid",          "Hybrid"
    GRID_TIED_BACKUP = "grid_tied_backup", "Grid-Tied with Backup"
    MINI_GRID       = "mini_grid",       "Mini-Grid Concept"


class SystemArchitecture(models.TextChoices):
    SOLAR_ONLY       = "solar_only",       "Solar Only"
    SOLAR_BATTERY    = "solar_battery",    "Solar + Battery"
    SOLAR_GRID       = "solar_grid",       "Solar + Grid"
    SOLAR_BATT_GRID  = "solar_batt_grid",  "Solar + Battery + Grid"
    SOLAR_GENERATOR  = "solar_gen",        "Solar + Generator"
    SOLAR_BATT_GEN   = "solar_batt_gen",   "Solar + Battery + Generator"
    HYBRID_FULL      = "hybrid_full",      "Full Hybrid (Solar+Battery+Grid+Gen)"
    WIND_SOLAR       = "wind_solar",       "Wind + Solar (Placeholder)"


class SystemSizingRun(models.Model):
    """
    A complete system sizing calculation run.
    Stores inputs, computed engineering outputs, economic analysis, and recommendations.
    Can be versioned, attached to a site/customer, cloned, and exported to PDF.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_sizing_runs")
    site = models.ForeignKey(EnergySite, on_delete=models.SET_NULL, null=True, blank=True, related_name="sizing_runs")

    # Identity
    title = models.CharField(max_length=250, help_text="Proposal / sizing run title")
    version = models.PositiveSmallIntegerField(default=1)
    reference_code = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[("draft", "Draft"), ("final", "Final"), ("archived", "Archived")],
        default="draft", db_index=True,
    )

    # Customer info (may differ from site customer)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")
    customer_address = models.CharField(max_length=300, blank=True, default="")

    # Configuration
    design_objective = models.CharField(
        max_length=20, choices=SizingObjective.choices, default=SizingObjective.BALANCED,
    )
    system_architecture = models.CharField(
        max_length=20, choices=SystemArchitecture.choices, default=SystemArchitecture.SOLAR_BATTERY,
    )

    # Grid / backup context
    has_grid_access = models.BooleanField(default=True)
    grid_reliability_pct = models.PositiveSmallIntegerField(
        default=80, help_text="Estimated grid reliability (0-100%)",
    )
    has_generator = models.BooleanField(default=False)
    generator_fuel_cost_per_litre = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    generator_litres_per_hour = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    # Solar parameters
    peak_sun_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("5.0"),
        help_text="Average peak sun hours/day for this location",
    )
    panel_wattage = models.PositiveSmallIntegerField(
        default=550, help_text="Individual panel wattage (Wp)",
    )
    panel_efficiency_pct = models.PositiveSmallIntegerField(
        default=85, help_text="Derating factor for panels (%)",
    )

    # Battery parameters
    battery_dod_pct = models.PositiveSmallIntegerField(
        default=80, help_text="Battery depth of discharge (%)",
    )
    battery_voltage = models.PositiveSmallIntegerField(
        default=48, help_text="System battery voltage (V)",
    )
    autonomy_days = models.DecimalField(
        max_digits=3, decimal_places=1, default=Decimal("1.0"),
        help_text="Days of autonomy required",
    )

    # Load modifiers
    diversity_factor = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0.80"),
        help_text="Diversity factor (0.0–1.0)",
    )
    simultaneity_factor = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0.70"),
        help_text="Simultaneity factor (0.0–1.0)",
    )
    future_growth_pct = models.PositiveSmallIntegerField(
        default=20, help_text="Planned future load growth (%)",
    )
    safety_margin_pct = models.PositiveSmallIntegerField(
        default=15, help_text="Engineering safety margin (%)",
    )

    # === Computed outputs (populated by sizing engine) ===
    total_daily_demand_wh = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_daily_demand_kwh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    peak_load_w = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    surge_load_w = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    corrected_design_load_wh = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Solar array
    recommended_array_kw = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    recommended_panel_count = models.PositiveSmallIntegerField(null=True, blank=True)

    # Battery bank
    recommended_battery_kwh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usable_storage_kwh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Inverter
    recommended_inverter_kw = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    inverter_loading_pct = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    # Charge controller
    recommended_charge_controller_a = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Generator backup
    recommended_generator_kva = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Runtime estimates
    estimated_runtime_hours = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True,
        help_text="Estimated battery runtime under full load (hours)",
    )

    # === Economic outputs ===
    estimated_capex = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_installation_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_annual_maintenance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    projected_monthly_savings = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    projected_annual_savings = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payback_years = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    roi_pct = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    lifetime_cost_estimate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost_per_kwh = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    diesel_offset_monthly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    grid_savings_monthly = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # === Recommendations (JSON) ===
    recommendations = models.JSONField(default=list, blank=True, help_text="List of recommendation strings")
    warnings = models.JSONField(default=list, blank=True, help_text="List of warning strings")
    component_summary = models.JSONField(default=dict, blank=True, help_text="Recommended component breakdown")

    # === Proposal lifecycle (Phase 2) ===
    proposal_status = models.CharField(
        max_length=20,
        choices=[
            ("sizing", "Sizing / Draft"),
            ("proposal_draft", "Proposal Draft"),
            ("proposal_sent", "Sent to Customer"),
            ("approved", "Approved"),
            ("project", "Active Project"),
            ("completed", "Completed / Live Site"),
            ("rejected", "Rejected"),
        ],
        default="sizing", db_index=True,
    )
    proposal_sent_date = models.DateField(null=True, blank=True)
    proposal_valid_until = models.DateField(null=True, blank=True)
    approval_date = models.DateField(null=True, blank=True)
    linked_project_site = models.ForeignKey(
        EnergySite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="originating_proposals",
        help_text="Site created when proposal is converted to active project",
    )

    # === Scenario comparison (Phase 2) ===
    scenario_group = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Group ID to link scenarios for side-by-side comparison",
    )
    scenario_label = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Label within scenario group (e.g. 'Low Cost', 'Balanced', 'High Reliability')",
    )
    is_recommended_scenario = models.BooleanField(
        default=False, help_text="Flagged as the recommended option in a comparison",
    )

    # === Advanced financial metrics (Phase 2) ===
    discount_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.0"),
        help_text="Discount rate for NPV calculation (%)",
    )
    inflation_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("8.0"),
        help_text="Annual inflation assumption (%)",
    )
    energy_tariff_per_kwh = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Grid electricity tariff (MWK/kWh) — overrides default if set",
    )
    diesel_cost_per_litre = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Diesel fuel cost per litre (MWK) — used when generator enabled",
    )
    installation_cost_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Installation cost as % of CapEx (overrides default 15%)",
    )
    annual_maintenance_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Annual maintenance cost as % of CapEx (overrides default 2%)",
    )

    # === Editable component cost assumptions (migration 1055) ===
    cost_per_panel_wp = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Solar panel cost per Wp (MWK). Default: 650",
    )
    cost_per_battery_kwh = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Battery cost per kWh (MWK). Default: 450,000",
    )
    cost_per_inverter_kw = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Inverter cost per kW (MWK). Default: 180,000",
    )
    cost_per_cc_amp = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Charge controller cost per Amp (MWK). Default: 12,000",
    )
    cost_wiring_lump = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Cable/wiring lump-sum (MWK). Default: 150,000",
    )
    cost_breakers_lump = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Breakers/protection lump-sum (MWK). Default: 80,000",
    )
    cost_mounting_lump = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Mounting structure lump-sum (MWK). Default: 50,000",
    )

    tariff_escalation_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.0"),
        help_text="Annual tariff/energy cost escalation (%)",
    )
    diesel_escalation_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("7.0"),
        help_text="Annual diesel price escalation (%)",
    )
    battery_replacement_year = models.PositiveSmallIntegerField(
        null=True, blank=True, default=10,
        help_text="Expected year for battery replacement",
    )
    battery_replacement_cost = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Estimated battery replacement cost (MWK)",
    )
    npv = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Net Present Value of the project (MWK)",
    )
    irr_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Internal Rate of Return (%)",
    )
    sensitivity_summary = models.JSONField(
        default=dict, blank=True,
        help_text="Sensitivity analysis results: {'pessimistic': {...}, 'base': {...}, 'optimistic': {...}}",
    )
    unmet_load_risk_pct = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Percentage of load that may go unmet (%)",
    )
    growth_headroom_pct = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Available capacity headroom for future growth (%)",
    )

    # Notes
    notes = models.TextField(blank=True, default="")
    assumptions = models.TextField(blank=True, default="")
    prepared_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="energy_sizing_runs"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "System Sizing Run"
        verbose_name_plural = "System Sizing Runs"

    def __str__(self):
        return f"{self.title} v{self.version}"

    @property
    def appliance_count(self) -> int:
        return self.appliances.count()

    @property
    def total_connected_load_w(self) -> Decimal:
        return sum(
            (a.wattage * a.quantity for a in self.appliances.all()),
            Decimal("0"),
        )

    def clone(self, new_title: str = "") -> "SystemSizingRun":
        """Create a new version/clone of this sizing run."""
        appliances = list(self.appliances.all())
        new = SystemSizingRun.objects.create(
            business=self.business,
            site=self.site,
            title=new_title or f"{self.title} (Copy)",
            version=self.version + 1,
            customer_name=self.customer_name,
            customer_phone=self.customer_phone,
            customer_email=self.customer_email,
            customer_address=self.customer_address,
            design_objective=self.design_objective,
            system_architecture=self.system_architecture,
            has_grid_access=self.has_grid_access,
            grid_reliability_pct=self.grid_reliability_pct,
            has_generator=self.has_generator,
            peak_sun_hours=self.peak_sun_hours,
            panel_wattage=self.panel_wattage,
            panel_efficiency_pct=self.panel_efficiency_pct,
            battery_dod_pct=self.battery_dod_pct,
            battery_voltage=self.battery_voltage,
            autonomy_days=self.autonomy_days,
            diversity_factor=self.diversity_factor,
            simultaneity_factor=self.simultaneity_factor,
            future_growth_pct=self.future_growth_pct,
            safety_margin_pct=self.safety_margin_pct,
            notes=self.notes,
            assumptions=self.assumptions,
            prepared_by=self.prepared_by,
        )
        for a in appliances:
            SizingAppliance.objects.create(
                sizing_run=new,
                name=a.name,
                category=a.category,
                quantity=a.quantity,
                wattage=a.wattage,
                surge_wattage=a.surge_wattage,
                hours_per_day=a.hours_per_day,
                days_per_week=a.days_per_week,
                priority=a.priority,
                load_type=a.load_type,
                is_critical=a.is_critical,
                usage_period=a.usage_period,
                efficiency_factor=a.efficiency_factor,
            )
        return new


class ApplianceCategory(models.TextChoices):
    LIGHTING     = "lighting",     "Lighting"
    ENTERTAINMENT = "entertainment", "Entertainment"
    REFRIGERATION = "refrigeration", "Refrigeration"
    COMPUTING    = "computing",    "Computing / Office"
    HVAC         = "hvac",         "HVAC / Cooling"
    PUMPING      = "pumping",      "Pumping"
    INDUSTRIAL   = "industrial",   "Industrial / Motors"
    MEDICAL      = "medical",      "Medical Equipment"
    TELECOM      = "telecom",      "Telecom Equipment"
    COOKING      = "cooking",      "Cooking"
    CHARGING     = "charging",     "Charging Stations"
    SECURITY     = "security",     "Security Systems"
    CUSTOM       = "custom",       "Custom / Other"


class LoadPriority(models.TextChoices):
    CRITICAL     = "critical",     "Critical (Must-Run)"
    HIGH         = "high",         "High Priority"
    MEDIUM       = "medium",       "Medium Priority"
    LOW          = "low",          "Low / Deferrable"


class SizingAppliance(models.Model):
    """
    Individual appliance / load entry within a system sizing run.
    Supports advanced scheduling: day/night, weekday/weekend, criticality.
    """

    sizing_run = models.ForeignKey(SystemSizingRun, on_delete=models.CASCADE, related_name="appliances")

    name = models.CharField(max_length=150, help_text="Appliance / load name")
    category = models.CharField(
        max_length=20, choices=ApplianceCategory.choices, default=ApplianceCategory.CUSTOM,
    )
    quantity = models.PositiveSmallIntegerField(default=1)

    # Power
    wattage = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Running wattage per unit (W)",
    )
    surge_wattage = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Surge / starting wattage per unit (W)",
    )

    # Schedule
    hours_per_day = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("1.0"),
        help_text="Hours of use per day",
    )
    days_per_week = models.PositiveSmallIntegerField(
        default=7, help_text="Days used per week (1–7)",
    )

    # Categorization
    priority = models.CharField(
        max_length=10, choices=LoadPriority.choices, default=LoadPriority.MEDIUM,
    )
    load_type = models.CharField(
        max_length=15,
        choices=[("resistive", "Resistive"), ("inductive", "Inductive"), ("electronic", "Electronic")],
        default="resistive",
    )
    is_critical = models.BooleanField(default=False, help_text="Must run during outage")
    usage_period = models.CharField(
        max_length=10,
        choices=[("day", "Daytime"), ("night", "Nighttime"), ("both", "Both")],
        default="both",
    )
    efficiency_factor = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00"),
        help_text="Efficiency correction (1.0 = no correction)",
    )

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Sizing Appliance"

    def __str__(self):
        return f"{self.quantity}x {self.name} ({self.wattage}W)"

    @property
    def daily_wh(self) -> Decimal:
        return self.wattage * self.quantity * self.hours_per_day * self.efficiency_factor

    @property
    def weekly_factor(self) -> Decimal:
        return Decimal(str(self.days_per_week)) / Decimal("7")

    @property
    def adjusted_daily_wh(self) -> Decimal:
        return self.daily_wh * self.weekly_factor

    @property
    def total_running_w(self) -> Decimal:
        return self.wattage * self.quantity

    @property
    def total_surge_w(self) -> Decimal:
        sw = self.surge_wattage or self.wattage
        return sw * self.quantity


# ---------------------------------------------------------------------------
# DemandForecast
# ---------------------------------------------------------------------------

class DemandForecast(models.Model):
    """
    Stored demand forecast record per site.
    [AI_HOOK] Replace rules-based engine with ML model output.
    """

    site = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="demand_forecasts")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_demand_forecasts")

    forecast_date = models.DateField(db_index=True, help_text="Date this forecast was generated")
    horizon_days = models.PositiveSmallIntegerField(default=7, help_text="Forecast horizon (days)")

    predicted_daily_kwh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    predicted_peak_kw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    confidence_pct = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Confidence level (0–100%)",
    )

    trend = models.CharField(
        max_length=15,
        choices=[("increasing", "Increasing"), ("stable", "Stable"), ("decreasing", "Decreasing")],
        blank=True, default="",
    )
    growth_rate_pct = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    overload_risk = models.BooleanField(default=False)
    explanation = models.TextField(blank=True, default="")

    # Method
    method = models.CharField(
        max_length=20,
        choices=[("rules", "Rules-Based"), ("statistical", "Statistical"), ("ml", "Machine Learning")],
        default="rules",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-forecast_date"]
        verbose_name = "Demand Forecast"

    def __str__(self):
        return f"{self.site.name} – {self.horizon_days}d forecast from {self.forecast_date}"


# ---------------------------------------------------------------------------
# TechnicianVisit
# ---------------------------------------------------------------------------

class TechnicianVisit(models.Model):
    """
    Field service visit record for technician operations.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_technician_visits")
    site = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="technician_visits")
    technician = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="energy_visits",
    )

    visit_type = models.CharField(
        max_length=20,
        choices=[
            ("installation", "Installation"),
            ("maintenance", "Scheduled Maintenance"),
            ("repair", "Repair / Fault Response"),
            ("inspection", "Inspection / Audit"),
            ("commissioning", "Commissioning"),
            ("decommission", "Decommissioning"),
            ("other", "Other"),
        ],
        default="maintenance",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("scheduled", "Scheduled"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="scheduled", db_index=True,
    )

    scheduled_date = models.DateField(db_index=True)
    completed_date = models.DateField(null=True, blank=True)

    description = models.TextField(blank=True, default="")
    diagnosis_notes = models.TextField(blank=True, default="")
    closure_notes = models.TextField(blank=True, default="")
    spare_parts_used = models.TextField(blank=True, default="")
    follow_up_date = models.DateField(null=True, blank=True)

    # Linked records
    related_alert = models.ForeignKey(
        EnergyAlert, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits",
    )
    related_maintenance = models.ForeignKey(
        AssetMaintenanceRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_date"]
        verbose_name = "Technician Visit"

    def __str__(self):
        return f"{self.get_visit_type_display()} at {self.site.name} – {self.scheduled_date}"


# ---------------------------------------------------------------------------
# LoadProfile
# ---------------------------------------------------------------------------

class LoadProfile(models.Model):
    """
    Load profile / analysis snapshot for a site.
    Tracks peak windows, utilization, and load management insights.
    """

    site = models.ForeignKey(EnergySite, on_delete=models.CASCADE, related_name="load_profiles")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_load_profiles")

    analysis_date = models.DateField(db_index=True)
    period_days = models.PositiveSmallIntegerField(default=30)

    # Metrics
    avg_daily_consumption_kwh = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    peak_demand_kw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    avg_demand_kw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    load_factor_pct = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Load factor = avg demand / peak demand * 100",
    )
    peak_window_start = models.TimeField(null=True, blank=True)
    peak_window_end = models.TimeField(null=True, blank=True)
    utilization_pct = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="System utilization (demand vs installed capacity)",
    )
    overload_events = models.PositiveSmallIntegerField(default=0)

    # Load breakdown (JSON)
    load_breakdown = models.JSONField(
        default=dict, blank=True,
        help_text="Category-wise load breakdown {'lighting': 30, 'hvac': 45, ...} in %",
    )
    recommendations = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-analysis_date"]
        verbose_name = "Load Profile"

    def __str__(self):
        return f"{self.site.name} – Load Profile {self.analysis_date}"


# ---------------------------------------------------------------------------
# EnergyDataUpload (Phase 2 — monitoring ingestion)
# ---------------------------------------------------------------------------

class EnergyDataUpload(models.Model):
    """
    Tracks CSV / bulk data uploads for energy readings.
    Supports data quality scoring and validation.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_data_uploads")
    site = models.ForeignKey(EnergySite, on_delete=models.CASCADE, null=True, blank=True, related_name="data_uploads")

    upload_type = models.CharField(
        max_length=20,
        choices=[("csv", "CSV Upload"), ("manual_batch", "Manual Batch"), ("api", "API Ingestion")],
        default="csv",
    )
    filename = models.CharField(max_length=255, blank=True, default="")
    rows_total = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    data_quality_score = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall data quality score (0-100)",
    )
    quality_notes = models.JSONField(default=list, blank=True)

    uploaded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="energy_uploads",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Energy Data Upload"

    def __str__(self):
        return f"{self.filename or 'Upload'} – {self.rows_imported}/{self.rows_total} rows"


# ---------------------------------------------------------------------------
# CopilotInsight (Phase 2 — energy copilot / intelligence panel)
# ---------------------------------------------------------------------------

class CopilotInsight(models.Model):
    """
    Rule-based intelligent insights for the Energy Copilot panel.
    Generated by periodic scans or on-demand analysis.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_copilot_insights")
    site = models.ForeignKey(EnergySite, on_delete=models.CASCADE, null=True, blank=True, related_name="copilot_insights")
    asset = models.ForeignKey(EnergyAsset, on_delete=models.CASCADE, null=True, blank=True, related_name="copilot_insights")

    category = models.CharField(
        max_length=30,
        choices=[
            ("performance", "Performance"),
            ("cost", "Cost / Savings"),
            ("maintenance", "Maintenance"),
            ("capacity", "Capacity / Sizing"),
            ("risk", "Risk / Safety"),
            ("opportunity", "Opportunity"),
        ],
        db_index=True,
    )
    severity = models.CharField(max_length=10, choices=AlertSeverity.choices, default=AlertSeverity.LOW)
    title = models.CharField(max_length=300)
    explanation = models.TextField(blank=True, default="")
    suggested_action = models.TextField(blank=True, default="")
    is_dismissed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Copilot Insight"

    def __str__(self):
        return f"[{self.category}] {self.title}"


# ---------------------------------------------------------------------------
# Energy Commerce — Retail Product Catalog, Stock-In & Sales
# ---------------------------------------------------------------------------

class EnergyProductCategory(models.TextChoices):
    SOLAR_PANEL        = "solar_panel",        "Solar Panels"
    BATTERY            = "battery",            "Batteries"
    INVERTER           = "inverter",           "Inverters"
    CHARGE_CONTROLLER  = "charge_controller",  "Charge Controllers"
    SOLAR_LIGHT        = "solar_light",        "Solar Lights & Bulbs"
    CABLE_WIRE         = "cable_wire",         "Cables & Wiring"
    BREAKER            = "breaker",            "Breakers & Protection"
    MOUNTING           = "mounting",           "Mounting Accessories"
    CONNECTOR          = "connector",          "Connectors (MC4 etc.)"
    GAS_COOKER         = "gas_cooker",         "Gas Cookers"
    GAS_CYLINDER       = "gas_cylinder",       "Gas Cylinders"
    GAS_REGULATOR      = "gas_regulator",      "Gas Regulators"
    ENERGY_METER       = "energy_meter",       "Energy Meters"
    PUMP               = "pump",               "Pumps"
    BACKUP_KIT         = "backup_kit",         "Backup / Mini-Grid Kits"
    OTHER              = "other",              "Other"


class EnergyProduct(models.Model):
    """Retail energy product available for sale."""

    business         = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_products")
    name             = models.CharField(max_length=200)
    category         = models.CharField(max_length=50, choices=EnergyProductCategory.choices, default=EnergyProductCategory.OTHER)
    sku              = models.CharField(max_length=100, blank=True, default="")
    unit             = models.CharField(max_length=30, default="unit", help_text="e.g. unit, metre, kg, set")
    cost_price       = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    selling_price    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    quantity_in_stock = models.PositiveIntegerField(default=0)
    reorder_level    = models.PositiveIntegerField(default=2)
    description      = models.TextField(blank=True, default="")
    is_active        = models.BooleanField(default=True)
    is_seeded        = models.BooleanField(default=False, help_text="Auto-seeded catalog item")
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventory"
        ordering = ["category", "name"]
        unique_together = [["business", "name", "category"]]
        verbose_name = "Energy Product"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_category_display()})"

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_in_stock <= self.reorder_level

    @property
    def inventory_value(self) -> Decimal:
        return self.cost_price * self.quantity_in_stock


class EnergyStockIn(models.Model):
    """A stock-in event (goods received) for an energy product."""

    business      = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_stock_ins")
    product       = models.ForeignKey(EnergyProduct, on_delete=models.CASCADE, related_name="stock_ins")
    quantity      = models.PositiveIntegerField()
    cost_price    = models.DecimalField(max_digits=14, decimal_places=2)
    supplier      = models.CharField(max_length=200, blank=True, default="")
    notes         = models.TextField(blank=True, default="")
    received_date = models.DateField()
    recorded_by   = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "inventory"
        ordering = ["-created_at"]
        verbose_name = "Energy Stock-In"

    def __str__(self) -> str:
        return f"Stock-in: {self.product.name} ×{self.quantity} ({self.received_date})"

    @property
    def total_cost(self) -> Decimal:
        return self.cost_price * self.quantity


class EnergyItemSale(models.Model):
    """A completed retail sale of an energy product."""

    PAYMENT_CHOICES = [
        ("CASH",         "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("BANK",         "Bank Transfer"),
        ("CREDIT",       "Credit"),
        ("OTHER",        "Other"),
    ]

    business        = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="energy_item_sales")
    product         = models.ForeignKey(EnergyProduct, on_delete=models.CASCADE, related_name="sales")
    quantity        = models.PositiveIntegerField(default=1)
    unit_price      = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost       = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_amount    = models.DecimalField(max_digits=14, decimal_places=2, editable=False, default=Decimal("0.00"))
    profit          = models.DecimalField(max_digits=14, decimal_places=2, editable=False, default=Decimal("0.00"))
    payment_method  = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="CASH")
    customer_name   = models.CharField(max_length=200, blank=True, default="")
    notes           = models.TextField(blank=True, default="")
    sold_by         = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    sold_at         = models.DateTimeField(auto_now_add=True)
    is_reversed     = models.BooleanField(default=False)

    class Meta:
        app_label = "inventory"
        ordering = ["-sold_at"]
        verbose_name = "Energy Item Sale"

    def save(self, *args, **kwargs):
        self.total_amount = self.unit_price * self.quantity
        self.profit = (self.unit_price - self.unit_cost) * self.quantity
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Sale: {self.product.name} ×{self.quantity} @ {self.total_amount}"


__all__ = [
    "SiteType", "SiteStatus", "AssetType", "AssetStatus",
    "MaintenanceType", "AlertSeverity", "AlertType",
    "EnergySite", "EnergyAsset", "AssetMaintenanceRecord",
    "EnergyReading", "SavingsRecord", "EnergyAlert",
    "SizingObjective", "SystemArchitecture",
    "SystemSizingRun", "ApplianceCategory", "LoadPriority", "SizingAppliance",
    "DemandForecast", "TechnicianVisit", "LoadProfile",
    "EnergyDataUpload", "CopilotInsight",
    # Commerce
    "EnergyProductCategory", "EnergyProduct", "EnergyStockIn", "EnergyItemSale",
]
