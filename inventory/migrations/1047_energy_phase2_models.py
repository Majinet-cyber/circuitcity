# inventory/migrations/1047_energy_phase2_models.py
"""
Phase 2 energy model extensions:
- SystemSizingRun: proposal lifecycle, scenario comparison, advanced financials (NPV/IRR)
- EnergyDataUpload: CSV/bulk data ingestion tracking
- CopilotInsight: rule-based intelligence panel
"""
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1046_energy_sizing_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- SystemSizingRun: Proposal lifecycle fields ---
        migrations.AddField(
            model_name="systemsizingrun",
            name="proposal_status",
            field=models.CharField(
                choices=[
                    ("sizing", "Sizing / Draft"),
                    ("proposal_draft", "Proposal Draft"),
                    ("proposal_sent", "Sent to Customer"),
                    ("approved", "Approved"),
                    ("project", "Active Project"),
                    ("completed", "Completed / Live Site"),
                    ("rejected", "Rejected"),
                ],
                db_index=True, default="sizing", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="proposal_sent_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="proposal_valid_until",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="approval_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="linked_project_site",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="originating_proposals", to="inventory.energysite",
            ),
        ),
        # --- SystemSizingRun: Scenario comparison fields ---
        migrations.AddField(
            model_name="systemsizingrun",
            name="scenario_group",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="scenario_label",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="is_recommended_scenario",
            field=models.BooleanField(default=False),
        ),
        # --- SystemSizingRun: Advanced financial fields ---
        migrations.AddField(
            model_name="systemsizingrun",
            name="discount_rate_pct",
            field=models.DecimalField(decimal_places=2, default=Decimal("10.0"), max_digits=5),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="inflation_rate_pct",
            field=models.DecimalField(decimal_places=2, default=Decimal("8.0"), max_digits=5),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="tariff_escalation_pct",
            field=models.DecimalField(decimal_places=2, default=Decimal("5.0"), max_digits=5),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="diesel_escalation_pct",
            field=models.DecimalField(decimal_places=2, default=Decimal("7.0"), max_digits=5),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="battery_replacement_year",
            field=models.PositiveSmallIntegerField(blank=True, default=10, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="battery_replacement_cost",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="npv",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="irr_pct",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="sensitivity_summary",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="unmet_load_risk_pct",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="systemsizingrun",
            name="growth_headroom_pct",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True),
        ),
        # --- EnergyDataUpload ---
        migrations.CreateModel(
            name="EnergyDataUpload",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("upload_type", models.CharField(choices=[("csv", "CSV Upload"), ("manual_batch", "Manual Batch"), ("api", "API Ingestion")], default="csv", max_length=20)),
                ("filename", models.CharField(blank=True, default="", max_length=255)),
                ("rows_total", models.PositiveIntegerField(default=0)),
                ("rows_imported", models.PositiveIntegerField(default=0)),
                ("rows_skipped", models.PositiveIntegerField(default=0)),
                ("errors", models.JSONField(blank=True, default=list)),
                ("data_quality_score", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("quality_notes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_data_uploads", to="tenants.business")),
                ("site", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="data_uploads", to="inventory.energysite")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="energy_uploads", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Energy Data Upload"},
        ),
        # --- CopilotInsight ---
        migrations.CreateModel(
            name="CopilotInsight",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("performance", "Performance"), ("cost", "Cost / Savings"), ("maintenance", "Maintenance"), ("capacity", "Capacity / Sizing"), ("risk", "Risk / Safety"), ("opportunity", "Opportunity")], db_index=True, max_length=30)),
                ("severity", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="low", max_length=10)),
                ("title", models.CharField(max_length=300)),
                ("explanation", models.TextField(blank=True, default="")),
                ("suggested_action", models.TextField(blank=True, default="")),
                ("is_dismissed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_copilot_insights", to="tenants.business")),
                ("site", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="copilot_insights", to="inventory.energysite")),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="copilot_insights", to="inventory.energyasset")),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Copilot Insight"},
        ),
    ]
