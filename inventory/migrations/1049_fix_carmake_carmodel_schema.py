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

from django.db import migrations


def _col_exists(cursor, table, col):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cursor.fetchall())


def _idx_exists(cursor, idx_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=%s",
        [idx_name],
    )
    return cursor.fetchone() is not None


def fix_carmake_carmodel(apps, schema_editor):
    conn = schema_editor.connection
    cursor = conn.cursor()

    # ----------------------------------------------------------------
    # inventory_carmake: add slug, logo, sort_order, is_popular
    # ----------------------------------------------------------------
    MAKE_TABLE = "inventory_carmake"
    make_cols = [
        ("slug",       "varchar(80) NOT NULL DEFAULT ''"),
        ("logo",       "varchar(100) NULL"),
        ("sort_order", "smallint unsigned NOT NULL DEFAULT 0"),
        ("is_popular", "bool NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in make_cols:
        if not _col_exists(cursor, MAKE_TABLE, col_name):
            cursor.execute(
                f'ALTER TABLE "{MAKE_TABLE}" ADD COLUMN "{col_name}" {col_def}'
            )

    # Index on sort_order for CarMake
    if not _idx_exists(cursor, "inventory_carmake_sort_order_idx"):
        cursor.execute(
            'CREATE INDEX "inventory_carmake_sort_order_idx" '
            f'ON "{MAKE_TABLE}" ("sort_order")'
        )
    # Unique index on slug
    if not _idx_exists(cursor, "inventory_carmake_slug_9d56eae0_uniq"):
        cursor.execute(
            'CREATE UNIQUE INDEX "inventory_carmake_slug_9d56eae0_uniq" '
            f'ON "{MAKE_TABLE}" ("slug") WHERE "slug" != \'\''
        )

    # ----------------------------------------------------------------
    # inventory_carmodel: add slug, body_type, common_years, sort_order
    # ----------------------------------------------------------------
    MODEL_TABLE = "inventory_carmodel"
    model_cols = [
        ("slug",         "varchar(80) NOT NULL DEFAULT ''"),
        ("body_type",    "varchar(20) NOT NULL DEFAULT ''"),
        ("common_years", "varchar(40) NOT NULL DEFAULT ''"),
        ("sort_order",   "smallint unsigned NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in model_cols:
        if not _col_exists(cursor, MODEL_TABLE, col_name):
            cursor.execute(
                f'ALTER TABLE "{MODEL_TABLE}" ADD COLUMN "{col_name}" {col_def}'
            )

    # Index on sort_order for CarModel
    if not _idx_exists(cursor, "inventory_carmodel_sort_order_idx"):
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
