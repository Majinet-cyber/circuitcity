# Generated manually on 2025-12-03
# 
# FIX: Rename warranty columns to match model definition.
# The DB has warranty_expires_at but the model expects warranty_expiration.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0038_add_phone_product_catalog"),
    ]

    operations = [
        # Rename warranty_expires_at -> warranty_expiration (if it exists in DB)
        migrations.RunSQL(
            sql="ALTER TABLE inventory_inventoryitem RENAME COLUMN warranty_expires_at TO warranty_expiration;",
            reverse_sql="ALTER TABLE inventory_inventoryitem RENAME COLUMN warranty_expiration TO warranty_expires_at;",
        ),
        
        # Rename warranty_last_checked_at -> warranty_checked_at (if it exists in DB)
        migrations.RunSQL(
            sql="ALTER TABLE inventory_inventoryitem RENAME COLUMN warranty_last_checked_at TO warranty_checked_at;",
            reverse_sql="ALTER TABLE inventory_inventoryitem RENAME COLUMN warranty_checked_at TO warranty_last_checked_at;",
        ),
        
        # Add warranty_source column if it doesn't exist (from migration 0034 that didn't apply)
        migrations.RunSQL(
            sql="""
            ALTER TABLE inventory_inventoryitem 
            ADD COLUMN warranty_source varchar(50) DEFAULT 'carlcare' NOT NULL;
            """,
            reverse_sql="ALTER TABLE inventory_inventoryitem DROP COLUMN warranty_source;",
        ),
    ]

