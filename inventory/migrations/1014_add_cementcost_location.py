# Generated manually to add missing location_id column to CementCost
# Fixed: Check if column exists before adding (idempotent)
# Fixed: Use Django introspection instead of SQLite PRAGMA (works on Postgres too)

import django.db.models.deletion
from django.db import migrations, models


def add_location_if_missing(apps, schema_editor):
    """
    Add location_id column to CementCost if it doesn't exist.
    This makes the migration idempotent - safe to run even if column exists.
    Uses Django's database-agnostic introspection (works on SQLite and Postgres).
    """
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if location_id column exists using Django's introspection
    # This works on all database backends (SQLite, Postgres, MySQL, etc.)
    table_name = "inventory_cementcost"

    # Get table description - returns list of FieldInfo named tuples
    # Each has .name attribute for column name
    try:
        table_description = connection.introspection.get_table_description(
            cursor, table_name
        )
        columns = {col.name for col in table_description}
    except Exception:
        # Table might not exist yet - let Django handle it
        columns = set()

    if "location_id" not in columns:
        # Column doesn't exist, add it
        CementCost = apps.get_model("inventory", "CementCost")
        from django.db import models as db_models

        field = db_models.ForeignKey(
            "inventory.Location",
            blank=True,
            null=True,
            on_delete=db_models.SET_NULL,
            related_name="cement_costs",
        )
        field.set_attributes_from_name("location")
        schema_editor.add_field(CementCost, field)


def reverse_add_location(apps, schema_editor):
    """Reverse migration - no-op since we only add if missing"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1013_merge_20260105_1513"),
    ]

    operations = [
        # Use RunPython to conditionally add field
        migrations.RunPython(
            add_location_if_missing,
            reverse_code=reverse_add_location,
        ),
    ]
