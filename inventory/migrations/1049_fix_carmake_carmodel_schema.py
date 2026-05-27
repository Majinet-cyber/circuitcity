# inventory/migrations/1049_fix_carmake_carmodel_schema.py
#
# Fixes missing columns in inventory_carmake and inventory_carmodel tables.
#
# Same root cause as 1048: migration 1043 was faked, so the CarMake and
# CarModel tables still have the old schema from an earlier migration.
#
# CarMake DB has:    id, name, created_at
# CarMake model has: id, name, slug, logo, sort_order, is_popular
#
# CarModel DB has:    id, name, year_introduced, year_discontinued, make_id, created_at
# CarModel model has: id, name, slug, body_type, common_years, sort_order, make_id
#
# Cross-database: works on both PostgreSQL (Render) and SQLite (local dev).
# Never uses PRAGMA or sqlite_master.

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

def fix_carmake_carmodel(apps, schema_editor):
    conn = schema_editor.connection
    vendor = conn.vendor

    # ----------------------------------------------------------------
    # inventory_carmake: add slug, logo, sort_order, is_popular
    # ----------------------------------------------------------------
    MAKE_TABLE = "inventory_carmake"

    if vendor == "postgresql":
        make_cols = [
            ("slug",       "varchar(80) NOT NULL DEFAULT ''"),
            ("logo",       "varchar(100) NULL"),
            # PostgreSQL has no UNSIGNED modifier; BOOLEAN default must be TRUE/FALSE
            ("sort_order", "smallint NOT NULL DEFAULT 0"),
            ("is_popular", "boolean NOT NULL DEFAULT FALSE"),
        ]
    else:  # sqlite
        make_cols = [
            ("slug",       "varchar(80) NOT NULL DEFAULT ''"),
            ("logo",       "varchar(100) NULL"),
            ("sort_order", "smallint unsigned NOT NULL DEFAULT 0"),
            ("is_popular", "bool NOT NULL DEFAULT 0"),
        ]

    with conn.cursor() as cursor:
        for col_name, col_def in make_cols:
            if not _col_exists(conn, MAKE_TABLE, col_name):
                cursor.execute(
                    f'ALTER TABLE "{MAKE_TABLE}" ADD COLUMN "{col_name}" {col_def}'
                )

        if not _idx_exists(conn, MAKE_TABLE, "inventory_carmake_sort_order_idx"):
            cursor.execute(
                'CREATE INDEX "inventory_carmake_sort_order_idx" '
                f'ON "{MAKE_TABLE}" ("sort_order")'
            )

        # Partial unique index on slug (WHERE slug != '').
        # Partial indexes are supported by both PostgreSQL and SQLite 3.8.9+.
        # Django 5.2 requires Python 3.10+ which bundles SQLite 3.37+, so safe.
        if not _idx_exists(conn, MAKE_TABLE, "inventory_carmake_slug_9d56eae0_uniq"):
            cursor.execute(
                'CREATE UNIQUE INDEX "inventory_carmake_slug_9d56eae0_uniq" '
                f'ON "{MAKE_TABLE}" ("slug") WHERE "slug" != \'\''
            )

    # ----------------------------------------------------------------
    # inventory_carmodel: add slug, body_type, common_years, sort_order
    # ----------------------------------------------------------------
    MODEL_TABLE = "inventory_carmodel"

    if vendor == "postgresql":
        model_cols = [
            ("slug",         "varchar(80) NOT NULL DEFAULT ''"),
            ("body_type",    "varchar(20) NOT NULL DEFAULT ''"),
            ("common_years", "varchar(40) NOT NULL DEFAULT ''"),
            # PostgreSQL has no UNSIGNED modifier
            ("sort_order",   "smallint NOT NULL DEFAULT 0"),
        ]
    else:  # sqlite
        model_cols = [
            ("slug",         "varchar(80) NOT NULL DEFAULT ''"),
            ("body_type",    "varchar(20) NOT NULL DEFAULT ''"),
            ("common_years", "varchar(40) NOT NULL DEFAULT ''"),
            ("sort_order",   "smallint unsigned NOT NULL DEFAULT 0"),
        ]

    with conn.cursor() as cursor:
        for col_name, col_def in model_cols:
            if not _col_exists(conn, MODEL_TABLE, col_name):
                cursor.execute(
                    f'ALTER TABLE "{MODEL_TABLE}" ADD COLUMN "{col_name}" {col_def}'
                )

        if not _idx_exists(conn, MODEL_TABLE, "inventory_carmodel_sort_order_idx"):
            cursor.execute(
                'CREATE INDEX "inventory_carmodel_sort_order_idx" '
                f'ON "{MODEL_TABLE}" ("sort_order")'
            )


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1048_fix_cardealervehicle_schema"),
    ]

    operations = [
        migrations.RunPython(
            fix_carmake_carmodel,
            migrations.RunPython.noop,
        ),
    ]
