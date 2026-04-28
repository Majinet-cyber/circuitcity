# inventory/migrations/1059_grocerysale_legacy_fields_state_only.py
"""
Add legacy GrocerySale fields to Django's migration state only.

Root cause:
  The inventory_grocerysale table was originally created by migration 0062
  (RunPython / CREATE TABLE IF NOT EXISTS). It used an older schema that has
  these NOT NULL columns with no DB-level defaults:
    - sale_type      varchar(20)   NOT NULL
    - total_amount   decimal       NOT NULL
    - customer_name  varchar(200)  NOT NULL
    - customer_phone varchar(20)   NOT NULL
    - is_deleted     bool          NOT NULL
    - created_at     datetime      NOT NULL

  The current model dropped these fields, so Django never provided values for
  them during INSERT, causing:
    NOT NULL constraint failed: inventory_grocerysale.sale_type

Fix:
  Re-add all six legacy fields to the model with safe defaults so Django
  always supplies values in INSERT statements. Since the columns already exist
  in the database, this migration only updates Django's state (no DDL runs).
"""
from decimal import Decimal

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1058_add_iot_and_mobilemoney_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Tell Django's ORM that these columns exist so it includes them
            # in INSERT/UPDATE statements going forward.
            state_operations=[
                migrations.AddField(
                    model_name="grocerysale",
                    name="sale_type",
                    field=models.CharField(
                        choices=[
                            ("regular", "Regular"),
                            ("discount", "Discount"),
                            ("wholesale", "Wholesale"),
                            ("correction", "Correction"),
                        ],
                        default="regular",
                        max_length=30,
                    ),
                ),
                migrations.AddField(
                    model_name="grocerysale",
                    name="total_amount",
                    field=models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                    ),
                ),
                migrations.AddField(
                    model_name="grocerysale",
                    name="customer_name",
                    field=models.CharField(blank=True, default="", max_length=200),
                ),
                migrations.AddField(
                    model_name="grocerysale",
                    name="customer_phone",
                    field=models.CharField(blank=True, default="", max_length=20),
                ),
                migrations.AddField(
                    model_name="grocerysale",
                    name="is_deleted",
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name="grocerysale",
                    name="created_at",
                    field=models.DateTimeField(default=django.utils.timezone.now),
                ),
            ],
            # Columns already exist in the DB — no DDL needed.
            database_operations=[],
        ),
    ]
