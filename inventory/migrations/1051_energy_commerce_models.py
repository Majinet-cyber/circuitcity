"""
Migration: Add energy commerce models — EnergyProduct, EnergyStockIn, EnergyItemSale.

Depends on: 1050_rebuild_carmake_carmodel_tables
"""
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1050_rebuild_carmake_carmodel_tables"),
        ("tenants", "0033_energy_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EnergyProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("solar_panel", "Solar Panels"),
                            ("battery", "Batteries"),
                            ("inverter", "Inverters"),
                            ("charge_controller", "Charge Controllers"),
                            ("solar_light", "Solar Lights & Bulbs"),
                            ("cable_wire", "Cables & Wiring"),
                            ("breaker", "Breakers & Protection"),
                            ("mounting", "Mounting Accessories"),
                            ("connector", "Connectors (MC4 etc.)"),
                            ("gas_cooker", "Gas Cookers"),
                            ("gas_cylinder", "Gas Cylinders"),
                            ("gas_regulator", "Gas Regulators"),
                            ("energy_meter", "Energy Meters"),
                            ("pump", "Pumps"),
                            ("backup_kit", "Backup / Mini-Grid Kits"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=50,
                    ),
                ),
                ("sku", models.CharField(blank=True, default="", max_length=100)),
                ("unit", models.CharField(default="unit", help_text="e.g. unit, metre, kg, set", max_length=30)),
                ("cost_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("selling_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("quantity_in_stock", models.PositiveIntegerField(default=0)),
                ("reorder_level", models.PositiveIntegerField(default=2)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("is_seeded", models.BooleanField(default=False, help_text="Auto-seeded catalog item")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="energy_products",
                        to="tenants.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "Energy Product",
                "ordering": ["category", "name"],
                "unique_together": {("business", "name", "category")},
            },
        ),
        migrations.CreateModel(
            name="EnergyStockIn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField()),
                ("cost_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("supplier", models.CharField(blank=True, default="", max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("received_date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="energy_stock_ins",
                        to="tenants.business",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_ins",
                        to="inventory.energyproduct",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Energy Stock-In",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="EnergyItemSale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("unit_cost", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), editable=False, max_digits=14)),
                ("profit", models.DecimalField(decimal_places=2, default=Decimal("0.00"), editable=False, max_digits=14)),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("CASH", "Cash"),
                            ("MOBILE_MONEY", "Mobile Money"),
                            ("BANK", "Bank Transfer"),
                            ("CREDIT", "Credit"),
                            ("OTHER", "Other"),
                        ],
                        default="CASH",
                        max_length=20,
                    ),
                ),
                ("customer_name", models.CharField(blank=True, default="", max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("sold_at", models.DateTimeField(auto_now_add=True)),
                ("is_reversed", models.BooleanField(default=False)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="energy_item_sales",
                        to="tenants.business",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sales",
                        to="inventory.energyproduct",
                    ),
                ),
                (
                    "sold_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Energy Item Sale",
                "ordering": ["-sold_at"],
            },
        ),
    ]
