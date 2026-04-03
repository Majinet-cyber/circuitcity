# inventory/migrations/1048_fix_cardealervehicle_schema.py
#
# Root cause fix for CarDealerVehicle schema mismatch.
#
# Migration 1043_car_dealer_vehicle_models was recorded in django_migrations as
# applied (via --fake) but never actually ran against the database. The table
# was created by migration 1041 with an older schema:
#   vin, mileage_km, asking_price, cost_price, date_acquired, date_sold,
#   sold_price, notes, created_by_id  — instead of the current model fields.
#
# Django's virtual state post-1043 already has all the NEW fields, so we
# CANNOT use AddField operations here (they would trigger SQLite table rebuilds
# that read old column names Django no longer knows about, causing errors).
#
# Solution: use RunPython to introspect the actual database schema and only
# execute ALTER TABLE ... ADD COLUMN for columns that are genuinely absent.
# This is safe to run multiple times (idempotent).

from django.db import migrations


def _col_exists(cursor, table, col):
    """Return True if `col` exists in `table` (SQLite PRAGMA)."""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cursor.fetchall())


def _idx_exists(cursor, idx_name):
    """Return True if an index with this name exists in sqlite_master."""
    # Use %s parameter style (Django's backend convention)
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=%s",
        [idx_name],
    )
    return cursor.fetchone() is not None


def add_missing_columns(apps, schema_editor):
    """
    Directly add every column that the current CarDealerVehicle model requires
    but that is absent from the database.  Uses raw SQL so Django's virtual
    state (which already has these fields from the faked 1043 migration) does
    not interfere.
    """
    conn = schema_editor.connection
    cursor = conn.cursor()
    TABLE = "inventory_cardealervehicle"

    # Columns to add: (name, SQL type fragment)
    # All text-like columns use NOT NULL + default '' so SQLite can add them.
    # Nullable numeric / FK columns use NULL.
    columns = [
        ("make_text",           "varchar(80) NOT NULL DEFAULT ''"),
        ("model_text",          "varchar(80) NOT NULL DEFAULT ''"),
        ("trim",                "varchar(80) NOT NULL DEFAULT ''"),
        ("drivetrain",          "varchar(5) NOT NULL DEFAULT ''"),
        ("engine_size",         "varchar(20) NOT NULL DEFAULT ''"),
        ("mileage",             "integer unsigned NULL"),
        ("interior_color",      "varchar(40) NOT NULL DEFAULT ''"),
        ("chassis_no",          "varchar(50) NOT NULL DEFAULT ''"),
        ("stock_ref",           "varchar(40) NOT NULL DEFAULT ''"),
        ("buying_price",        "decimal(14,2) NULL"),
        ("selling_price",       "decimal(14,2) NULL"),
        ("location_text",       "varchar(200) NOT NULL DEFAULT ''"),
        ("features_notes",      "text NOT NULL DEFAULT ''"),
        ("import_source_notes", "text NOT NULL DEFAULT ''"),
        ("date_stocked",        "date NOT NULL DEFAULT (date('now'))"),
        ("sold_at",             "datetime NULL"),          # THE CRITICAL ONE
        ("buyer_name",          "varchar(200) NOT NULL DEFAULT ''"),
        ("buyer_phone",         "varchar(30) NOT NULL DEFAULT ''"),
        ("sale_price",          "decimal(14,2) NULL"),
        ("payment_method",      "varchar(30) NOT NULL DEFAULT ''"),
        ("marketplace_listing_id", (
            "bigint NULL REFERENCES inventory_marketplacelisting(id) "
            "DEFERRABLE INITIALLY DEFERRED"
        )),
        ("stocked_by_id", (
            "integer NULL REFERENCES auth_user(id) "
            "DEFERRABLE INITIALLY DEFERRED"
        )),
    ]

    for col_name, col_def in columns:
        if not _col_exists(cursor, TABLE, col_name):
            cursor.execute(
                f'ALTER TABLE "{TABLE}" ADD COLUMN "{col_name}" {col_def}'
            )

    # Indexes: only create if they do not already exist
    indexes = [
        ("inv_cdv_biz_status_idx",
         f'CREATE INDEX "inv_cdv_biz_status_idx" ON "{TABLE}" ("business_id", "status")'),
        ("inv_cdv_make_model_idx",
         f'CREATE INDEX "inv_cdv_make_model_idx" ON "{TABLE}" ("make_id", "model_id")'),
        ("inventory_cardealervehicle_stock_ref_64b1d3dd",
         f'CREATE INDEX "inventory_cardealervehicle_stock_ref_64b1d3dd" ON "{TABLE}" ("stock_ref")'),
        ("inventory_cardealervehicle_marketplace_listing_id_8b75e7c0",
         f'CREATE INDEX "inventory_cardealervehicle_marketplace_listing_id_8b75e7c0" ON "{TABLE}" ("marketplace_listing_id")'),
        ("inventory_cardealervehicle_stocked_by_id_35120891",
         f'CREATE INDEX "inventory_cardealervehicle_stocked_by_id_35120891" ON "{TABLE}" ("stocked_by_id")'),
    ]
    for idx_name, idx_sql in indexes:
        if not _idx_exists(cursor, idx_name):
            cursor.execute(idx_sql)


class Migration(migrations.Migration):
    """
    Schema-sync migration for CarDealerVehicle.

    Uses RunPython with raw SQL to safely add missing columns without relying on
    Django's AddField state machinery (which would conflict with the already-faked
    migration 1043).
    """

    dependencies = [
        ("inventory", "1047_energy_phase2_models"),
        ("tenants", "0032_marketplace_upgrade_and_car_dealer"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_columns,
            migrations.RunPython.noop,
        ),
    ]
