from django.db import migrations


def create_missing_hire_vehicle_image_table(apps, schema_editor):
    table_name = "inventory_hirevehicleimage"
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    HireVehicleImage = apps.get_model("inventory", "HireVehicleImage")
    schema_editor.create_model(HireVehicleImage)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1063_repair_vehicle_marketplace_listing_column"),
    ]

    operations = [
        migrations.RunPython(
            create_missing_hire_vehicle_image_table,
            migrations.RunPython.noop,
        ),
    ]
