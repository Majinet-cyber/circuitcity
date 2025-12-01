# Generated migration for warranty fields and approval workflow

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
        ('tenants', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Update warranty fields on InventoryItem
        migrations.AlterField(
            model_name='inventoryitem',
            name='warranty_status',
            field=models.CharField(
                choices=[
                    ('unknown', 'Unknown'),
                    ('no_warranty', 'No warranty'),
                    ('in_warranty', 'In warranty'),
                    ('expired', 'Expired'),
                    ('activated', 'Activated'),
                ],
                default='unknown',
                help_text='Carlcare warranty status for Tecno/Itel phones',
                max_length=20
            ),
        ),
        migrations.RenameField(
            model_name='inventoryitem',
            old_name='warranty_expires_at',
            new_name='warranty_expiration',
        ),
        migrations.RenameField(
            model_name='inventoryitem',
            old_name='warranty_last_checked_at',
            new_name='warranty_checked_at',
        ),
        migrations.AddField(
            model_name='inventoryitem',
            name='warranty_source',
            field=models.CharField(
                blank=True,
                default='carlcare',
                help_text='Source of warranty information (e.g., carlcare)',
                max_length=50
            ),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='warranty_expiration',
            field=models.DateField(
                blank=True,
                help_text='Warranty expiration date if available',
                null=True
            ),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='warranty_checked_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Last time warranty was checked with Carlcare',
                null=True
            ),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='warranty_raw',
            field=models.JSONField(
                blank=True,
                help_text='Raw warranty check response for auditing',
                null=True
            ),
        ),
        # Remove old activation_detected_at field (replaced by warranty_checked_at)
        migrations.RemoveField(
            model_name='inventoryitem',
            name='activation_detected_at',
        ),
        
        # Create PhoneStockEditRequest model
        migrations.CreateModel(
            name='PhoneStockEditRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payload', models.JSONField(help_text='Proposed changes as a dict of field: new_value')),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
                    db_index=True,
                    default='PENDING',
                    max_length=10
                )),
                ('reason', models.TextField(blank=True, help_text='Optional reason for rejection or notes')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reviewed_at', models.DateTimeField(blank=True, help_text='When the request was approved/rejected', null=True)),
                ('business', models.ForeignKey(
                    db_index=True,
                    help_text='Business this edit request belongs to',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stock_edit_requests',
                    to='tenants.business'
                )),
                ('requested_by', models.ForeignKey(
                    help_text='Agent who requested the edit',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stock_edit_requests',
                    to=settings.AUTH_USER_MODEL
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True,
                    help_text='Manager who approved/rejected this request',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reviewed_stock_edits',
                    to=settings.AUTH_USER_MODEL
                )),
                ('stock', models.ForeignKey(
                    help_text='The stock item to be edited',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='edit_requests',
                    to='inventory.inventoryitem'
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='phonestockeditrequest',
            index=models.Index(fields=['business', 'status'], name='inv_phone_edit_biz_status'),
        ),
        migrations.AddIndex(
            model_name='phonestockeditrequest',
            index=models.Index(fields=['requested_by', 'status'], name='inv_phone_edit_req_status'),
        ),
        migrations.AddIndex(
            model_name='phonestockeditrequest',
            index=models.Index(fields=['stock', 'status'], name='inv_phone_edit_stock_status'),
        ),
    ]

