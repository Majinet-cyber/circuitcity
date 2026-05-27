"""
Migration 1055: Add editable component cost fields to SystemSizingRun.

These allow users to override Malawi-market default pricing assumptions
per sizing run — e.g. if a supplier has a different panel or battery price.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1054_energy_tariff_assumption"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_per_panel_wp",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                help_text="Solar panel cost per Wp (MWK). Default: 650 MWK/Wp",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_per_battery_kwh",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Battery cost per kWh (MWK). Default: 450,000 MWK/kWh",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_per_inverter_kw",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Inverter cost per kW (MWK). Default: 180,000 MWK/kW",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_per_cc_amp",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                help_text="Charge controller cost per Amp (MWK). Default: 12,000 MWK/A",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_wiring_lump",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Cable and wiring lump-sum cost (MWK). Default: 150,000",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_breakers_lump",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Breakers and protection devices lump-sum cost (MWK). Default: 80,000",
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="cost_mounting_lump",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Mounting structure lump-sum cost (MWK). Default: 50,000",
            ),
        ),
    ]
