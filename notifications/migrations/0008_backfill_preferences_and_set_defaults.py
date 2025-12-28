# Data migration to backfill NotificationPreference for existing users
# Sets sale_emails_enabled based on user role: True for managers, False for agents

from django.db import migrations
from django.conf import settings


def backfill_preferences(apps, schema_editor):
    """
    Backfill NotificationPreference for all existing users.
    Sets sale_emails_enabled=True for managers/owners, False for agents.
    """
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Membership = apps.get_model("tenants", "Membership")
    
    # Get all users without preferences
    users_without_prefs = User.objects.exclude(
        id__in=NotificationPreference.objects.values_list("user_id", flat=True)
    )
    
    created_count = 0
    
    for user in users_without_prefs:
        # Determine if user is a manager/owner or agent
        is_manager = Membership.objects.filter(
            user=user,
            role__in=["MANAGER", "OWNER", "ADMIN"],
            status="ACTIVE"
        ).exists()
        
        # Default: managers get sale_emails_enabled=True, agents get False
        sale_emails_enabled = is_manager
        
        NotificationPreference.objects.create(
            user=user,
            sale_emails_enabled=sale_emails_enabled,
            # Keep other defaults from model
        )
        created_count += 1
    
    # Also update existing preferences to sync sale_emails_enabled with instant_sale_email
    # if sale_emails_enabled is True (default) but instant_sale_email is False
    existing_prefs = NotificationPreference.objects.filter(sale_emails_enabled=True)
    for pref in existing_prefs:
        # If instant_sale_email is False, sync sale_emails_enabled to False
        if not pref.instant_sale_email:
            pref.sale_emails_enabled = False
            pref.save(update_fields=["sale_emails_enabled"])
    
    # Also set sale_emails_enabled based on role for existing preferences
    for pref in NotificationPreference.objects.all():
        user = pref.user
        is_manager = Membership.objects.filter(
            user=user,
            role__in=["MANAGER", "OWNER", "ADMIN"],
            status="ACTIVE"
        ).exists()
        
        # Only update if it's still at default (True) and user is an agent
        if pref.sale_emails_enabled and not is_manager:
            pref.sale_emails_enabled = False
            pref.save(update_fields=["sale_emails_enabled"])


def reverse_backfill(apps, schema_editor):
    """Reverse migration - no-op since we're just creating/updating preferences"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0007_add_sale_emails_enabled_field"),
        ("tenants", "__latest__"),
    ]

    operations = [
        migrations.RunPython(backfill_preferences, reverse_backfill),
    ]
