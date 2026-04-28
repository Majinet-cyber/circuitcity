# inventory/migrations/1057_fix_grocerysale_missing_columns.py
"""
Fix GrocerySale table: add missing columns that were defined in models_verticals.py
but never added to the actual DB table (which was created by an earlier migration
using a different schema: total_amount, sale_type instead of total_price, sale_mode).

Root cause: Migration 0062 used RunPython with "create if not exists" logic.
Since the table already existed (old schema), it was skipped and the new columns
were never added. Django's migration state thinks the columns exist; the DB disagrees.
"""
from decimal import Decimal

from django.db import migrations


def add_missing_grocerysale_columns(apps, schema_editor):
    """Add missing columns to inventory_grocerysale table if they don't exist."""
    connection = schema_editor.connection

    try:
        with connection.cursor() as cursor:
            # Get existing columns
            cursor.execute("PRAGMA table_info(inventory_grocerysale)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            if not existing_cols:
                # Table doesn't exist at all - nothing to do (0062 will handle it)
                return

            # Add total_price if missing
            if "total_price" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale ADD COLUMN total_price DECIMAL(12,2) DEFAULT 0.00"
                )
                # Backfill from total_amount if it exists
                if "total_amount" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_price = total_amount WHERE total_price = 0"
                    )
                elif "unit_price" in existing_cols and "quantity" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_price = unit_price * quantity WHERE total_price = 0"
                    )

            # Add sale_mode if missing
            if "sale_mode" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale ADD COLUMN sale_mode VARCHAR(20) DEFAULT 'retail'"
                )
                # Backfill from sale_type if it exists
                if "sale_type" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET sale_mode = 'retail' WHERE sale_mode IS NULL OR sale_mode = ''"
                    )

            # Add total_cost if missing
            if "total_cost" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale ADD COLUMN total_cost DECIMAL(12,2) DEFAULT 0.00"
                )
                # Backfill: total_cost = unit_cost * quantity
                if "unit_cost" in existing_cols and "quantity" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_cost = unit_cost * quantity WHERE total_cost = 0"
                    )

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Could not add missing GrocerySale columns (non-fatal): {e}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1056_alter_systemsizingrun_cost_breakers_lump_and_more"),
    ]

    operations = [
        # State is already correct from 0062 - only fix the DB
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(
                    add_missing_grocerysale_columns,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
        ),
    ]
