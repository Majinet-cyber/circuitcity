# Generated migration for Pharmacy & Cosmetics vertical upgrade

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0041_add_gympayment_payment_method'),
    ]

    operations = [
        # Add soft delete and undo fields to PharmacySale
        migrations.AddField(
            model_name='pharmacysale',
            name='is_deleted',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='Soft delete flag - deleted sales excluded from reports'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='is_reversed',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='True if this sale was reversed/undone'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='reversal_of',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reversals',
                to='inventory.pharmacysale',
                help_text='Original sale this reverses (if undo)'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='deleted_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pharmacy_sales_deleted',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        
        # Add indexes for the new fields
        migrations.AddIndex(
            model_name='pharmacysale',
            index=models.Index(fields=['is_deleted'], name='inventory_ph_is_dele_idx'),
        ),
        migrations.AddIndex(
            model_name='pharmacysale',
            index=models.Index(fields=['is_reversed'], name='inventory_ph_is_reve_idx'),
        ),
    ]

