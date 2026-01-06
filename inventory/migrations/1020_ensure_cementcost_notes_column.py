# Generated migration to ensure CementCost.notes column exists

from django.db import migrations, models


def ensure_notes_column(apps, schema_editor):
    """
    Ensure the 'notes' column exists in inventory_cementcost table.
    This is idempotent - safe to run even if column already exists.
    """
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if column exists
    table_name = "inventory_cementcost"
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1].lower() for row in cursor.fetchall()}

    if "notes" not in columns:
        # Add notes column with default value
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN notes TEXT DEFAULT '' NOT NULL
        """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1019_ensure_cementcost_category_column"),
    ]

    operations = [
        migrations.RunPython(ensure_notes_column, reverse_code=migrations.RunPython.noop),
    ]
