from django.db import migrations


def ensure_phone_stock_edit_request_table(apps, schema_editor):
    table_name = "inventory_phonestockeditrequest"
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    PhoneStockEditRequest = apps.get_model("inventory", "PhoneStockEditRequest")
    schema_editor.create_model(PhoneStockEditRequest)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1075_rename_inv_recurr_biz_active_idx_inventory_r_busines_635041_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(ensure_phone_stock_edit_request_table, migrations.RunPython.noop),
    ]
