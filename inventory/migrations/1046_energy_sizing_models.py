# inventory/migrations/1046_energy_sizing_models.py
"""
Adds flagship energy sizing models and supporting tables:
- SystemSizingRun
- SizingAppliance
- DemandForecast
- TechnicianVisit
- LoadProfile
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1045_energy_models"),
        ("tenants", "0033_energy_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # SystemSizingRun
        migrations.CreateModel(
            name="SystemSizingRun",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=250, help_text="Proposal / sizing run title")),
                ("version", models.PositiveSmallIntegerField(default=1)),
                ("reference_code", models.CharField(blank=True, default="", max_length=50)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("final", "Final"), ("archived", "Archived")], db_index=True, default="draft", max_length=20)),
                ("customer_name", models.CharField(blank=True, default="", max_length=200)),
                ("customer_phone", models.CharField(blank=True, default="", max_length=30)),
                ("customer_email", models.EmailField(blank=True, default="", max_length=254)),
                ("customer_address", models.CharField(blank=True, default="", max_length=300)),
                ("design_objective", models.CharField(choices=[("lowest_cost", "Lowest Cost"), ("balanced", "Balanced System"), ("high_reliability", "High Reliability"), ("backup_first", "Backup-First"), ("savings_first", "Savings-First"), ("growth_ready", "Growth-Ready"), ("off_grid", "Off-Grid"), ("hybrid", "Hybrid"), ("grid_tied_backup", "Grid-Tied with Backup"), ("mini_grid", "Mini-Grid Concept")], default="balanced", max_length=20)),
                ("system_architecture", models.CharField(choices=[("solar_only", "Solar Only"), ("solar_battery", "Solar + Battery"), ("solar_grid", "Solar + Grid"), ("solar_batt_grid", "Solar + Battery + Grid"), ("solar_gen", "Solar + Generator"), ("solar_batt_gen", "Solar + Battery + Generator"), ("hybrid_full", "Full Hybrid (Solar+Battery+Grid+Gen)"), ("wind_solar", "Wind + Solar (Placeholder)")], default="solar_battery", max_length=20)),
                ("has_grid_access", models.BooleanField(default=True)),
                ("grid_reliability_pct", models.PositiveSmallIntegerField(default=80)),
                ("has_generator", models.BooleanField(default=False)),
                ("generator_fuel_cost_per_litre", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("generator_litres_per_hour", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("peak_sun_hours", models.DecimalField(decimal_places=1, default=Decimal("5.0"), max_digits=4)),
                ("panel_wattage", models.PositiveSmallIntegerField(default=550)),
                ("panel_efficiency_pct", models.PositiveSmallIntegerField(default=85)),
                ("battery_dod_pct", models.PositiveSmallIntegerField(default=80)),
                ("battery_voltage", models.PositiveSmallIntegerField(default=48)),
                ("autonomy_days", models.DecimalField(decimal_places=1, default=Decimal("1.0"), max_digits=3)),
                ("diversity_factor", models.DecimalField(decimal_places=2, default=Decimal("0.80"), max_digits=4)),
                ("simultaneity_factor", models.DecimalField(decimal_places=2, default=Decimal("0.70"), max_digits=4)),
                ("future_growth_pct", models.PositiveSmallIntegerField(default=20)),
                ("safety_margin_pct", models.PositiveSmallIntegerField(default=15)),
                ("total_daily_demand_wh", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("total_daily_demand_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("peak_load_w", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("surge_load_w", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("corrected_design_load_wh", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("recommended_array_kw", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("recommended_panel_count", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("recommended_battery_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("usable_storage_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("recommended_inverter_kw", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("inverter_loading_pct", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("recommended_charge_controller_a", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("recommended_generator_kva", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("estimated_runtime_hours", models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True)),
                ("estimated_capex", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("estimated_installation_cost", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("estimated_annual_maintenance", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("projected_monthly_savings", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("projected_annual_savings", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("payback_years", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("roi_pct", models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True)),
                ("lifetime_cost_estimate", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("cost_per_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("diesel_offset_monthly", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("grid_savings_monthly", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("recommendations", models.JSONField(blank=True, default=list)),
                ("warnings", models.JSONField(blank=True, default=list)),
                ("component_summary", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True, default="")),
                ("assumptions", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_sizing_runs", to="tenants.business")),
                ("site", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sizing_runs", to="inventory.energysite")),
                ("prepared_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="energy_sizing_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
                "verbose_name": "System Sizing Run",
                "verbose_name_plural": "System Sizing Runs",
            },
        ),
        # SizingAppliance
        migrations.CreateModel(
            name="SizingAppliance",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("category", models.CharField(choices=[("lighting", "Lighting"), ("entertainment", "Entertainment"), ("refrigeration", "Refrigeration"), ("computing", "Computing / Office"), ("hvac", "HVAC / Cooling"), ("pumping", "Pumping"), ("industrial", "Industrial / Motors"), ("medical", "Medical Equipment"), ("telecom", "Telecom Equipment"), ("cooking", "Cooking"), ("charging", "Charging Stations"), ("security", "Security Systems"), ("custom", "Custom / Other")], default="custom", max_length=20)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("wattage", models.DecimalField(decimal_places=2, max_digits=10)),
                ("surge_wattage", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("hours_per_day", models.DecimalField(decimal_places=1, default=Decimal("1.0"), max_digits=4)),
                ("days_per_week", models.PositiveSmallIntegerField(default=7)),
                ("priority", models.CharField(choices=[("critical", "Critical (Must-Run)"), ("high", "High Priority"), ("medium", "Medium Priority"), ("low", "Low / Deferrable")], default="medium", max_length=10)),
                ("load_type", models.CharField(choices=[("resistive", "Resistive"), ("inductive", "Inductive"), ("electronic", "Electronic")], default="resistive", max_length=15)),
                ("is_critical", models.BooleanField(default=False)),
                ("usage_period", models.CharField(choices=[("day", "Daytime"), ("night", "Nighttime"), ("both", "Both")], default="both", max_length=10)),
                ("efficiency_factor", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=4)),
                ("sizing_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="appliances", to="inventory.systemsizingrun")),
            ],
            options={
                "ordering": ["category", "name"],
                "verbose_name": "Sizing Appliance",
            },
        ),
        # DemandForecast
        migrations.CreateModel(
            name="DemandForecast",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("forecast_date", models.DateField(db_index=True)),
                ("horizon_days", models.PositiveSmallIntegerField(default=7)),
                ("predicted_daily_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("predicted_peak_kw", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("confidence_pct", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("trend", models.CharField(blank=True, choices=[("increasing", "Increasing"), ("stable", "Stable"), ("decreasing", "Decreasing")], default="", max_length=15)),
                ("growth_rate_pct", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("overload_risk", models.BooleanField(default=False)),
                ("explanation", models.TextField(blank=True, default="")),
                ("method", models.CharField(choices=[("rules", "Rules-Based"), ("statistical", "Statistical"), ("ml", "Machine Learning")], default="rules", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_demand_forecasts", to="tenants.business")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="demand_forecasts", to="inventory.energysite")),
            ],
            options={
                "ordering": ["-forecast_date"],
                "verbose_name": "Demand Forecast",
            },
        ),
        # TechnicianVisit
        migrations.CreateModel(
            name="TechnicianVisit",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visit_type", models.CharField(choices=[("installation", "Installation"), ("maintenance", "Scheduled Maintenance"), ("repair", "Repair / Fault Response"), ("inspection", "Inspection / Audit"), ("commissioning", "Commissioning"), ("decommission", "Decommissioning"), ("other", "Other")], default="maintenance", max_length=20)),
                ("status", models.CharField(choices=[("scheduled", "Scheduled"), ("in_progress", "In Progress"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="scheduled", max_length=20)),
                ("scheduled_date", models.DateField(db_index=True)),
                ("completed_date", models.DateField(blank=True, null=True)),
                ("description", models.TextField(blank=True, default="")),
                ("diagnosis_notes", models.TextField(blank=True, default="")),
                ("closure_notes", models.TextField(blank=True, default="")),
                ("spare_parts_used", models.TextField(blank=True, default="")),
                ("follow_up_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_technician_visits", to="tenants.business")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="technician_visits", to="inventory.energysite")),
                ("technician", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="energy_visits", to=settings.AUTH_USER_MODEL)),
                ("related_alert", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="inventory.energyalert")),
                ("related_maintenance", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="inventory.assetmaintenancerecord")),
            ],
            options={
                "ordering": ["-scheduled_date"],
                "verbose_name": "Technician Visit",
            },
        ),
        # LoadProfile
        migrations.CreateModel(
            name="LoadProfile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("analysis_date", models.DateField(db_index=True)),
                ("period_days", models.PositiveSmallIntegerField(default=30)),
                ("avg_daily_consumption_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("peak_demand_kw", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("avg_demand_kw", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("load_factor_pct", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("peak_window_start", models.TimeField(blank=True, null=True)),
                ("peak_window_end", models.TimeField(blank=True, null=True)),
                ("utilization_pct", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("overload_events", models.PositiveSmallIntegerField(default=0)),
                ("load_breakdown", models.JSONField(blank=True, default=dict)),
                ("recommendations", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_load_profiles", to="tenants.business")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="load_profiles", to="inventory.energysite")),
            ],
            options={
                "ordering": ["-analysis_date"],
                "verbose_name": "Load Profile",
            },
        ),
    ]
