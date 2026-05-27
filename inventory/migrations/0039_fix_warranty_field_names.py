# Generated manually on 2025-12-03
# FIXED: Postgres-compatible warranty column renames
#
# FIX: Rename warranty columns to match model definition.
# The DB has warranty_expires_at but the model expects warranty_expiration.

from django.db import migrations


def rename_warranty_columns_if_exist(apps, schema_editor):
    """
    Rename warranty columns only if the old ones exist.
    Works on both SQLite and Postgres using database-specific introspection.
    """
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            # Postgres: Use information_schema

            # Check if old warranty_expires_at column exists
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM information_schema.columns
                WHERE table_name = 'inventory_inventoryitem'
                  AND column_name = 'warranty_expires_at'
            """
            )
            has_old_expiration = cursor.fetchone()[0] > 0

            # Check if old warranty_last_checked_at column exists
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM information_schema.columns
                WHERE table_name = 'inventory_inventoryitem'
                  AND column_name = 'warranty_last_checked_at'
            """
            )
            has_old_checked = cursor.fetchone()[0] > 0

            # Check if warranty_source exists
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM information_schema.columns
                WHERE table_name = 'inventory_inventoryitem'
                  AND column_name = 'warranty_source'
            """
            )
            has_source = cursor.fetchone()[0] > 0

            # Rename columns if old names exist
            if has_old_expiration:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    RENAME COLUMN warranty_expires_at TO warranty_expiration
                """
                )

            if has_old_checked:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    RENAME COLUMN warranty_last_checked_at TO warranty_checked_at
                """
                )

            # Add warranty_source if it doesn't exist
            if not has_source:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    ADD COLUMN warranty_source VARCHAR(50) DEFAULT 'carlcare' NOT NULL
                """
                )

        elif connection.vendor == "sqlite":
            # SQLite: Use pragma_table_info

            cursor.execute(
                """
                SELECT COUNT(*) FROM pragma_table_info('inventory_inventoryitem') 
                WHERE name='warranty_expires_at'
            """
            )
            has_old_expiration = cursor.fetchone()[0] > 0

            cursor.execute(
                """
                SELECT COUNT(*) FROM pragma_table_info('inventory_inventoryitem') 
                WHERE name='warranty_last_checked_at'
            """
            )
            has_old_checked = cursor.fetchone()[0] > 0

            cursor.execute(
                """
                SELECT COUNT(*) FROM pragma_table_info('inventory_inventoryitem') 
                WHERE name='warranty_source'
            """
            )
            has_source = cursor.fetchone()[0] > 0

            # Rename if old columns exist
            if has_old_expiration:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    RENAME COLUMN warranty_expires_at TO warranty_expiration
                """
                )

            if has_old_checked:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    RENAME COLUMN warranty_last_checked_at TO warranty_checked_at
                """
                )

            # Add warranty_source if it doesn't exist
            if not has_source:
                cursor.execute(
                    """
                    ALTER TABLE inventory_inventoryitem 
                    ADD COLUMN warranty_source VARCHAR(50) DEFAULT 'carlcare' NOT NULL
                """
                )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0038_add_phone_product_catalog"),
    ]

    operations = [
        migrations.RunPython(rename_warranty_columns_if_exist, migrations.RunPython.noop),
    ]
