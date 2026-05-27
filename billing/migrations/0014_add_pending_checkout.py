# Generated migration for PendingCheckout model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0013_businesssubscription_cancel_requested_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PendingCheckout',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('selected_plan_code', models.CharField(help_text='Plan code user selected', max_length=50)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Plan amount at time of selection', max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('currency', models.CharField(default='MWK', max_length=10)),
                ('tx_ref', models.CharField(blank=True, db_index=True, default='', help_text='Payment provider transaction reference', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('expired', 'Expired')], default='pending', max_length=20)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional metadata (payment method, provider, etc.)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('expires_at', models.DateTimeField(blank=True, help_text='When this pending checkout expires', null=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pending_checkouts', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('selected_plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pending_checkouts', to='billing.subscriptionplan')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['business', 'status'], name='billing_pen_busines_idx'),
                    models.Index(fields=['tx_ref'], name='billing_pen_tx_ref_idx'),
                ],
            },
        ),
    ]

