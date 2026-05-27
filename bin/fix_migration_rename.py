#!/usr/bin/env python
"""
One-time script to fix migration history after renaming 0019_fix_cement_business_kind.

This script directly updates the django_migrations table to rename the migration record.
Run this ONCE before running 'python manage.py migrate'.

Usage:
    python bin/fix_migration_rename.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.db import connection


def fix_migration_rename():
    """
    Update django_migrations table to reflect the rename of
    0019_fix_cement_business_kind -> 0019a_fix_cement_business_kind
    """
    print("="*70)
    print("MIGRATION RENAME FIX")
    print("="*70)
    print("\nThis script fixes the migration history after renaming")
    print("0019_fix_cement_business_kind -> 0019a_fix_cement_business_kind\n")
    
    with connection.cursor() as cursor:
        # Check current state
        print("Checking current migration records...")
        cursor.execute("""
            SELECT name FROM django_migrations
            WHERE app = 'tenants' AND name LIKE '0019%'
            ORDER BY name
        """)
        
        current_migrations = [row[0] for row in cursor.fetchall()]
        print(f"Found migrations: {current_migrations}")
        
        # Check if old migration exists
        cursor.execute("""
            SELECT COUNT(*) FROM django_migrations
            WHERE app = 'tenants' AND name = '0019_fix_cement_business_kind'
        """)
        
        old_count = cursor.fetchone()[0]
        
        if old_count > 0:
            print(f"\n[OK] Found {old_count} record(s) with old name '0019_fix_cement_business_kind'")
            print("  Updating to '0019a_fix_cement_business_kind'...")
            
            # Update the record
            cursor.execute("""
                UPDATE django_migrations
                SET name = '0019a_fix_cement_business_kind'
                WHERE app = 'tenants' AND name = '0019_fix_cement_business_kind'
            """)
            
            print("[OK] Successfully updated migration record!")
            print("\nYou can now run: python manage.py migrate")
            return True
        else:
            print("\n[OK] No old migration record found.")
            print("  Migration history is already correct, or this is a fresh database.")
            print("\nYou can proceed with: python manage.py migrate")
            return False


def main():
    try:
        fixed = fix_migration_rename()
        
        print("\n" + "="*70)
        if fixed:
            print("SUCCESS: Migration history fixed!")
        else:
            print("INFO: No changes needed")
        print("="*70)
        
        return 0
    except Exception as e:
        print(f"\n[ERROR]: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

