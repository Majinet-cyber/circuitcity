# tenants/migrations/0027_add_farm_welding_business_kinds.py
"""
Migration to add farm and welding business kinds to the choices.

This enables the signup wizard to show these new verticals.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0026_add_membership_is_active"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="business_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("phones", "Phones & Electronics"),
                    ("liquor", "Liquor / Bar"),
                    ("grocery", "Grocery / General"),
                    ("pharmacy", "Cosmetics & Pharmacy"),
                    ("clothing", "Clothing"),
                    ("gym", "Gym / Fitness"),
                    ("hardware", "Hardware & General Dealers"),
                    ("cement", "Cement / Building Materials"),
                    ("farm", "Farm Manager"),
                    ("welding", "Welding Workshop"),
                ],
                db_index=True,
                help_text="Business vertical (drives tailored dashboards and flows).",
                max_length=20,
                null=True,
            ),
        ),
    ]

