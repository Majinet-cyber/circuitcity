# Generated migration for adding product_type to MerchProduct
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0039_fix_warranty_field_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchproduct',
            name='product_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('MEDICINE', 'Medicine'),
                    ('OTHER', 'Other Product'),
                ],
                default='MEDICINE',
                help_text='Product type for pharmacy: medicine or other products',
            ),
        ),
        migrations.AddIndex(
            model_name='merchproduct',
            index=models.Index(fields=['business', 'kind', 'product_type'], name='merchprod_biz_kind_type_idx'),
        ),
    ]

