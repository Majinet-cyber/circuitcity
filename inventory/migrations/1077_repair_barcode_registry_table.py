from django.db import migrations, models


def ensure_barcode_registry_table(apps, schema_editor):
    table_name = "inventory_barcoderegistry"
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    BarcodeRegistry = apps.get_model("inventory", "BarcodeRegistry")
    for constraint in BarcodeRegistry._meta.constraints:
        if constraint.name == "unique_barcode_per_business":
            constraint.name = "unique_barcode_registry_per_business"
    schema_editor.create_model(BarcodeRegistry)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1076_repair_phone_stock_edit_request_table"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_barcode_registry_table, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="barcoderegistry",
                    name="unique_barcode_per_business",
                ),
                migrations.AddConstraint(
                    model_name="barcoderegistry",
                    constraint=models.UniqueConstraint(
                        fields=["business", "normalized_code"],
                        condition=models.Q(("is_active", True)),
                        name="unique_barcode_registry_per_business",
                    ),
                ),
            ],
        ),
    ]
