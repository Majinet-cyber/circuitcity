# inventory/migrations/1050_rebuild_carmake_carmodel_tables.py
#
# Full table rebuild for inventory_carmake and inventory_carmodel.
#
# The old tables (created before migration 1043 was faked) have stale schemas
# with columns the current Django model does not declare (e.g. created_at with
# NOT NULL constraint). Django's INSERT statements omit those columns which
# violates the constraint. Rebuilding the tables solves this cleanly.
#
# Data preservation strategy:
#   - CarMake:  preserve id, name (slug is auto-generated)
#   - CarModel: preserve id, name, make_id (slug is auto-generated)
#   The old `year_introduced` / `year_discontinued` data is discarded — they
#   are not part of the current model.

from django.db import migrations


def rebuild_tables(apps, schema_editor):
    conn = schema_editor.connection
    c = conn.cursor()

    # ----------------------------------------------------------------
    # CarMake rebuild
    # ----------------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS "_new_inventory_carmake" (
            "id"         integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "name"       varchar(80) NOT NULL UNIQUE,
            "slug"       varchar(80) NOT NULL DEFAULT '',
            "logo"       varchar(100) NULL,
            "sort_order" smallint unsigned NOT NULL DEFAULT 0,
            "is_popular" bool NOT NULL DEFAULT 0
        )
    """)
    # Copy rows we care about
    c.execute("""
        INSERT INTO "_new_inventory_carmake" (id, name, slug, sort_order, is_popular)
        SELECT id, name, '', 0, 0
        FROM "inventory_carmake"
        WHERE id NOT IN (SELECT id FROM "_new_inventory_carmake")
    """)
    c.execute('DROP TABLE "inventory_carmake"')
    c.execute('ALTER TABLE "_new_inventory_carmake" RENAME TO "inventory_carmake"')
    # Recreate expected indexes
    c.execute('CREATE INDEX IF NOT EXISTS "inventory_carmake_sort_order_3e7c34b3" ON "inventory_carmake" ("sort_order")')

    # ----------------------------------------------------------------
    # CarModel rebuild
    # ----------------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS "_new_inventory_carmodel" (
            "id"           integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "name"         varchar(80) NOT NULL,
            "slug"         varchar(80) NOT NULL DEFAULT '',
            "body_type"    varchar(20) NOT NULL DEFAULT '',
            "common_years" varchar(40) NOT NULL DEFAULT '',
            "sort_order"   smallint unsigned NOT NULL DEFAULT 0,
            "make_id"      bigint NOT NULL REFERENCES "inventory_carmake" ("id")
                           DEFERRABLE INITIALLY DEFERRED
        )
    """)
    c.execute("""
        INSERT INTO "_new_inventory_carmodel" (id, name, slug, body_type, common_years, sort_order, make_id)
        SELECT id, name, '', '', '', 0, make_id
        FROM "inventory_carmodel"
        WHERE id NOT IN (SELECT id FROM "_new_inventory_carmodel")
    """)
    c.execute('DROP TABLE "inventory_carmodel"')
    c.execute('ALTER TABLE "_new_inventory_carmodel" RENAME TO "inventory_carmodel"')
    # Recreate expected indexes
    c.execute('CREATE INDEX IF NOT EXISTS "inventory_carmodel_sort_order_idx" ON "inventory_carmodel" ("sort_order")')
    c.execute('CREATE INDEX IF NOT EXISTS "inventory_carmodel_make_id_aed37374" ON "inventory_carmodel" ("make_id")')

    # ----------------------------------------------------------------
    # Fix CarDealerVehicle FK integrity: drop rows whose make_id/model_id
    # reference CarMake/CarModel rows that no longer exist (shouldn't happen
    # in dev but defensive).
    # ----------------------------------------------------------------
    c.execute("""
        UPDATE "inventory_cardealervehicle"
        SET "make_id" = NULL
        WHERE "make_id" IS NOT NULL
          AND "make_id" NOT IN (SELECT id FROM "inventory_carmake")
    """)
    c.execute("""
        UPDATE "inventory_cardealervehicle"
        SET "model_id" = NULL
        WHERE "model_id" IS NOT NULL
          AND "model_id" NOT IN (SELECT id FROM "inventory_carmodel")
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1049_fix_carmake_carmodel_schema"),
    ]

    operations = [
        migrations.RunPython(
            rebuild_tables,
            migrations.RunPython.noop,
        ),
    ]
