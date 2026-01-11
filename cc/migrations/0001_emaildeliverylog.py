# Generated migration for EmailDeliveryLog model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),  # Adjust based on your tenants app migrations
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cc', '__latest__'),  # cc app migrations (create initial if doesn't exist)
    ]

    operations = [
        migrations.CreateModel(
            name='EmailDeliveryLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.CharField(
                    choices=[
                        ('SALE_OCCURRED', 'Sale Occurred'),
                        ('USER_SIGNUP', 'User Signup'),
                        ('OTP_REQUEST', 'OTP Request'),
                        ('SUBSCRIPTION_SUCCESS', 'Subscription Success'),
                        ('SUBSCRIPTION_CANCELLED', 'Subscription Cancelled'),
                        ('AGENT_COMMISSION', 'Agent Commission'),
                        ('DAILY_SUMMARY', 'Daily Summary'),
                        ('WEEKLY_DIGEST', 'Weekly Digest'),
                        ('IMPORTANT_ALERT', 'Important Alert'),
                        ('CUSTOM', 'Custom'),
                    ],
                    help_text='Type of email event being sent',
                    max_length=50
                )),
                ('to', models.EmailField(help_text='Primary recipient email', max_length=254)),
                ('cc', models.TextField(blank=True, default='', help_text='CC recipients (comma-separated)')),
                ('bcc', models.TextField(blank=True, default='', help_text='BCC recipients (comma-separated)')),
                ('subject', models.CharField(help_text='Email subject line', max_length=255)),
                ('template_name', models.CharField(blank=True, help_text='Template used (if applicable)', max_length=255)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('sent', 'Sent'),
                        ('failed', 'Failed'),
                        ('retrying', 'Retrying'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20
                )),
                ('attempts', models.IntegerField(default=0, help_text='Number of send attempts')),
                ('last_error', models.TextField(blank=True, default='', help_text='Last error message if failed')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sent_at', models.DateTimeField(blank=True, help_text='When email was successfully sent', null=True)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional context (sale_id, subscription_id, etc.)')),
                ('business', models.ForeignKey(
                    blank=True,
                    help_text='Business this email relates to (if applicable)',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='email_logs',
                    to='tenants.business'
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    help_text='User this email relates to (if applicable)',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='email_logs',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Email Delivery Log',
                'verbose_name_plural': 'Email Delivery Logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='emaildeliverylog',
            index=models.Index(fields=['status', 'created_at'], name='cc_emaildel_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='emaildeliverylog',
            index=models.Index(fields=['event', 'created_at'], name='cc_emaildel_event_created_idx'),
        ),
        migrations.AddIndex(
            model_name='emaildeliverylog',
            index=models.Index(fields=['to', 'created_at'], name='cc_emaildel_to_created_idx'),
        ),
        migrations.AddIndex(
            model_name='emaildeliverylog',
            index=models.Index(fields=['business', 'created_at'], name='cc_emaildel_business_created_idx'),
        ),
    ]

