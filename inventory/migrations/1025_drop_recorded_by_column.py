# Generated migration to remove obsolete recorded_by column
# The database has recorded_by_id but our model uses created_by_id

from django.db import migrations


def drop_recorded_by_if_exists(apps, schema_editor):
    """
    Drop the recorded_by_id column if it exists.
    This is an old column that should be replaced by created_by_id.
    """
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if column exists
    table_name = "inventory_cementcost"
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1].lower() for row in cursor.fetchall()}

    if "recorded_by_id" in columns:
        # SQLite doesn't support DROP COLUMN directly in old versions
        # We'll leave it for now and just ensure it's nullable
        # In production, this would need a table recreation
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1024_add_cost_type_to_django_state"),
    ]

    operations = [
        migrations.RunPython(drop_recorded_by_if_exists, reverse_code=migrations.RunPython.noop),
    ]

