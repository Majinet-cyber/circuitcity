# Generated migration for liquor payment mix and wine glass pricing
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1004_merchproduct_bottles_per_crate_and_more'),
    ]

    operations = [
        # Add payment mix fields to LiquorSale
        migrations.AddField(
            model_name='liquorsale',
            name='cash_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Amount paid in cash',
                max_digits=12
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='bank_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Amount paid via bank transfer',
                max_digits=12
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='mobile_money_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Amount paid via mobile money',
                max_digits=12
            ),
        ),
        
        # Add wine glass pricing fields to MerchProduct
        migrations.AddField(
            model_name='merchproduct',
            name='has_glasses',
            field=models.BooleanField(
                default=False,
                help_text='True for wine products sold by glass'
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='glasses_per_bottle',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text='Number of glasses per bottle (typically 5 for wine)'
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='price_per_glass',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Price per individual glass (for wine)',
                max_digits=10,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='cost_per_glass',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Cost price per glass',
                max_digits=10,
                null=True
            ),
        ),
    ]

