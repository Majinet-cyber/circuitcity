"""
Migration: Extend FarmLivestockEvent with new event types and tracking fields.

Adds:
- New FarmLivestockEventType choices: VACCINATION, TREATMENT, FEEDING,
  WEIGHT_CHECK, DISEASE_OUTBREAK, BREEDING, EGG_COLLECTION, MILK_COLLECTION,
  HOUSING_MAINTENANCE, OTHER
- weight_kg field
- quantity / quantity_unit fields
- cost_impact_mwk / revenue_impact_mwk fields
"""
from __future__ import annotations

import django.core.validators
from decimal import Decimal
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1079_consultancy_models"),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # New optional fields on FarmLivestockEvent
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="farmlivestockevent",
            name="weight_kg",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Average weight per animal (for weight checks)",
                max_digits=8,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockevent",
            name="quantity",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Quantity of output (e.g. eggs collected, litres of milk)",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockevent",
            name="quantity_unit",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Unit for quantity (e.g. eggs, litres, kg)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockevent",
            name="cost_impact_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Cost of this event (e.g. vaccination cost, feed cost)",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockevent",
            name="revenue_impact_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Revenue from this event (e.g. egg sales, milk sales)",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        # ------------------------------------------------------------------ #
        # Update event_type field to accept new choices
        # ------------------------------------------------------------------ #
        migrations.AlterField(
            model_name="farmlivestockevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("birth", "Birth"),
                    ("death", "Death"),
                    ("purchase", "Purchase"),
                    ("sale", "Sale"),
                    ("transfer_in", "Transfer In"),
                    ("transfer_out", "Transfer Out"),
                    ("slaughter", "Slaughter"),
                    ("vaccination", "Vaccination"),
                    ("treatment", "Veterinary Treatment"),
                    ("feeding", "Feed / Feeding Record"),
                    ("weight_check", "Weight Check"),
                    ("disease_outbreak", "Disease Outbreak"),
                    ("breeding", "Breeding / Mating"),
                    ("egg_collection", "Egg Collection"),
                    ("milk_collection", "Milk Collection"),
                    ("housing_maintenance", "Housing / Pen Maintenance"),
                    ("other", "Other"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
        # ------------------------------------------------------------------ #
        # count field: allow 0 (for non-count events like vaccination)
        # ------------------------------------------------------------------ #
        migrations.AlterField(
            model_name="farmlivestockevent",
            name="count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of animals affected (0 for non-count events)",
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
