# Generated migration to add location tracking to Membership
# 
# NOTE: This migration was originally created as 0004_add_location_tracking.py with
# an invalid dependency on ('tenants', '0003_auto_20250101_0000') which did not exist.
# It has been renumbered to 0013 and the dependency corrected to point to the actual
# last valid tenants migration (0012_add_business_logo) to fix NodeNotFoundError.
# This maintains backwards compatibility with the existing migration history.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0012_add_business_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='membership',
            name='location_tracking_enabled',
            field=models.BooleanField(
                default=False,
                help_text='True if the agent has granted location permission for automatic time logs.'
            ),
        ),
        migrations.AddField(
            model_name='membership',
            name='last_known_latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Last known GPS latitude from agent.',
                max_digits=9,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='membership',
            name='last_known_longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text='Last known GPS longitude from agent.',
                max_digits=9,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='membership',
            name='last_location_update',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp of last location ping.',
                null=True
            ),
        ),
    ]

