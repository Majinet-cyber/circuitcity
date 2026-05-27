"""
Migration 1081: Butchery vertical models.

Creates:
  - ButcheryProduct  (cuts/products sold by the butchery)
  - ButcheryIntake   (carcass / bulk meat intake from supplier)
  - ButcheryIntakeAllocation (how intake is split into cuts)
  - ButcherySale     (sales transactions)
  - ButcheryExpense  (operating costs)
"""
from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1080_farm_extended_events"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0035_add_new_business_kinds"),
    ]

    operations = [
        # ── ButcheryProduct ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ButcheryProduct",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("meat_type", models.CharField(
                    choices=[
                        ("beef", "Beef"), ("goat", "Goat"), ("chicken", "Chicken"),
                        ("pork", "Pork"), ("lamb", "Lamb"), ("fish", "Fish"), ("other", "Other"),
                    ],
                    default="beef", max_length=20,
                )),
                ("description", models.TextField(blank=True)),
                ("cost_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("selling_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("unit", models.CharField(
                    choices=[("kg", "kg"), ("pcs", "Pieces")],
                    default="kg", max_length=10,
                )),
                ("stock_quantity", models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=14)),
                ("reorder_level", models.DecimalField(decimal_places=3, default=Decimal("2.000"), max_digits=14)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="butchery_products",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["meat_type", "name"], "verbose_name": "Butchery Product", "verbose_name_plural": "Butchery Products"},
        ),
        # ── ButcheryIntake ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="ButcheryIntake",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("intake_date", models.DateField(default=django.utils.timezone.localdate)),
                ("meat_type", models.CharField(
                    choices=[
                        ("beef", "Beef"), ("goat", "Goat"), ("chicken", "Chicken"),
                        ("pork", "Pork"), ("lamb", "Lamb"), ("fish", "Fish"), ("other", "Other"),
                    ],
                    default="beef", max_length=20,
                )),
                ("description", models.CharField(blank=True, max_length=200)),
                ("supplier_name", models.CharField(blank=True, max_length=150)),
                ("batch_ref", models.CharField(blank=True, max_length=60)),
                ("intake_weight_kg", models.DecimalField(decimal_places=3, max_digits=12)),
                ("total_cost", models.DecimalField(decimal_places=2, max_digits=14)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="butchery_intakes",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-intake_date", "-created_at"], "verbose_name": "Butchery Intake", "verbose_name_plural": "Butchery Intakes"},
        ),
        # ── ButcheryIntakeAllocation ─────────────────────────────────────────
        migrations.CreateModel(
            name="ButcheryIntakeAllocation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocated_kg", models.DecimalField(decimal_places=3, max_digits=12)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("intake", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="allocations",
                    to="inventory.butcheryintake",
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="intake_allocations",
                    to="inventory.butcheryproduct",
                )),
            ],
            options={"verbose_name": "Intake Allocation", "verbose_name_plural": "Intake Allocations"},
        ),
        # ── ButcherySale ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="ButcherySale",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sold_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("receipt_ref", models.CharField(blank=True, max_length=30)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("cost_price_snapshot", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("discount_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("payment_method", models.CharField(
                    choices=[
                        ("cash", "Cash"), ("airtel_money", "Airtel Money"), ("tnm_mpamba", "TNM Mpamba"),
                        ("bank", "Bank Transfer"), ("credit", "Credit / Balance"), ("other", "Other"),
                    ],
                    default="cash", max_length=20,
                )),
                ("amount_paid", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("credit_due_date", models.DateField(blank=True, null=True)),
                ("customer_name", models.CharField(blank=True, max_length=150)),
                ("customer_phone", models.CharField(blank=True, max_length=30)),
                ("notes", models.TextField(blank=True)),
                ("is_rolled_back", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="butchery_sales",
                    to="tenants.business",
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sales",
                    to="inventory.butcheryproduct",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-sold_at"], "verbose_name": "Butchery Sale", "verbose_name_plural": "Butchery Sales"},
        ),
        # ── ButcheryExpense ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ButcheryExpense",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("category", models.CharField(
                    choices=[
                        ("supplies", "Supplies & Consumables"), ("staff", "Staff / Labour"),
                        ("utilities", "Utilities"), ("equipment", "Equipment & Maintenance"),
                        ("transport", "Transport / Delivery"), ("rent", "Rent / Premises"),
                        ("other", "Other"),
                    ],
                    default="other", max_length=30,
                )),
                ("expense_date", models.DateField(default=django.utils.timezone.localdate)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="butchery_expenses",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-expense_date", "-created_at"], "verbose_name": "Butchery Expense", "verbose_name_plural": "Butchery Expenses"},
        ),
    ]
