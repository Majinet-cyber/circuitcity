# inventory/management/commands/seed_energy_data.py
"""
Management command: seed sample Renewable Energy data for demo/testing.

Usage:
    python manage.py seed_energy_data
    python manage.py seed_energy_data --business 3
    python manage.py seed_energy_data --force   (re-seed even if data exists)

This command is idempotent — safe to run multiple times without duplicating data.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone


DEMO_SITES = [
    {
        "name": "Mzuzu Commercial Hub – Block A",
        "site_type": "commercial",
        "status": "active",
        "installed_capacity_kw": Decimal("15.0"),
        "address": "Industrial Road, Mzuzu",
        "client_name": "ABC Trading Ltd",
        "installation_cost": Decimal("4500000"),
    },
    {
        "name": "Lilongwe Residential Estate",
        "site_type": "household",
        "status": "active",
        "installed_capacity_kw": Decimal("5.0"),
        "address": "Area 49, Lilongwe",
        "client_name": "Mr. Banda",
        "installation_cost": Decimal("1800000"),
    },
    {
        "name": "Blantyre Health Clinic",
        "site_type": "community",
        "status": "active",
        "installed_capacity_kw": Decimal("20.0"),
        "address": "Ndirande, Blantyre",
        "client_name": "Ministry of Health",
        "installation_cost": Decimal("7500000"),
    },
]

DEMO_ASSETS = [
    # Commercial Hub assets
    {"site_idx": 0, "asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S30-540/MR",   "capacity": Decimal("0.54"),  "capacity_unit": "kW",  "status": "operational", "health_score": 88},
    {"site_idx": 0, "asset_type": "battery",           "brand": "Pylontech",   "model_name": "US5000C",           "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "status": "operational", "health_score": 82},
    {"site_idx": 0, "asset_type": "inverter",          "brand": "Deye",        "model_name": "SUN-15K-SG04LP3",   "capacity": Decimal("15.0"),  "capacity_unit": "kW",  "status": "operational", "health_score": 95},
    {"site_idx": 0, "asset_type": "charge_controller", "brand": "Victron",     "model_name": "SmartSolar 150/70", "capacity": Decimal("70.0"),  "capacity_unit": "A",   "status": "operational", "health_score": 90},
    # Residential assets
    {"site_idx": 1, "asset_type": "solar_panel",       "brand": "Canadian Solar", "model_name": "CS6L-450MS",    "capacity": Decimal("0.45"),  "capacity_unit": "kW",  "status": "operational", "health_score": 91},
    {"site_idx": 1, "asset_type": "battery",           "brand": "Felicity",    "model_name": "LPBA24200",         "capacity": Decimal("4.8"),   "capacity_unit": "kWh", "status": "degraded",    "health_score": 52},
    {"site_idx": 1, "asset_type": "inverter",          "brand": "Growatt",     "model_name": "MIN5000TL-X",       "capacity": Decimal("5.0"),   "capacity_unit": "kW",  "status": "operational", "health_score": 87},
    # Clinic assets
    {"site_idx": 2, "asset_type": "solar_panel",       "brand": "JA Solar",    "model_name": "JAM72S30-540/MR",   "capacity": Decimal("0.54"),  "capacity_unit": "kW",  "status": "operational", "health_score": 93},
    {"site_idx": 2, "asset_type": "battery",           "brand": "Pylontech",   "model_name": "US5000C",           "capacity": Decimal("9.6"),   "capacity_unit": "kWh", "status": "operational", "health_score": 78},
    {"site_idx": 2, "asset_type": "inverter",          "brand": "Deye",        "model_name": "SUN-20K-SG04LP3",   "capacity": Decimal("20.0"),  "capacity_unit": "kW",  "status": "operational", "health_score": 96},
    {"site_idx": 2, "asset_type": "meter",             "brand": "Landis+Gyr",  "model_name": "E350",              "capacity": None,             "capacity_unit": "—",   "status": "operational", "health_score": 100},
    {"site_idx": 2, "asset_type": "generator",         "brand": "Lister",      "model_name": "LD10",              "capacity": Decimal("10.0"),  "capacity_unit": "kVA", "status": "maintenance", "health_score": 65},
]


class Command(BaseCommand):
    help = "Seed sample Renewable Energy sites, assets, readings and savings data"

    def add_arguments(self, parser):
        parser.add_argument("--business", type=int, default=None, help="Limit to specific business ID")
        parser.add_argument("--force", action="store_true", help="Re-seed even if data exists")

    def handle(self, *args, **options):
        business_id = options.get("business")
        force = options.get("force", False)

        try:
            from inventory.models_energy import (
                EnergySite, EnergyAsset, EnergyReading, SavingsRecord,
                SiteType, AssetType, AssetStatus, SiteStatus,
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
                "No energy businesses found. Create an Energy business first, "
                "then re-run this command."
            ))
            return

        today = timezone.now().date()

        for biz in qs:
            existing_sites = EnergySite.objects.filter(business=biz).count()
            if existing_sites >= 3 and not force:
                self.stdout.write(
                    f"  Skipping {biz.name} — already has {existing_sites} sites (use --force to re-seed)"
                )
                continue

            self.stdout.write(f"Seeding energy data for: {biz.name} ...")

            # ── Seed sites ──────────────────────────────────────────────
            sites = []
            for sdata in DEMO_SITES:
                site, created = EnergySite.objects.get_or_create(
                    business=biz,
                    name=sdata["name"],
                    defaults={
                        "site_type": sdata["site_type"],
                        "status": sdata["status"],
                        "installed_capacity_kw": sdata["installed_capacity_kw"],
                        "address": sdata.get("address", ""),
                        "client_name": sdata.get("client_name", ""),
                        "installation_cost": sdata.get("installation_cost", Decimal("0")),
                    },
                )
                sites.append(site)
                self.stdout.write(f"    Site: {site.name} ({'created' if created else 'exists'})")

            # ── Seed assets ──────────────────────────────────────────────
            assets_created = 0
            for adata in DEMO_ASSETS:
                site = sites[adata["site_idx"]]
                asset, created = EnergyAsset.objects.get_or_create(
                    business=biz,
                    site=site,
                    asset_type=adata["asset_type"],
                    brand=adata["brand"],
                    model_name=adata["model_name"],
                    defaults={
                        "capacity": adata["capacity"],
                        "capacity_unit": adata["capacity_unit"],
                        "status": adata["status"],
                        "health_score": adata["health_score"],
                        "install_date": today - timedelta(days=180),
                        "maintenance_interval_days": 180,
                    },
                )
                if created:
                    assets_created += 1
            self.stdout.write(f"    Assets: {assets_created} created")

            # ── Seed 30 days of energy readings ─────────────────────────
            readings_created = 0
            for days_ago in range(29, -1, -1):
                reading_date = today - timedelta(days=days_ago)
                # Simulate realistic generation/consumption
                import random
                random.seed(biz.pk + days_ago)
                base_gen = 85.0
                variation = random.uniform(0.7, 1.15)
                gen_kwh = Decimal(str(round(base_gen * variation, 2)))
                cons_kwh = Decimal(str(round(float(gen_kwh) * random.uniform(0.6, 0.95), 2)))

                _, created = EnergyReading.objects.get_or_create(
                    business=biz,
                    reading_date=reading_date,
                    defaults={
                        "generation_kwh": gen_kwh,
                        "consumption_kwh": cons_kwh,
                        "notes": "Auto-seeded sample reading",
                    },
                )
                if created:
                    readings_created += 1
            self.stdout.write(f"    Readings: {readings_created} created (30-day history)")

            # ── Seed monthly savings records ─────────────────────────────
            savings_created = 0
            for months_ago in range(5, -1, -1):
                month_date = (today.replace(day=1) - timedelta(days=months_ago * 28)).replace(day=1)
                _, created = SavingsRecord.objects.get_or_create(
                    business=biz,
                    month=month_date,
                    defaults={
                        "estimated_savings": Decimal(str(round(95000 + months_ago * 3000, 0))),
                        "notes": "Auto-seeded sample savings",
                    },
                )
                if created:
                    savings_created += 1
            self.stdout.write(f"    Savings records: {savings_created} created")

            self.stdout.write(self.style.SUCCESS(f"  ✓ Done: {biz.name}"))

        self.stdout.write(self.style.SUCCESS("Energy seed complete."))
