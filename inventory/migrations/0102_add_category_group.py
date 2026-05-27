# Generated migration to add category_group field to MerchProduct
# Fixes: "no such column: inventory_merchproduct.category_group"

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0101_add_groceries_v2_fields"),
    ]

    operations = [
        # Add category_group field for groceries UI tiles
        migrations.AddField(
            model_name="merchproduct",
            name="category_group",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Category group for groceries UI tiles (drinks, water, snacks, etc.)",
                max_length=30,
            ),
        ),
    ]
