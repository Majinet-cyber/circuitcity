# Generated migration to extend MerchProduct.category field for Pharmacy & Cosmetics

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0046_rename_gymcheckin_biz_ts_idx_inventory_g_busines_72ef0c_idx_and_more"),
    ]

    operations = [
        # Extend category field to support longer pharmacy category codes
        migrations.AlterField(
            model_name="merchproduct",
            name="category",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Product category (e.g., liquor: beer/cider/spirits; pharmacy: medicine/cosmetics)",
                max_length=30,
            ),
        ),
    ]
