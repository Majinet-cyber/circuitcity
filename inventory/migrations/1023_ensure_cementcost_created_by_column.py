# Generated migration to ensure CementCost.created_by_id column exists

from django.db import migrations, models


def ensure_created_by_column(apps, schema_editor):
    """
    Ensure the 'created_by_id' column exists in inventory_cementcost table.
    This is idempotent - safe to run even if column already exists.
    """
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if column exists
    table_name = "inventory_cementcost"
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1].lower() for row in cursor.fetchall()}

    if "created_by_id" not in columns:
        # Add created_by_id column with NULL allowed (FK to auth_user)
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN created_by_id INTEGER NULL
        """
        )

        # Create index on created_by_id for FK lookups
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS inventory_c_created_by_idx
            ON {table_name} (created_by_id)
        """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1022_delete_pricechangelog"),
    ]

    operations = [
        migrations.RunPython(ensure_created_by_column, reverse_code=migrations.RunPython.noop),
    ]
