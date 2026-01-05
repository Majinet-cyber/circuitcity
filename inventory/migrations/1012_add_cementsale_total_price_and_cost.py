# Generated manually to fix missing total_price and total_cost columns

from decimal import Decimal

from django.db import migrations, models


def backfill_totals(apps, schema_editor):
    """
    Backfill total_price and total_cost for existing CementSale rows.
    Compute from quantity * unit_price and quantity * unit_cost.
    """
    CementSale = apps.get_model("inventory", "CementSale")

    # Update all rows in batches
    for sale in CementSale.objects.all():
        sale.total_price = Decimal(sale.quantity) * sale.unit_price
        sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
        sale.save(update_fields=["total_price", "total_cost"])


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1011_pharmacy_packaging_fields"),
    ]

    operations = [
        # Add total_price column with default=0 (required for SQLite to add column to existing table)
        migrations.AddField(
            model_name="cementsale",
            name="total_price",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                default=Decimal("0.00"),
            ),
            preserve_default=True,
        ),
        # Add total_cost column with default=0
        migrations.AddField(
            model_name="cementsale",
            name="total_cost",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                default=Decimal("0.00"),
                help_text="Total cost of goods sold",
            ),
            preserve_default=True,
        ),
        # Backfill existing rows
        migrations.RunPython(
            backfill_totals,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
