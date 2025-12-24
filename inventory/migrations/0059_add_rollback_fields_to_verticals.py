# Generated migration for adding rollback tracking to vertical sale models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0058_seed_default_accessories'),
    ]

    operations = [
        # Add rollback fields to LiquorSale
        migrations.AddField(
            model_name='liquorsale',
            name='is_rolled_back',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='Whether this sale has been rolled back/reversed'
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='rolled_back_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='When this sale was rolled back'
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='rolled_back_by',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rolled_back_liquor_sales',
                to=settings.AUTH_USER_MODEL,
                help_text='User who rolled back this sale'
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='rollback_reason',
            field=models.CharField(
                max_length=50,
                blank=True,
                default='',
                help_text='Reason for rollback'
            ),
        ),
        migrations.AddField(
            model_name='liquorsale',
            name='rollback_notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Additional notes about the rollback'
            ),
        ),
        
        # Add rollback fields to ClothingSale
        migrations.AddField(
            model_name='clothingsale',
            name='is_rolled_back',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='Whether this sale has been rolled back/reversed'
            ),
        ),
        migrations.AddField(
            model_name='clothingsale',
            name='rolled_back_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='When this sale was rolled back'
            ),
        ),
        migrations.AddField(
            model_name='clothingsale',
            name='rolled_back_by',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rolled_back_clothing_sales',
                to=settings.AUTH_USER_MODEL,
                help_text='User who rolled back this sale'
            ),
        ),
        migrations.AddField(
            model_name='clothingsale',
            name='rollback_reason',
            field=models.CharField(
                max_length=50,
                blank=True,
                default='',
                help_text='Reason for rollback'
            ),
        ),
        migrations.AddField(
            model_name='clothingsale',
            name='rollback_notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Additional notes about the rollback'
            ),
        ),
        
        # Add rollback fields to PharmacySale
        migrations.AddField(
            model_name='pharmacysale',
            name='is_rolled_back',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='Whether this sale has been rolled back/reversed'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='rolled_back_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='When this sale was rolled back'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='rolled_back_by',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rolled_back_pharmacy_sales',
                to=settings.AUTH_USER_MODEL,
                help_text='User who rolled back this sale'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='rollback_reason',
            field=models.CharField(
                max_length=50,
                blank=True,
                default='',
                help_text='Reason for rollback'
            ),
        ),
        migrations.AddField(
            model_name='pharmacysale',
            name='rollback_notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Additional notes about the rollback'
            ),
        ),
        
        # Add indexes for performance
        migrations.AddIndex(
            model_name='liquorsale',
            index=models.Index(fields=['business', 'is_rolled_back', '-sold_at'], name='liquor_rollback_idx'),
        ),
        migrations.AddIndex(
            model_name='clothingsale',
            index=models.Index(fields=['business', 'is_rolled_back', '-sold_at'], name='clothing_rollback_idx'),
        ),
        migrations.AddIndex(
            model_name='pharmacysale',
            index=models.Index(fields=['business', 'is_rolled_back', '-sold_at'], name='pharmacy_rollback_idx'),
        ),
    ]

