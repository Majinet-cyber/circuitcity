# Generated migration to ensure CementCost.category column exists

from django.db import migrations, models


def ensure_category_column(apps, schema_editor):
    """
    Ensure the 'category' column exists in inventory_cementcost table.
    This is idempotent - safe to run even if column already exists.
    """
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if column exists
    table_name = "inventory_cementcost"
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1].lower() for row in cursor.fetchall()}

    if "category" not in columns:
        # Add category column with default value
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN category VARCHAR(50) DEFAULT 'other' NOT NULL
        """
        )

        # Create index on category
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS inventory_c_category_idx
            ON {table_name} (category)
        """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1018_clothingbarcodeunit"),
    ]

    operations = [
        migrations.RunPython(ensure_category_column, reverse_code=migrations.RunPython.noop),
    ]
