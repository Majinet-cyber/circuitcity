"""
Migration: Add Mixed Retail models (RetailDepartment, RetailCategory, RetailProduct, RetailSale, RetailExpense)
"""
from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1077_repair_barcode_registry_table"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RetailDepartment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120)),
                ("icon", models.CharField(blank=True, default="bi-bag", max_length=50)),
                ("description", models.TextField(blank=True)),
                ("is_seeded", models.BooleanField(default=False, help_text="True = came from seed data")),
                ("is_enabled", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    blank=True,
                    help_text="Null = global seeded department available to all businesses",
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="retail_departments",
                    to="tenants.business",
                )),
            ],
            options={"ordering": ["sort_order", "name"], "verbose_name": "Retail Department", "verbose_name_plural": "Retail Departments"},
        ),
        migrations.CreateModel(
            name="RetailCategory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_seeded", models.BooleanField(default=False)),
                ("is_enabled", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    blank=True,
                    help_text="Null = global seeded category",
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="retail_categories",
                    to="tenants.business",
                )),
                ("department", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="categories",
                    to="inventory.retaildepartment",
                )),
            ],
            options={"ordering": ["department__sort_order", "sort_order", "name"], "verbose_name": "Retail Category", "verbose_name_plural": "Retail Categories"},
        ),
        migrations.CreateModel(
            name="RetailProduct",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("sku", models.CharField(blank=True, help_text="Stock code / barcode", max_length=100)),
                ("brand", models.CharField(blank=True, max_length=100)),
                ("model_number", models.CharField(blank=True, max_length=100)),
                ("cost_price", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("selling_price", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("stock_quantity", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="Current quantity in stock", max_digits=10)),
                ("reorder_level", models.DecimalField(decimal_places=2, default=Decimal("5"), help_text="Alert when stock falls below this level", max_digits=10)),
                ("unit", models.CharField(
                    choices=[("pcs","Pieces"),("kg","Kilograms"),("g","Grams"),("litre","Litres"),("ml","Millilitres"),("pair","Pair"),("pack","Pack"),("box","Box"),("roll","Roll"),("set","Set"),("m","Metres"),("other","Other")],
                    default="pcs",
                    max_length=20,
                )),
                ("size", models.CharField(blank=True, max_length=50)),
                ("color", models.CharField(blank=True, max_length=50)),
                ("style", models.CharField(blank=True, max_length=100)),
                ("material", models.CharField(blank=True, max_length=100)),
                ("condition", models.CharField(blank=True, choices=[("new","New"),("refurbished","Refurbished"),("used","Used / Second-hand")], default="new", max_length=20)),
                ("dimensions", models.CharField(blank=True, max_length=100)),
                ("serial_number", models.CharField(blank=True, max_length=100)),
                ("imei", models.CharField(blank=True, max_length=20)),
                ("warranty_months", models.PositiveIntegerField(blank=True, help_text="Warranty period in months", null=True)),
                ("expiry_date", models.DateField(blank=True, help_text="For food, cosmetics, medicine", null=True)),
                ("batch_number", models.CharField(blank=True, max_length=50)),
                ("supplier_name", models.CharField(blank=True, max_length=255)),
                ("supplier_phone", models.CharField(blank=True, max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="retail_products",
                    to="tenants.business",
                )),
                ("category", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="products",
                    to="inventory.retailcategory",
                )),
                ("department", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="products",
                    to="inventory.retaildepartment",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_retail_products",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["department__sort_order", "category__sort_order", "name"], "verbose_name": "Retail Product", "verbose_name_plural": "Retail Products"},
        ),
        migrations.AddIndex(
            model_name="retailproduct",
            index=models.Index(fields=["business", "is_active"], name="retail_product_biz_active_idx"),
        ),
        migrations.AddIndex(
            model_name="retailproduct",
            index=models.Index(fields=["business", "department"], name="retail_product_biz_dept_idx"),
        ),
        migrations.CreateModel(
            name="RetailSale",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("1"), max_digits=10)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("cost_price_snapshot", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=16)),
                ("profit", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=16)),
                ("payment_method", models.CharField(
                    choices=[("cash","Cash"),("airtel_money","Airtel Money"),("tnm_mpamba","TNM Mpamba"),("bank","Bank Transfer"),("credit","Credit / Balance"),("other","Other")],
                    default="cash",
                    max_length=20,
                )),
                ("receipt_ref", models.CharField(blank=True, db_index=True, max_length=50)),
                ("customer_name", models.CharField(blank=True, max_length=255)),
                ("customer_phone", models.CharField(blank=True, max_length=20)),
                ("amount_paid", models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True)),
                ("balance_due", models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True)),
                ("credit_due_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("sold_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("is_rolled_back", models.BooleanField(db_index=True, default=False)),
                ("rolled_back_at", models.DateTimeField(blank=True, null=True)),
                ("rollback_reason", models.CharField(blank=True, max_length=255)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="retail_sales",
                    to="tenants.business",
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sales",
                    to="inventory.retailproduct",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_retail_sales",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-sold_at"], "verbose_name": "Retail Sale", "verbose_name_plural": "Retail Sales"},
        ),
        migrations.AddIndex(
            model_name="retailsale",
            index=models.Index(fields=["business", "sold_at"], name="retail_sale_biz_time_idx"),
        ),
        migrations.AddIndex(
            model_name="retailsale",
            index=models.Index(fields=["business", "is_rolled_back"], name="retail_sale_biz_rb_idx"),
        ),
        migrations.CreateModel(
            name="RetailExpense",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("category", models.CharField(
                    choices=[("rent","Rent"),("utilities","Utilities"),("salaries","Salaries"),("transport","Transport"),("purchase","Stock Purchase"),("repairs","Repairs & Maintenance"),("marketing","Marketing"),("other","Other")],
                    default="other",
                    max_length=30,
                )),
                ("description", models.CharField(max_length=255)),
                ("expense_date", models.DateField(default=django.utils.timezone.localdate)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="retail_expenses",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-expense_date"], "verbose_name": "Retail Expense"},
        ),
    ]
