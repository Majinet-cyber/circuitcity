# Migration: Add payment_method and battery_health to ElectronicsStockItem
# Backward compatible: both fields nullable so existing rows are unaffected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1037_electronics_category_and_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="electronicsstockitem",
            name="payment_method",
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                choices=[
                    ("CASH", "Cash"),
                    ("BANK", "Bank Transfer"),
                    ("MOBILE_MONEY", "Mobile Money"),
                ],
                help_text="Payment method used at sale time",
            ),
        ),
        migrations.AddField(
            model_name="electronicsstockitem",
            name="battery_health",
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                help_text="Battery health indicator (e.g. 'Good', '85%'). Laptops/desktops only.",
            ),
        ),
    ]
