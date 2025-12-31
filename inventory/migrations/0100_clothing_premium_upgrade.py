# Generated migration for clothing premium upgrade
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1011_pharmacy_packaging_fields'),
    ]

    operations = [
        # Add new fields to MerchProduct for clothing
        migrations.AddField(
            model_name='merchproduct',
            name='internal_sku',
            field=models.CharField(
                max_length=64,
                blank=True,
                default='',
                db_index=True,
                help_text="Auto-generated internal SKU (business-scoped unique)"
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='brand',
            field=models.CharField(
                max_length=100,
                blank=True,
                default='',
                help_text="Brand name (optional, for premium items)"
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='item_type',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
                help_text="Item type: apparel, footwear, accessory, fragrance, other"
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='has_sizes',
            field=models.BooleanField(
                default=False,
                help_text="Enable size variants for this product"
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='has_colors',
            field=models.BooleanField(
                default=False,
                help_text="Enable color variants for this product"
            ),
        ),
        
        # Create ClothingVariant model
        migrations.CreateModel(
            name='ClothingVariant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('size', models.CharField(blank=True, default='', max_length=20, help_text="Size for this variant (e.g., M, 42)")),
                ('color', models.CharField(blank=True, default='', max_length=50, help_text="Color for this variant")),
                ('variant_sku', models.CharField(blank=True, default='', max_length=100, help_text="Auto-generated variant SKU")),
                ('quantity_in_stock', models.PositiveIntegerField(default=0, help_text="Stock quantity for this variant")),
                ('selling_price_override', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    max_digits=10,
                    null=True,
                    help_text="Override selling price for this variant (optional)"
                )),
                ('cost_price_override', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    max_digits=10,
                    null=True,
                    help_text="Override cost price for this variant (optional)"
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='clothing_variants',
                    to='inventory.merchproduct',
                    help_text="Parent product"
                )),
            ],
            options={
                'ordering': ['size', 'color'],
                'indexes': [
                    models.Index(fields=['product', 'is_active'], name='clothvar_prod_active_idx'),
                    models.Index(fields=['product', 'size', 'color'], name='clothvar_prod_sz_col_idx'),
                ],
            },
        ),
        
        # Add unique constraint for product + size + color
        migrations.AddConstraint(
            model_name='clothingvariant',
            constraint=models.UniqueConstraint(
                fields=['product', 'size', 'color'],
                name='unique_product_size_color'
            ),
        ),
        
        # Add index for internal_sku
        migrations.AddIndex(
            model_name='merchproduct',
            index=models.Index(fields=['business', 'internal_sku'], name='merchprod_biz_isku_idx'),
        ),
    ]

