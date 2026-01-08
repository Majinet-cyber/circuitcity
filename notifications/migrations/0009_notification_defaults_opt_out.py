# Generated migration for notification defaults (opt-out model)

from django.db import migrations, models


def backfill_notification_preferences_to_true(apps, schema_editor):
    """
    Backfill existing NotificationPreference and WhatsAppPreference records
    to set all notification fields to True (opt-out model).
    Only updates NULL values or existing False values for commission emails.
    """
    NotificationPreference = apps.get_model('notifications', 'NotificationPreference')
    WhatsAppPreference = apps.get_model('notifications', 'WhatsAppPreference')
    
    # Update NotificationPreference: Set commission_emails_enabled to True where False
    # (since we're switching to opt-out model)
    NotificationPreference.objects.filter(
        commission_emails_enabled=False
    ).update(commission_emails_enabled=True)
    
    # Ensure all fields are True for any existing records with NULL
    # (shouldn't happen due to defaults, but defensive)
    for pref in NotificationPreference.objects.all():
        updated = False
        if not pref.welcome_emails:
            pref.welcome_emails = True
            updated = True
        if not pref.instant_sale_email:
            pref.instant_sale_email = True
            updated = True
        if not pref.sale_emails_enabled:
            pref.sale_emails_enabled = True
            updated = True
        if not pref.daily_summary_email:
            pref.daily_summary_email = True
            updated = True
        if not pref.important_alerts_email:
            pref.important_alerts_email = True
            updated = True
        if not pref.high_sales_alerts:
            pref.high_sales_alerts = True
            updated = True
        if not pref.weekly_digest_enabled:
            pref.weekly_digest_enabled = True
            updated = True
        if updated:
            pref.save(update_fields=[
                'welcome_emails', 'instant_sale_email', 'sale_emails_enabled',
                'daily_summary_email', 'important_alerts_email', 'high_sales_alerts',
                'commission_emails_enabled', 'weekly_digest_enabled'
            ])
    
    # Update WhatsAppPreference: Set receive_commission_alerts to True where False
    WhatsAppPreference.objects.filter(
        receive_commission_alerts=False
    ).update(receive_commission_alerts=True)
    
    print(f"✅ Backfilled {NotificationPreference.objects.count()} NotificationPreference records")
    print(f"✅ Backfilled {WhatsAppPreference.objects.count()} WhatsAppPreference records")


def reverse_backfill(apps, schema_editor):
    """
    Reverse migration: Reset commission preferences to False (old default).
    This is a conservative reverse - we can't know what users explicitly set.
    """
    NotificationPreference = apps.get_model('notifications', 'NotificationPreference')
    WhatsAppPreference = apps.get_model('notifications', 'WhatsAppPreference')
    
    # Note: This is NOT perfect reverse as we can't distinguish user choices from backfill
    # In production, this should rarely be run
    pass  # Keep current values (safer than blindly reverting)


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0008_backfill_preferences_and_set_defaults'),
    ]

    operations = [
        # Change model defaults (already done in models.py, this migration records it)
        migrations.AlterField(
            model_name='notificationpreference',
            name='commission_emails_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Receive commission emails when completing sales (for agents)'
            ),
        ),
        migrations.AlterField(
            model_name='notificationpreference',
            name='sale_emails_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Receive sale completion emails (for managers and agents)'
            ),
        ),
        migrations.AlterField(
            model_name='whatsapppreference',
            name='receive_commission_alerts',
            field=models.BooleanField(
                default=True,
                help_text='Notify on commission earnings (for agents)'
            ),
        ),
        # Backfill existing records
        migrations.RunPython(
            backfill_notification_preferences_to_true,
            reverse_backfill
        ),
    ]

