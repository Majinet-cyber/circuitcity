# Generated migration to add Groceries V2 fields to MerchProduct
# Fixes: "no such column: inventory_merchproduct.wholesale_price_per_pack"

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0100_clothing_premium_upgrade"),
    ]

    operations = [
        # Add wholesale_price_per_pack field (nullable for backward compatibility)
        migrations.AddField(
            model_name="merchproduct",
            name="wholesale_price_per_pack",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Wholesale price per pack (carton/bale/bundle). If null, derived from retail price * pack_size",
                max_digits=10,
                null=True,
            ),
        ),
        # Add track_expiry field for groceries expiry tracking
        migrations.AddField(
            model_name="merchproduct",
            name="track_expiry",
            field=models.BooleanField(
                default=False, help_text="Track expiry dates for this product (optional for groceries)"
            ),
        ),
    ]
