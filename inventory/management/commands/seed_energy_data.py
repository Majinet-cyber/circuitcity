# inventory/management/commands/seed_energy_data.py
"""
Management command: seed rich, realistic Renewable Energy data for demo/testing.

This creates a comprehensive, investor-worthy demo dataset that shows the full
power of the Emajinet Energy Intelligence Platform.

Usage:
    python manage.py seed_energy_data
    python manage.py seed_energy_data --business 3
    python manage.py seed_energy_data --force   (re-seed even if data exists)

Seeded data includes:
  - 10 realistic sites (mini-grid, rooftop, solar farm, clinic, school, etc.)
  - 5+ assets per site with realistic health scores and specs
  - 90 days of generation/consumption readings per site
  - Monthly savings records
  - Active and resolved energy alerts
  - Demand forecasts
  - Copilot insights
  - Technician visit records
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone


# ---------------------------------------------------------------------------
# Demo Sites — realistic Malawi / Africa energy installations
# ---------------------------------------------------------------------------

DEMO_SITES = [
    {
        "name": "Mzuzu Commercial Hub – Block A",
        "site_type": "commercial",
        "status": "active",
        "installed_capacity_kw": Decimal("15.0"),
        "location": "Industrial Road, Mzuzu, Malawi",
        "customer_name": "ABC Trading Ltd",
        "customer_phone": "+265 999 100 001",
        "installation_cost": Decimal("4500000"),
        "monthly_grid_bill_before": Decimal("380000"),
        "commissioning_days_ago": 420,
        "energy_sources": ["solar", "battery", "grid"],
        "base_gen_kwh": 85.0,
    },
    {
        "name": "Lilongwe Residential Estate",
        "site_type": "household",
        "status": "active",
        "installed_capacity_kw": Decimal("5.0"),
        "location": "Area 49, Lilongwe",
        "customer_name": "Mr. Chikumbu Banda",
        "customer_phone": "+265 888 200 002",
        "installation_cost": Decimal("1800000"),
        "monthly_grid_bill_before": Decimal("95000"),
        "commissioning_days_ago": 280,
        "energy_sources": ["solar", "battery"],
        "base_gen_kwh": 22.0,
    },
    {
        "name": "Blantyre Health Clinic",
        "site_type": "community",
        "status": "active",
        "installed_capacity_kw": Decimal("20.0"),
        "location": "Ndirande, Blantyre",
        "customer_name": "Ministry of Health – Blantyre District",
        "customer_phone": "+265 111 300 003",
        "installation_cost": Decimal("7500000"),
        "monthly_grid_bill_before": Decimal("620000"),
        "commissioning_days_ago": 550,
        "energy_sources": ["solar", "battery", "generator"],
        "base_gen_kwh": 110.0,
    },
    {
        "name": "Kasungu Poultry Farm",
        "site_type": "agricultural",
        "status": "active",
        "installed_capacity_kw": Decimal("12.0"),
        "location": "Kasungu, Central Region",
        "customer_name": "Sunrise Poultry Ltd",
        "customer_phone": "+265 888 400 004",
        "installation_cost": Decimal("3800000"),
        "monthly_grid_bill_before": Decimal("280000"),
        "commissioning_days_ago": 190,
        "energy_sources": ["solar", "battery", "generator"],
        "base_gen_kwh": 65.0,
    },
    {
        "name": "Salima Irrigation Scheme",
        "site_type": "agricultural",
        "status": "active",
        "installed_capacity_kw": Decimal("30.0"),
        "location": "Salima, Lakeshore District",
        "customer_name": "Salima Smallholder Farmers Co-op",
        "customer_phone": "+265 999 500 005",
        "installation_cost": Decimal("9200000"),
        "monthly_grid_bill_before": Decimal("0"),
        "commissioning_days_ago": 310,
        "energy_sources": ["solar", "battery"],
        "base_gen_kwh": 155.0,
    },
    {
        "name": "Mchinji Telecom Tower Backup",
        "site_type": "commercial",
        "status": "active",
        "installed_capacity_kw": Decimal("8.0"),
        "location": "Mchinji Border Town",
        "customer_name": "TelMal Networks",
        "customer_phone": "+265 777 600 006",
        "installation_cost": Decimal("2900000"),
        "monthly_grid_bill_before": Decimal("190000"),
        "commissioning_days_ago": 480,
        "energy_sources": ["solar", "battery"],
        "base_gen_kwh": 42.0,
    },
    {
        "name": "Zomba Secondary School",
        "site_type": "community",
        "status": "active",
        "installed_capacity_kw": Decimal("10.0"),
        "location": "Zomba City",
        "customer_name": "Zomba Poly Secondary School",
        "customer_phone": "+265 888 700 007",
        "installation_cost": Decimal("3200000"),
        "monthly_grid_bill_before": Decimal("160000"),
        "commissioning_days_ago": 225,
        "energy_sources": ["solar", "battery", "grid"],
        "base_gen_kwh": 52.0,
    },
    {
        "name": "Dedza Community Mini-Grid",
        "site_type": "community",
        "status": "active",
        "installed_capacity_kw": Decimal("50.0"),
        "location": "Dedza Boma, Central Region",
        "customer_name": "Dedza District Rural Electrification",
        "customer_phone": "+265 111 800 008",
        "installation_cost": Decimal("18500000"),
        "monthly_grid_bill_before": Decimal("0"),
        "commissioning_days_ago": 380,
        "energy_sources": ["solar", "battery", "generator"],
        "base_gen_kwh": 280.0,
    },
    {
        "name": "Nkhata Bay Fishing Cold Room",
        "site_type": "commercial",
        "status": "active",
        "installed_capacity_kw": Decimal("18.0"),
        "location": "Nkhata Bay, Northern Region",
        "customer_name": "Lake Fish Processors Ltd",
        "customer_phone": "+265 999 900 009",
        "installation_cost": Decimal("5800000"),
        "monthly_grid_bill_before": Decimal("420000"),
        "commissioning_days_ago": 145,
        "energy_sources": ["solar", "battery", "generator"],
        "base_gen_kwh": 95.0,
    },
    {
        "name": "Balaka Manufacturing Plant",
        "site_type": "industrial",
        "status": "active",
        "installed_capacity_kw": Decimal("75.0"),
        "location": "Balaka Industrial Zone",
        "customer_name": "Southern Manufacturing Co.",
        "customer_phone": "+265 777 100 010",
        "installation_cost": Decimal("28000000"),
        "monthly_grid_bill_before": Decimal("1850000"),
        "commissioning_days_ago": 520,
        "energy_sources": ["solar", "battery", "grid", "generator"],
        "base_gen_kwh": 420.0,
    },
]

# ---------------------------------------------------------------------------
# Assets per site type
# ---------------------------------------------------------------------------

SITE_ASSETS = {
    "commercial_small": [
        {"asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S30-540/MR",   "capacity": Decimal("0.54"),  "capacity_unit": "kW",  "health": 92, "quantity": 28},
        {"asset_type": "battery",           "brand": "Pylontech",   "model_name": "US5000C",           "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "health": 84},
        {"asset_type": "inverter",          "brand": "Deye",        "model_name": "SUN-15K-SG04LP3",   "capacity": Decimal("15.0"),  "capacity_unit": "kW",  "health": 97},
        {"asset_type": "charge_controller", "brand": "Victron",     "model_name": "SmartSolar 150/70", "capacity": Decimal("70.0"),  "capacity_unit": "A",   "health": 91},
        {"asset_type": "meter",             "brand": "Landis+Gyr",  "model_name": "E350",              "capacity": None,             "capacity_unit": "—",   "health": 100},
    ],
    "household": [
        {"asset_type": "solar_panel",       "brand": "Canadian Solar", "model_name": "CS6L-450MS",    "capacity": Decimal("0.45"),  "capacity_unit": "kW",  "health": 88, "quantity": 12},
        {"asset_type": "battery",           "brand": "Felicity",    "model_name": "LPBA48200",         "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "health": 58},
        {"asset_type": "inverter",          "brand": "Growatt",     "model_name": "MIN5000TL-X",       "capacity": Decimal("5.0"),   "capacity_unit": "kW",  "health": 90},
    ],
    "clinic": [
        {"asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S30-540/MR",   "capacity": Decimal("0.54"),  "capacity_unit": "kW",  "health": 95, "quantity": 37},
        {"asset_type": "battery",           "brand": "Pylontech",   "model_name": "US5000C",           "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "health": 82},
        {"asset_type": "battery",           "brand": "Pylontech",   "model_name": "US5000C",           "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "health": 79},
        {"asset_type": "inverter",          "brand": "Deye",        "model_name": "SUN-20K-SG04LP3",   "capacity": Decimal("20.0"),  "capacity_unit": "kW",  "health": 98},
        {"asset_type": "meter",             "brand": "Landis+Gyr",  "model_name": "E350",              "capacity": None,             "capacity_unit": "—",   "health": 100},
        {"asset_type": "generator",         "brand": "Lister",      "model_name": "LD10",              "capacity": Decimal("10.0"),  "capacity_unit": "kVA", "health": 68},
    ],
    "agricultural": [
        {"asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S20-460/MR",   "capacity": Decimal("0.46"),  "capacity_unit": "kW",  "health": 87, "quantity": 26},
        {"asset_type": "battery",           "brand": "Pylontech",   "model_name": "US3000C",           "capacity": Decimal("3.55"),  "capacity_unit": "kWh", "health": 75},
        {"asset_type": "inverter",          "brand": "Victron",     "model_name": "Quattro 48/15000",  "capacity": Decimal("15.0"),  "capacity_unit": "kW",  "health": 93},
        {"asset_type": "charge_controller", "brand": "Victron",     "model_name": "MPPT 250/100",      "capacity": Decimal("100.0"), "capacity_unit": "A",   "health": 88},
        {"asset_type": "sensor",            "brand": "Davis",       "model_name": "Vue Weather Station","capacity": None,            "capacity_unit": "—",   "health": 100},
    ],
    "mini_grid": [
        {"asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S30-540/MR",   "capacity": Decimal("0.54"),  "capacity_unit": "kW",  "health": 91, "quantity": 93},
        {"asset_type": "battery",           "brand": "BYD",         "model_name": "B-Box Premium LVS", "capacity": Decimal("15.36"), "capacity_unit": "kWh", "health": 89},
        {"asset_type": "battery",           "brand": "BYD",         "model_name": "B-Box Premium LVS", "capacity": Decimal("15.36"), "capacity_unit": "kWh", "health": 86},
        {"asset_type": "inverter",          "brand": "Sungrow",     "model_name": "SH50K-20",          "capacity": Decimal("50.0"),  "capacity_unit": "kW",  "health": 96},
        {"asset_type": "generator",         "brand": "Cummins",     "model_name": "C25D5",             "capacity": Decimal("25.0"),  "capacity_unit": "kVA", "health": 72},
        {"asset_type": "meter",             "brand": "Landis+Gyr",  "model_name": "E660",              "capacity": None,             "capacity_unit": "—",   "health": 99},
    ],
    "industrial": [
        {"asset_type": "solar_panel",       "brand": "LONGi",       "model_name": "LR4-72HBD-535M",    "capacity": Decimal("0.535"), "capacity_unit": "kW",  "health": 94, "quantity": 140},
        {"asset_type": "battery",           "brand": "CATL",        "model_name": "EnerOne 100kWh",    "capacity": Decimal("100.0"), "capacity_unit": "kWh", "health": 91},
        {"asset_type": "inverter",          "brand": "Huawei",      "model_name": "SUN2000-100KTL-M1", "capacity": Decimal("100.0"), "capacity_unit": "kW",  "health": 97},
        {"asset_type": "charge_controller", "brand": "SolarEdge",   "model_name": "SE100K",            "capacity": Decimal("100.0"), "capacity_unit": "kW",  "health": 95},
        {"asset_type": "generator",         "brand": "Cummins",     "model_name": "C55D5",             "capacity": Decimal("55.0"),  "capacity_unit": "kVA", "health": 80},
        {"asset_type": "meter",             "brand": "ABB",         "model_name": "A41 3-Phase",       "capacity": None,             "capacity_unit": "—",   "health": 100},
    ],
}

SITE_ASSET_MAP = {
    0: "commercial_small",  # Mzuzu Commercial Hub
    1: "household",          # Lilongwe Residential
    2: "clinic",             # Blantyre Clinic
    3: "agricultural",       # Kasungu Poultry
    4: "agricultural",       # Salima Irrigation
    5: "commercial_small",   # Mchinji Telecom
    6: "commercial_small",   # Zomba School
    7: "mini_grid",          # Dedza Mini-Grid
    8: "agricultural",       # Nkhata Bay Cold Room
    9: "industrial",         # Balaka Manufacturing
}

# ---------------------------------------------------------------------------
# Alerts seed data
# ---------------------------------------------------------------------------

DEMO_ALERTS = [
    {"site_idx": 1, "alert_type": "low_battery_health",   "severity": "high",     "title": "Battery health at 58% — approaching replacement threshold", "suggested_action": "Schedule battery inspection and capacity test. Budget for replacement in 6 months.", "is_resolved": False},
    {"site_idx": 2, "alert_type": "maintenance_due",      "severity": "medium",   "title": "Generator maintenance overdue by 45 days", "suggested_action": "Schedule oil change and service. Check fuel filters.", "is_resolved": False},
    {"site_idx": 3, "alert_type": "low_generation",       "severity": "medium",   "title": "Panel string 3 generating 14% below expected output", "suggested_action": "Clean panels. Check MC4 connectors and string fuse.", "is_resolved": False},
    {"site_idx": 7, "alert_type": "demand_spike",         "severity": "high",     "title": "Demand spike detected at 18:30 — 38% above daily average", "suggested_action": "Identify high-load users. Consider time-of-use tariff or load control switch.", "is_resolved": False},
    {"site_idx": 9, "alert_type": "overload_risk",        "severity": "critical", "title": "Inverter loading at 94% — overload risk if new machinery starts", "suggested_action": "Increase inverter capacity or defer high-load equipment start times.", "is_resolved": False},
    {"site_idx": 0, "alert_type": "asset_degraded",       "severity": "medium",   "title": "Charge controller efficiency down 7% — check connections", "suggested_action": "Inspect MPPT connections and firmware version.", "is_resolved": False},
    {"site_idx": 4, "alert_type": "data_missing",         "severity": "low",      "title": "No readings submitted for 3 days — monitoring gap", "suggested_action": "Ask site technician to submit daily meter readings.", "is_resolved": True},
    {"site_idx": 5, "alert_type": "unusual_consumption",  "severity": "medium",   "title": "Night-time consumption 22% higher than usual — possible equipment fault", "suggested_action": "Inspect site for equipment left on. Check for meter tampering.", "is_resolved": True},
]

# ---------------------------------------------------------------------------
# Copilot Insights seed data
# ---------------------------------------------------------------------------

DEMO_INSIGHTS = [
    {"site_idx": 1, "category": "maintenance", "severity": "high",     "title": "Battery bank imbalance detected — string 2 showing 12% lower SOC", "explanation": "Pylontech US5000C in string 2 consistently shows lower state-of-charge compared to strings 1 and 3. This suggests early cell degradation or connection resistance.", "suggested_action": "Perform capacity test on string 2. Check BMS balancing status. Consider cell replacement within 3 months."},
    {"site_idx": 0, "category": "performance", "severity": "medium",   "title": "Inverter efficiency dropped 8% over past 30 days", "explanation": "DC-to-AC conversion efficiency has declined from 96.2% to 88.4% based on generation vs consumption ratios.", "suggested_action": "Check inverter cooling fans and firmware. Clean heat sinks. Verify no harmonic distortion from connected loads."},
    {"site_idx": 3, "category": "capacity",    "severity": "medium",   "title": "System running near full capacity during peak farming season", "explanation": "Load factor reached 87% during peak irrigation hours (08:00–11:00). System was designed for 75% max.", "suggested_action": "Consider adding 3 kW of solar capacity before next farming season. ROI: 14 months."},
    {"site_idx": 7, "category": "opportunity", "severity": "low",      "title": "Load factor at 62% — room for 3 additional productive-use connections", "explanation": "Mini-grid has 38% spare capacity during off-peak hours. Adding a grain mill or water pump would improve financial viability.", "suggested_action": "Approach community leaders about adding a cereal milling unit. Estimated additional revenue: MWK 45,000/month."},
    {"site_idx": 9, "category": "cost",        "severity": "low",      "title": "Generator running 4.2 hours/day — potential MWK 180,000/month fuel savings", "explanation": "Generator starts automatically at 18:30 daily before batteries reach minimum. Adding battery capacity could defer this.", "suggested_action": "Add 50 kWh battery capacity to eliminate 3 of the 4.2 daily generator hours. Payback: 18 months."},
]


class Command(BaseCommand):
    help = "Seed comprehensive, realistic Renewable Energy demo data for the Emajinet platform"

    def add_arguments(self, parser):
        parser.add_argument("--business", type=int, default=None, help="Limit to specific business ID")
        parser.add_argument("--force", action="store_true", help="Re-seed even if data exists")
        parser.add_argument("--days", type=int, default=90, help="Days of historical readings to generate (default: 90)")

    def handle(self, *args, **options):
        business_id = options.get("business")
        force = options.get("force", False)
        history_days = options.get("days", 90)

        try:
            from inventory.models_energy import (
                EnergySite, EnergyAsset, EnergyReading, SavingsRecord,
                EnergyAlert, CopilotInsight, TechnicianVisit, DemandForecast,
                SiteType, AssetType, AssetStatus, SiteStatus,
                AlertType, AlertSeverity,
            )
        except ImportError:
            self.stderr.write(self.style.ERROR("Energy models not available. Run migrations first."))
            return

        try:
            from tenants.models import Business
        except ImportError:
            self.stderr.write(self.style.ERROR("tenants.models not available."))
            return

        qs = Business.objects.filter(business_kind="energy")
        if business_id:
            qs = qs.filter(pk=business_id)

        if not qs.exists():
            self.stdout.write(self.style.WARNING(
                "No energy businesses found. Create a business with kind='energy' first, "
                "then re-run this command."
            ))
            return

        today = timezone.now().date()

        for biz in qs:
            existing_sites = EnergySite.objects.filter(business=biz).count()
            if existing_sites >= 5 and not force:
                self.stdout.write(
                    f"  Skipping {biz.name} — already has {existing_sites} sites (use --force to re-seed)"
                )
                continue

            self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
            self.stdout.write(self.style.SUCCESS(f"Seeding energy data for: {biz.name}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*60}"))

            # ── Seed sites ──────────────────────────────────────────────
            sites = []
            for sdata in DEMO_SITES:
                commission_date = today - timedelta(days=sdata.get("commissioning_days_ago", 365))
                site, created = EnergySite.objects.update_or_create(
                    business=biz,
                    name=sdata["name"],
                    defaults={
                        "site_type": sdata["site_type"],
                        "status": sdata["status"],
                        "installed_capacity_kw": sdata["installed_capacity_kw"],
                        "location": sdata.get("location", ""),
                        "customer_name": sdata.get("customer_name", ""),
                        "customer_phone": sdata.get("customer_phone", ""),
                        "installation_cost": sdata.get("installation_cost", Decimal("0")),
                        "monthly_grid_bill_before": sdata.get("monthly_grid_bill_before", Decimal("0")),
                        "commissioning_date": commission_date,
                        "energy_sources": sdata.get("energy_sources", ["solar"]),
                    },
                )
                sites.append(site)
                self.stdout.write(f"  Site: {site.name} ({'created' if created else 'updated'})")

            # ── Seed assets ──────────────────────────────────────────────
            assets_created = 0
            for site_idx, site in enumerate(sites):
                asset_template_key = SITE_ASSET_MAP.get(site_idx, "commercial_small")
                asset_templates = SITE_ASSETS.get(asset_template_key, [])
                install_date = today - timedelta(days=DEMO_SITES[site_idx].get("commissioning_days_ago", 365))

                for adata in asset_templates:
                    asset, created = EnergyAsset.objects.get_or_create(
                        business=biz,
                        site=site,
                        asset_type=adata["asset_type"],
                        brand=adata["brand"],
                        model_name=adata["model_name"],
                        defaults={
                            "capacity": adata["capacity"],
                            "capacity_unit": adata["capacity_unit"],
                            "status": (
                                "degraded" if adata["health"] < 65
                                else "maintenance" if adata["health"] < 70
                                else "operational"
                            ),
                            "health_score": adata["health"],
                            "install_date": install_date,
                            "maintenance_interval_days": 180,
                            "expected_lifespan_years": 10 if adata["asset_type"] == "battery" else 25,
                        },
                    )
                    if created:
                        assets_created += 1

            self.stdout.write(f"  Assets: {assets_created} created")

            # ── Seed energy readings (per-site, realistic simulation) ────────
            readings_created = 0
            for site_idx, site in enumerate(sites):
                base_gen = DEMO_SITES[site_idx]["base_gen_kwh"]
                rng = random.Random(biz.pk * 31 + site_idx * 17)

                for days_ago in range(history_days - 1, -1, -1):
                    reading_date = today - timedelta(days=days_ago)
                    day_of_year = reading_date.timetuple().tm_yday

                    # Seasonal variation: higher in dry season (Apr–Oct), lower in wet season
                    seasonal_factor = 1.0 + 0.15 * math.sin((day_of_year - 90) * math.pi / 183)

                    # Weather variation
                    weather = rng.uniform(0.65, 1.12)

                    # Weekend vs weekday (commercial sites use less on weekends)
                    weekday_factor = 0.82 if reading_date.weekday() >= 5 and site.site_type == "commercial" else 1.0

                    gen_kwh = Decimal(str(round(base_gen * seasonal_factor * weather, 2)))
                    cons_kwh = Decimal(str(round(float(gen_kwh) * rng.uniform(0.55, 0.92) * weekday_factor, 2)))

                    # Battery SOC (random but sensible)
                    soc = rng.randint(35, 95)

                    _, created = EnergyReading.objects.get_or_create(
                        business=biz,
                        site=site,
                        reading_date=reading_date,
                        defaults={
                            "generation_kwh": gen_kwh,
                            "consumption_kwh": cons_kwh,
                            "battery_soc_pct": soc,
                            "notes": "Auto-seeded demo reading",
                        },
                    )
                    if created:
                        readings_created += 1

            self.stdout.write(f"  Readings: {readings_created} created ({history_days}-day history × {len(sites)} sites)")

            # ── Seed monthly savings records ─────────────────────────────
            savings_created = 0
            for site_idx, site in enumerate(sites):
                monthly_bill = DEMO_SITES[site_idx].get("monthly_grid_bill_before", Decimal("0"))
                if monthly_bill == 0:
                    # Off-grid: savings = diesel offset
                    monthly_bill = DEMO_SITES[site_idx]["installed_capacity_kw"] * Decimal("15000")

                for months_ago in range(5, -1, -1):
                    month_date = (today.replace(day=1) - timedelta(days=months_ago * 28)).replace(day=1)
                    savings = monthly_bill * Decimal(str(round(0.75 + months_ago * 0.02, 2)))
                    _, created = SavingsRecord.objects.get_or_create(
                        business=biz,
                        site=site,
                        month=month_date,
                        defaults={
                            "estimated_savings": savings,
                            "generation_kwh": Decimal(str(
                                round(DEMO_SITES[site_idx]["base_gen_kwh"] * 28 * 0.9, 0)
                            )),
                            "operational_cost": savings * Decimal("0.08"),
                            "notes": "Auto-seeded savings estimate",
                        },
                    )
                    if created:
                        savings_created += 1

            self.stdout.write(f"  Savings records: {savings_created} created")

            # ── Seed alerts ──────────────────────────────────────────────
            alerts_created = 0
            for adata in DEMO_ALERTS:
                site_idx = adata["site_idx"]
                if site_idx >= len(sites):
                    continue
                site = sites[site_idx]
                alert, created = EnergyAlert.objects.get_or_create(
                    business=biz,
                    site=site,
                    alert_type=adata["alert_type"],
                    title=adata["title"],
                    defaults={
                        "severity": adata["severity"],
                        "description": adata.get("suggested_action", ""),
                        "suggested_action": adata.get("suggested_action", ""),
                        "is_resolved": adata.get("is_resolved", False),
                    },
                )
                if created:
                    alerts_created += 1

            self.stdout.write(f"  Alerts: {alerts_created} created")

            # ── Seed copilot insights ────────────────────────────────────
            insights_created = 0
            for idata in DEMO_INSIGHTS:
                site_idx = idata["site_idx"]
                if site_idx >= len(sites):
                    continue
                site = sites[site_idx]
                insight, created = CopilotInsight.objects.get_or_create(
                    business=biz,
                    site=site,
                    category=idata["category"],
                    title=idata["title"],
                    defaults={
                        "severity": idata["severity"],
                        "explanation": idata["explanation"],
                        "suggested_action": idata["suggested_action"],
                        "is_dismissed": False,
                    },
                )
                if created:
                    insights_created += 1

            self.stdout.write(f"  Copilot insights: {insights_created} created")

            # ── Seed demand forecasts ────────────────────────────────────
            forecasts_created = 0
            for site_idx, site in enumerate(sites[:5]):  # first 5 sites
                base_gen = DEMO_SITES[site_idx]["base_gen_kwh"]
                _, created = DemandForecast.objects.get_or_create(
                    business=biz,
                    site=site,
                    forecast_date=today,
                    defaults={
                        "horizon_days": 7,
                        "predicted_daily_kwh": Decimal(str(round(base_gen * 0.85, 1))),
                        "predicted_peak_kw": Decimal(str(round(float(DEMO_SITES[site_idx]["installed_capacity_kw"]) * 0.7, 1))),
                        "confidence_pct": 82,
                        "trend": "stable",
                        "growth_rate_pct": Decimal("3.5"),
                        "overload_risk": site_idx in [7, 9],
                        "explanation": "Based on 90-day historical generation and load trend analysis.",
                        "method": "statistical",
                    },
                )
                if created:
                    forecasts_created += 1

            self.stdout.write(f"  Demand forecasts: {forecasts_created} created")

            # ── Seed technician visits ───────────────────────────────────
            visits_created = 0
            for site_idx, site in enumerate(sites[:6]):
                _, created = TechnicianVisit.objects.get_or_create(
                    business=biz,
                    site=site,
                    scheduled_date=today + timedelta(days=7 + site_idx * 3),
                    defaults={
                        "visit_type": "maintenance",
                        "status": "scheduled",
                        "description": f"Scheduled 6-month routine inspection for {site.name}.",
                    },
                )
                if created:
                    visits_created += 1

            self.stdout.write(f"  Technician visits: {visits_created} created")

            self.stdout.write(self.style.SUCCESS(f"\n✓ {biz.name} — seed complete!"))
            self.stdout.write(f"  {len(sites)} sites | {assets_created} assets | {readings_created} readings")
            self.stdout.write(f"  {savings_created} savings records | {alerts_created} alerts | {insights_created} insights")

        self.stdout.write(self.style.SUCCESS("\n✅ Energy seed complete. Run 'manage.py energy_trigger_alerts' to generate rule-based alerts."))
