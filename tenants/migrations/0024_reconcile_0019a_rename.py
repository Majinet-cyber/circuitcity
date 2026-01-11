# Generated manually to reconcile migration history after renaming 0019_fix_cement_business_kind
# This migration fixes databases where the old migration name was already applied.

from django.db import migrations


def reconcile_migration_rename(apps, schema_editor):
    """
    Fix databases that have '0019_fix_cement_business_kind' applied
    but the migration was renamed to '0019a_fix_cement_business_kind'.
    
    This updates django_migrations table to reflect the rename.
    """
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check if old migration name exists
        cursor.execute("""
            SELECT COUNT(*) FROM django_migrations
            WHERE app = 'tenants' AND name = '0019_fix_cement_business_kind'
        """)
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            print(f"Found {count} record(s) for old migration name. Updating to new name...")
            
            # Update the migration name
            cursor.execute("""
                UPDATE django_migrations
                SET name = '0019a_fix_cement_business_kind'
                WHERE app = 'tenants' AND name = '0019_fix_cement_business_kind'
            """)
            
            print("[OK] Updated migration record from 0019_fix_cement_business_kind to 0019a_fix_cement_business_kind")
        else:
            print("[OK] No old migration record found - migration history is already correct")


def reverse_reconcile(apps, schema_editor):
    """Reverse the rename if needed."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE django_migrations
            SET name = '0019_fix_cement_business_kind'
            WHERE app = 'tenants' AND name = '0019a_fix_cement_business_kind'
        """)


class Migration(migrations.Migration):
    """
    RECONCILIATION MIGRATION
    
    This migration reconciles databases where 0019_fix_cement_business_kind was already
    applied before we renamed it to 0019a_fix_cement_business_kind.
    
    It updates the django_migrations table to reflect the new name, ensuring
    migration history is consistent.
    
    SAFE TO RUN:
    - On databases with the old name (updates the record)
    - On fresh databases (does nothing, no old record exists)
    - Multiple times (idempotent check before update)
    """
    
    # This depends on 0023 (latest migration) but comes before attempting to apply 0019a
    dependencies = [
        ("tenants", "0023_add_currency_field"),
    ]

    operations = [
        migrations.RunPython(
            reconcile_migration_rename,
            reverse_reconcile,
        ),
    ]

