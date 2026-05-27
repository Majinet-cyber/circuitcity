# inventory/migrations/1048_fix_cardealervehicle_schema.py
#
# Root cause fix for CarDealerVehicle schema mismatch.
#
# Migration 1043_car_dealer_vehicle_models was recorded in django_migrations as
# applied (via --fake) but never actually ran against the database.  The table
# was created by migration 1041 with an older schema:
#   vin, mileage_km, asking_price, cost_price, date_acquired, date_sold,
#   sold_price, notes, created_by_id  — instead of the current model fields.
#
# Django's virtual state post-1043 already has all the NEW fields, so we
# CANNOT use AddField operations here (they would conflict with the already-
# faked migration state).
#
# Solution: use RunPython to introspect the actual database schema and only
# execute ALTER TABLE … ADD COLUMN for columns that are genuinely absent.
# This is safe to run multiple times (idempotent) and works on both
# PostgreSQL (Render) and SQLite (local dev).

from django.db import migrations


# ---------------------------------------------------------------------------
# Cross-database introspection helpers
# ---------------------------------------------------------------------------

def _col_exists(conn, table, col):
    """
    Return True if `col` exists in `table`.

    Uses Django's built-in introspection API — never touches SQLite-only
    PRAGMA or sqlite_master.  Works on PostgreSQL, SQLite, MySQL.
    """
    with conn.cursor() as cursor:
        try:
            cols = conn.introspection.get_table_description(cursor, table)
        except Exception:
            return False
    return any(c.name == col for c in cols)


def _idx_exists(conn, table, idx_name):
    """
    Return True if an index or constraint named `idx_name` exists on `table`.

    Uses Django's built-in introspection API — never touches sqlite_master.
    Works on PostgreSQL, SQLite, MySQL.
    """
    with conn.cursor() as cursor:
        try:
            constraints = conn.introspection.get_constraints(cursor, table)
        except Exception:
            return False
    return idx_name in constraints


# ---------------------------------------------------------------------------
# Migration function
# ---------------------------------------------------------------------------

