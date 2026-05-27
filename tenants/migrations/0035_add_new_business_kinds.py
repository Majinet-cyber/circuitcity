"""
Migration 0035: Add mixed_retail, consultancy, and butchery to business_kind choices.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0034_alter_business_business_kind"),
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
                    ("car_hire", "Car Hire Service"),
                    ("car_dealer", "Car Dealer"),
                    ("energy", "Renewable Energy"),
                    ("mobile_money", "Mobile Money Agent"),
                    ("mixed_retail", "Mixed Retail"),
                    ("consultancy", "Consultancy & Services"),
                    ("butchery", "Butchery"),
                ],
                db_index=True,
                help_text="Business vertical (drives tailored dashboards and flows).",
                max_length=20,
                null=True,
            ),
        ),
    ]
