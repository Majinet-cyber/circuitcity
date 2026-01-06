# Generated migration to sync cost_type field to Django state
# The database already has this column, so we only update Django's migration state

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1023_ensure_cementcost_created_by_column"),
    ]

    operations = [
        # Only update Django state - database already has the cost_type column
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="cementcost",
                    name="cost_type",
                    field=models.CharField(
                        choices=[
                            ("operating", "Operating Expense"),
                            ("cogs", "Stock/COGS"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="operating",
                        help_text="Type of cost: operating expenses, inventory/COGS, or other",
                        max_length=20,
                    ),
                ),
            ],
            database_operations=[
                # No database operations - column already exists
            ],
        ),
    ]

