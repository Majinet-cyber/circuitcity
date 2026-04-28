# inventory/migrations/1057_fix_grocerysale_missing_columns.py
"""
Fix GrocerySale table: add missing columns that were defined in models_verticals.py
but never added to the actual DB table (which was created by an earlier migration
using a different schema: total_amount, sale_type instead of total_price, sale_mode).

Root cause: Migration 0062 used RunPython with "create if not exists" logic.
Since the table already existed (old schema), it was skipped and the new columns
were never added. Django's migration state thinks the columns exist; the DB disagrees.

Safety: This migration is fully idempotent for both PostgreSQL and SQLite.
- PostgreSQL: uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS (no-op if column exists).
- SQLite: checks information_schema.columns before issuing ALTER TABLE.
  PRAGMA is intentionally avoided — it is SQLite-only and causes PostgreSQL
  to abort the transaction, breaking all subsequent SQL in the same migration.
"""
from django.db import migrations


def _get_existing_columns_pg(cursor, table_name):
    """Return set of existing column names using information_schema (PostgreSQL-safe)."""
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
          AND table_schema = 'public'
        """,
        [table_name],
    )
    return {row[0] for row in cursor.fetchall()}


def _get_existing_columns_sqlite(cursor, table_name):
    """Return set of existing column names for SQLite using PRAGMA table_info."""
    cursor.execute(f"PRAGMA table_info({table_name})")  # nosec: table name is hard-coded
    rows = cursor.fetchall()
    return {row[1] for row in rows}


def add_missing_grocerysale_columns(apps, schema_editor):
    """Add missing columns to inventory_grocerysale using vendor-safe SQL."""
    connection = schema_editor.connection
    vendor = connection.vendor  # 'postgresql' | 'sqlite' | 'mysql'

    with connection.cursor() as cursor:
        if vendor == "postgresql":
            # ADD COLUMN IF NOT EXISTS is idempotent — no pre-check needed.
            # These statements are individually safe: if the column already exists
            # PostgreSQL silently skips them without raising an error.
            cursor.execute(
                "ALTER TABLE inventory_grocerysale "
                "ADD COLUMN IF NOT EXISTS total_price NUMERIC(12,2) DEFAULT 0.00"
            )
            cursor.execute(
                "ALTER TABLE inventory_grocerysale "
                "ADD COLUMN IF NOT EXISTS sale_mode VARCHAR(20) DEFAULT 'retail'"
            )
            cursor.execute(
                "ALTER TABLE inventory_grocerysale "
                "ADD COLUMN IF NOT EXISTS total_cost NUMERIC(12,2) DEFAULT 0.00"
            )

            # Backfill only where the value is still at the default zero.
            existing_cols = _get_existing_columns_pg(cursor, "inventory_grocerysale")

            if "total_amount" in existing_cols:
                cursor.execute(
                    "UPDATE inventory_grocerysale SET total_price = total_amount "
                    "WHERE total_price = 0"
                )
            elif "unit_price" in existing_cols and "quantity" in existing_cols:
                cursor.execute(
                    "UPDATE inventory_grocerysale SET total_price = unit_price * quantity "
                    "WHERE total_price = 0"
                )

            if "unit_cost" in existing_cols and "quantity" in existing_cols:
                cursor.execute(
                    "UPDATE inventory_grocerysale SET total_cost = unit_cost * quantity "
                    "WHERE total_cost = 0"
                )

        else:
            # SQLite (local dev): check columns before adding — SQLite does not
            # support ADD COLUMN IF NOT EXISTS on versions older than 3.37.0.
            existing_cols = _get_existing_columns_sqlite(cursor, "inventory_grocerysale")

            if not existing_cols:
                # Table does not exist yet; 0062 will create it with correct schema.
                return

            if "total_price" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale "
                    "ADD COLUMN total_price DECIMAL(12,2) DEFAULT 0.00"
                )
                if "total_amount" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_price = total_amount "
                        "WHERE total_price = 0"
                    )
                elif "unit_price" in existing_cols and "quantity" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_price = unit_price * quantity "
                        "WHERE total_price = 0"
                    )

            if "sale_mode" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale "
                    "ADD COLUMN sale_mode VARCHAR(20) DEFAULT 'retail'"
                )

            if "total_cost" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE inventory_grocerysale "
                    "ADD COLUMN total_cost DECIMAL(12,2) DEFAULT 0.00"
                )
                if "unit_cost" in existing_cols and "quantity" in existing_cols:
                    cursor.execute(
                        "UPDATE inventory_grocerysale SET total_cost = unit_cost * quantity "
                        "WHERE total_cost = 0"
                    )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1056_alter_systemsizingrun_cost_breakers_lump_and_more"),
    ]

    operations = [
        # State is already correct from 0062 — only fix the DB schema.
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
