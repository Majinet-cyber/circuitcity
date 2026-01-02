# Generated migration for clothing cost tracking
#
# IMPORTANT: This migration MUST be applied to fix the following error:
# django.db.utils.OperationalError: no such column: inventory_merchproduct.size
#
# This migration adds critical fields to MerchProduct for clothing vertical:
# - size: CharField for clothing sizes (S, M, L, XL, numeric sizes)
# - color: CharField for item colors
# - quantity_in_stock: PositiveIntegerField for inventory tracking
# - cost_price: DecimalField for cost per unit
# - selling_price: DecimalField for selling price per unit
#
# All fields use safe defaults (blank=True, default='') ensuring backward compatibility
# with existing liquor, grocery, and pharmacy products.
#
# To apply this migration, run:
#   python manage.py migrate inventory
#
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0044_gym_membership_enhancements"),
    ]

    operations = [
        # Add cost tracking to ClothingSale for profit calculation
        migrations.AddField(
            model_name="clothingsale",
            name="unit_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Cost per unit sold (for profit calculation)",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="clothingsale",
            name="total_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Total cost of goods sold",
                max_digits=12,
            ),
        ),
        # Add size and color fields to MerchProduct for clothing
        migrations.AddField(
            model_name="merchproduct",
            name="size",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Size for clothing items (e.g., S, M, L, XL, or numeric)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="merchproduct",
            name="color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Color for clothing items",
                max_length=50,
            ),
        ),
        # Add stock quantity to MerchProduct for clothing inventory tracking
        migrations.AddField(
            model_name="merchproduct",
            name="quantity_in_stock",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Current quantity in stock (for clothing and other inventory-tracked items)",
            ),
        ),
        # Add cost price to MerchProduct for clothing
        migrations.AddField(
            model_name="merchproduct",
            name="cost_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Cost price per unit (for non-liquor items)",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="merchproduct",
            name="selling_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Selling price per unit (for non-liquor items)",
                max_digits=10,
                null=True,
            ),
        ),
    ]
