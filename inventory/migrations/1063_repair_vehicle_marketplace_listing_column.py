from django.db import migrations


def _column_names(connection, table_name):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }


def add_missing_vehicle_marketplace_listing(apps, schema_editor):
    table_name = "inventory_vehicle"
    column_name = "marketplace_listing_id"
    if column_name in _column_names(schema_editor.connection, table_name):
        return

    Vehicle = apps.get_model("inventory", "Vehicle")
    field = Vehicle._meta.get_field("marketplace_listing")
    schema_editor.add_field(Vehicle, field)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1062_rename_inventory_m_biz_status_idx_inventory_m_busines_b10da4_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(add_missing_vehicle_marketplace_listing, migrations.RunPython.noop),
    ]
