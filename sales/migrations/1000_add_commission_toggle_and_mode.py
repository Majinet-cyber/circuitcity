# Generated migration for commission toggle and mode

from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0007_update_default_commission_to_12pct'),
    ]

    operations = [
        migrations.AddField(
            model_name='commissionconfig',
            name='commissions_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Enable or disable commission calculation for new sales. When OFF, agents do not earn commissions.',
            ),
        ),
        migrations.AddField(
            model_name='commissionconfig',
            name='commission_mode',
            field=models.CharField(
                choices=[('PERCENT', 'Percentage'), ('FIXED', 'Fixed Amount')],
                default='PERCENT',
                help_text='Commission calculation mode: Percentage or Fixed amount per sale.',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='commissionconfig',
            name='base_commission_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('12.00'),
                help_text='Commission percentage for phone sales (e.g., 12.00 = 12%). Used when commission_mode=PERCENT.',
                max_digits=5,
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='commissionconfig',
            name='fixed_commission_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('2000.00'),
                help_text='Fixed commission per sale in MWK. Used when commission_mode=FIXED.',
                max_digits=12,
                validators=[MinValueValidator(0)],
            ),
        ),
    ]

