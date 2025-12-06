# Generated migration to update default commission to 12%
#
# NOTE: This migration was originally created as 0003_update_default_commission_to_12pct.py 
# with an invalid dependency on ('sales', '0002_add_payment_method_and_penalties') which did not exist.
# It has been renumbered to 0007 and the dependency corrected to point to the actual
# last valid sales migration (0006_update_commission_default) to fix NodeNotFoundError.
# This maintains backwards compatibility with the existing migration history.

from django.db import migrations, models
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0006_update_commission_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commissionconfig',
            name='base_commission_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('12.00'),
                help_text='Default commission percentage for phone sales (e.g., 12.00 = 12%).',
                max_digits=5,
                validators=[MinValueValidator(0), MaxValueValidator(100)]
            ),
        ),
    ]

