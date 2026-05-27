# Generated migration: Electronics category on PhoneProductCatalog + ElectronicsStockItem
# Backward compatible: existing rows get category=PHONE, ram_str/storage_str blank.

from decimal import Decimal

import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def set_phone_category(apps, schema_editor):
    """Ensure all existing PhoneProductCatalog rows have category=PHONE."""
    PhoneProductCatalog = apps.get_model("inventory", "PhoneProductCatalog")
    PhoneProductCatalog.objects.all().update(category="PHONE", ram_str="", storage_str="")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1036_add_date_received_to_liquor_stock_in"),
        ("tenants", "0031_car_hire_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- PhoneProductCatalog: add category and specs fields ---
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="category",
            field=models.CharField(
                choices=[("PHONE", "Phone"), ("LAPTOP", "Laptop"), ("DESKTOP", "Desktop")],
                db_index=True,
                default="PHONE",
                help_text="Product type: Phone, Laptop, or Desktop",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="cpu",
            field=models.CharField(blank=True, default="", help_text="CPU (e.g., Intel i5-1135G7)", max_length=120),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="ram_str",
            field=models.CharField(
                blank=True,
                default="",
                help_text="RAM spec (e.g., 16GB) for laptop/desktop",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="storage_str",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Storage (e.g., 512GB SSD) for laptop/desktop",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="screen_size",
            field=models.CharField(blank=True, default="", help_text='Screen size (e.g., 15.6")', max_length=20),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="gpu",
            field=models.CharField(blank=True, default="", help_text="GPU (optional)", max_length=80),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="os",
            field=models.CharField(blank=True, default="", help_text="OS (e.g., Windows 11)", max_length=60),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="condition",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Condition: New, Used, A, B (optional)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="phoneproductcatalog",
            name="main_image",
            field=models.ImageField(blank=True, help_text="Main product photo", null=True, upload_to="electronics/products/%Y/%m/"),
        ),
        # Allow ram_gb/rom_gb to have default 0 for new LAPTOP/DESKTOP rows (existing keep values)
        migrations.AlterField(
            model_name="phoneproductcatalog",
            name="ram_gb",
            field=models.PositiveIntegerField(default=0, help_text="RAM in GB (e.g., 4, 8)"),
        ),
        migrations.AlterField(
            model_name="phoneproductcatalog",
            name="rom_gb",
            field=models.PositiveIntegerField(default=0, help_text="ROM/Storage in GB (e.g., 128, 256)"),
        ),
        migrations.RunPython(set_phone_category, noop_reverse),
        migrations.AlterUniqueTogether(
            name="phoneproductcatalog",
            unique_together={
                (
                    "business",
                    "category",
                    "brand",
                    "model_name",
                    "ram_gb",
                    "rom_gb",
                    "ram_str",
                    "storage_str",
                )
            },
        ),
        migrations.AddIndex(
            model_name="phoneproductcatalog",
            index=models.Index(fields=["business", "category"], name="phoneprod_biz_category_idx"),
        ),
        # --- ElectronicsStockItem ---
        migrations.CreateModel(
            name="ElectronicsStockItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "serial_number",
                    models.TextField(db_index=True, help_text="Serial number (unique per business); any length"),
                ),
                ("received_at", models.DateField(default=django.utils.timezone.localdate, help_text="Date received/stocked")),
                (
                    "order_price",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Cost price",
                        max_digits=12,
                    ),
                ),
                (
                    "selling_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Selling price",
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("IN_STOCK", "In Stock"), ("SOLD", "Sold")],
                        db_index=True,
                        default="IN_STOCK",
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("sold_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="electronics_stock_items",
                        to="tenants.business",
                    ),
                ),
                (
                    "catalog_product",
                    models.ForeignKey(
                        help_text="Catalog model (Laptop or Desktop)",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_items",
                        to="inventory.phoneproductcatalog",
                    ),
                ),
                (
                    "current_location",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="electronics_stock_items",
                        to="inventory.location",
                    ),
                ),
                (
                    "archived_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="archived_electronics_stock_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sold_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="electronics_items_sold",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Electronics stock item (laptop/desktop)",
                "verbose_name_plural": "Electronics stock items",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="electronicsstockitem",
            index=models.Index(
                fields=["business", "serial_number", "is_active"],
                name="electronics_stock_biz_serial",
            ),
        ),
        migrations.AddIndex(
            model_name="electronicsstockitem",
            index=models.Index(
                fields=["business", "status", "is_active"],
                name="electronics_stock_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="electronicsstockitem",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("business", "serial_number"),
                name="unique_electronics_serial_per_business",
            ),
        ),
    ]