def add_missing_columns(apps, schema_editor):
    """
    Add every column that the current CarDealerVehicle model requires but
    that is absent from the database.

    Uses raw SQL so Django's virtual state (which already has these fields
    from the faked 1043 migration) does not interfere.

    Column SQL is vendor-aware:
      - PostgreSQL:  no UNSIGNED modifier; NUMERIC not DECIMAL; CURRENT_DATE
                     for date default; TIMESTAMP WITH TIME ZONE for datetimes.
      - SQLite:      original type fragments preserved for compatibility.
    """
    conn = schema_editor.connection
    vendor = conn.vendor
    TABLE = "inventory_cardealervehicle"

    if vendor == "postgresql":
        columns = [
            ("make_text",              "varchar(80) NOT NULL DEFAULT ''"),
            ("model_text",             "varchar(80) NOT NULL DEFAULT ''"),
            ("trim",                   "varchar(80) NOT NULL DEFAULT ''"),
            ("drivetrain",             "varchar(5) NOT NULL DEFAULT ''"),
            ("engine_size",            "varchar(20) NOT NULL DEFAULT ''"),
            # PostgreSQL has no UNSIGNED modifier on integers
            ("mileage",                "integer NULL"),
            ("interior_color",         "varchar(40) NOT NULL DEFAULT ''"),
            ("chassis_no",             "varchar(50) NOT NULL DEFAULT ''"),
            ("stock_ref",              "varchar(40) NOT NULL DEFAULT ''"),
            # PostgreSQL prefers NUMERIC over DECIMAL (both work, NUMERIC is canonical)
            ("buying_price",           "numeric(14,2) NULL"),
            ("selling_price",          "numeric(14,2) NULL"),
            ("location_text",          "varchar(200) NOT NULL DEFAULT ''"),
            ("features_notes",         "text NOT NULL DEFAULT ''"),
            ("import_source_notes",    "text NOT NULL DEFAULT ''"),
            # PostgreSQL date default uses CURRENT_DATE, not SQLite's date('now')
            ("date_stocked",           "date NOT NULL DEFAULT CURRENT_DATE"),
            # PostgreSQL uses TIMESTAMP WITH TIME ZONE, not DATETIME
            ("sold_at",                "timestamp with time zone NULL"),
            ("buyer_name",             "varchar(200) NOT NULL DEFAULT ''"),
            ("buyer_phone",            "varchar(30) NOT NULL DEFAULT ''"),
            ("sale_price",             "numeric(14,2) NULL"),
            ("payment_method",         "varchar(30) NOT NULL DEFAULT ''"),
            ("marketplace_listing_id",
             "bigint NULL REFERENCES inventory_marketplacelisting(id) "
             "DEFERRABLE INITIALLY DEFERRED"),
            # auth_user.id is AutoField (integer / int4) in Django's default user model
            ("stocked_by_id",
             "integer NULL REFERENCES auth_user(id) "
             "DEFERRABLE INITIALLY DEFERRED"),
        ]
    else:  # sqlite
        columns = [
            ("make_text",              "varchar(80) NOT NULL DEFAULT ''"),
            ("model_text",             "varchar(80) NOT NULL DEFAULT ''"),
            ("trim",                   "varchar(80) NOT NULL DEFAULT ''"),
            ("drivetrain",             "varchar(5) NOT NULL DEFAULT ''"),
            ("engine_size",            "varchar(20) NOT NULL DEFAULT ''"),
            ("mileage",                "integer unsigned NULL"),
            ("interior_color",         "varchar(40) NOT NULL DEFAULT ''"),
            ("chassis_no",             "varchar(50) NOT NULL DEFAULT ''"),
            ("stock_ref",              "varchar(40) NOT NULL DEFAULT ''"),
            ("buying_price",           "decimal(14,2) NULL"),
            ("selling_price",          "decimal(14,2) NULL"),
            ("location_text",          "varchar(200) NOT NULL DEFAULT ''"),
            ("features_notes",         "text NOT NULL DEFAULT ''"),
            ("import_source_notes",    "text NOT NULL DEFAULT ''"),
            ("date_stocked",           "date NOT NULL DEFAULT (date('now'))"),
            ("sold_at",                "datetime NULL"),
            ("buyer_name",             "varchar(200) NOT NULL DEFAULT ''"),
            ("buyer_phone",            "varchar(30) NOT NULL DEFAULT ''"),
            ("sale_price",             "decimal(14,2) NULL"),
            ("payment_method",         "varchar(30) NOT NULL DEFAULT ''"),
            ("marketplace_listing_id",
             "bigint NULL REFERENCES inventory_marketplacelisting(id) "
             "DEFERRABLE INITIALLY DEFERRED"),
            ("stocked_by_id",
             "integer NULL REFERENCES auth_user(id) "
             "DEFERRABLE INITIALLY DEFERRED"),
        ]

    with conn.cursor() as cursor:
        for col_name, col_def in columns:
            if not _col_exists(conn, TABLE, col_name):
                cursor.execute(
                    f'ALTER TABLE "{TABLE}" ADD COLUMN "{col_name}" {col_def}'
                )

        indexes = [
            (
                "inv_cdv_biz_status_idx",
                f'CREATE INDEX "inv_cdv_biz_status_idx" '
                f'ON "{TABLE}" ("business_id", "status")',
            ),
            (
                "inv_cdv_make_model_idx",
                f'CREATE INDEX "inv_cdv_make_model_idx" '
                f'ON "{TABLE}" ("make_id", "model_id")',
            ),
            (
                "inventory_cardealervehicle_stock_ref_64b1d3dd",
                f'CREATE INDEX "inventory_cardealervehicle_stock_ref_64b1d3dd" '
                f'ON "{TABLE}" ("stock_ref")',
            ),
            (
                "inventory_cardealervehicle_marketplace_listing_id_8b75e7c0",
                f'CREATE INDEX "inventory_cardealervehicle_marketplace_listing_id_8b75e7c0" '
                f'ON "{TABLE}" ("marketplace_listing_id")',
            ),
            (
                "inventory_cardealervehicle_stocked_by_id_35120891",
                f'CREATE INDEX "inventory_cardealervehicle_stocked_by_id_35120891" '
                f'ON "{TABLE}" ("stocked_by_id")',
            ),
        ]
        for idx_name, idx_sql in indexes:
            if not _idx_exists(conn, TABLE, idx_name):
                cursor.execute(idx_sql)


class Migration(migrations.Migration):
    """
    Schema-sync migration for CarDealerVehicle.

    Uses RunPython with cross-database introspection to safely add missing
    columns without relying on Django's AddField state machinery (which would
    conflict with the already-faked migration 1043).

    Safe to re-run: all operations are guarded by existence checks.
    Reversible: noop reverse (columns added; data preserved; reversal would
    require explicit DROP COLUMN which is not safe to auto-apply).
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
