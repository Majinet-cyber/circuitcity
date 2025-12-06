# Generated migration for updating commission default from 2% to 10%

from django.db import migrations, models
from decimal import Decimal
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0005_add_payment_method_and_penalties'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commissionconfig',
            name='base_commission_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('10.00'),
                help_text='Default commission percentage for phone sales (e.g., 10.00 = 10%).',
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100)
                ]
            ),
        ),
    ]

