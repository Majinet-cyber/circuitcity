from django.db import migrations


def _column_names(connection, table_name):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }


def remove_stale_marketplace_is_active_column(apps, schema_editor):
    table_name = "inventory_marketplacelisting"
    column_name = "is_active"
    connection = schema_editor.connection
    if column_name not in _column_names(connection, table_name):
        return

    # Preserve legacy visibility intent before dropping the stale physical column.
    # The current model uses status='live' instead of a database is_active field.
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                f"""
                UPDATE {schema_editor.quote_name(table_name)}
                SET status = %s
                WHERE {schema_editor.quote_name(column_name)} = TRUE
                  AND (status IS NULL OR status = %s)
                """,
                ["live", "draft"],
            )
        else:
            cursor.execute(
                f"""
                UPDATE {schema_editor.quote_name(table_name)}
                SET status = %s
                WHERE {schema_editor.quote_name(column_name)} = 1
                  AND (status IS NULL OR status = %s)
                """,
                ["live", "draft"],
            )

    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(
                f"""
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = '{table_name}'
                  AND sql LIKE '%{column_name}%'
                """
            )
            for (index_name,) in cursor.fetchall():
                cursor.execute(f"DROP INDEX IF EXISTS {schema_editor.quote_name(index_name)}")

        if connection.vendor == "postgresql":
            cursor.execute(
                f"ALTER TABLE {schema_editor.quote_name(table_name)} "
                f"DROP COLUMN IF EXISTS {schema_editor.quote_name(column_name)} CASCADE"
            )
        else:
            cursor.execute(
                f"ALTER TABLE {schema_editor.quote_name(table_name)} "
                f"DROP COLUMN {schema_editor.quote_name(column_name)}"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1064_repair_hire_vehicle_image_table"),
    ]

    operations = [
        migrations.RunPython(
            remove_stale_marketplace_is_active_column,
            migrations.RunPython.noop,
        ),
    ]
