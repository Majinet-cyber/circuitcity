"""
Migration 1084: Add RetailBusinessDepartment (per-business enable/disable for seeded depts)
and RetailProductTemplate (global quick-start product suggestions).
"""
from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1083_butcheryexpense_butcheryintake_butcheryproduct_and_more"),
        ("tenants", "0035_add_new_business_kinds"),
    ]

    operations = [
        migrations.CreateModel(
            name="RetailBusinessDepartment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="retail_dept_enrollments",
                        to="tenants.business",
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_enrollments",
                        to="inventory.retaildepartment",
                    ),
                ),
            ],
            options={
                "verbose_name": "Business Department Enrollment",
                "verbose_name_plural": "Business Department Enrollments",
                "unique_together": {("business", "department")},
            },
        ),
        migrations.CreateModel(
            name="RetailProductTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("suggested_unit", models.CharField(default="pcs", max_length=20, help_text="Suggested unit of measure")),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_templates",
                        to="inventory.retaildepartment",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product Template",
                "verbose_name_plural": "Product Templates",
                "ordering": ["sort_order", "name"],
            },
        ),
    ]
