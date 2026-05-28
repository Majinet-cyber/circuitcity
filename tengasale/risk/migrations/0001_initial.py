from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("applications", "0009_alter_financingapplication_review_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerIdentityProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("emajinet_id", models.CharField(blank=True, max_length=80, null=True)),
                ("national_id_hash", models.CharField(blank=True, max_length=64)),
                ("phone_hash", models.CharField(blank=True, max_length=64)),
                ("verification_status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("verified", "Verified"),
                        ("failed", "Failed"),
                        ("manual", "Manual Review"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="identity_profile",
                    to="applications.financingapplication",
                )),
            ],
            options={"verbose_name": "Customer Identity Profile"},
        ),
        migrations.CreateModel(
            name="CreditRiskAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("affordability_score", models.IntegerField(default=0, help_text="Income vs repayment ratio score (0-100)")),
                ("identity_score", models.IntegerField(default=0, help_text="KYC completeness and match score (0-100)")),
                ("repayment_risk_score", models.IntegerField(default=0, help_text="Risk of non-repayment (0-100, higher = lower risk)")),
                ("data_quality_score", models.IntegerField(default=0, help_text="Application completeness score (0-100)")),
                ("final_score", models.IntegerField(default=0, help_text="Weighted final risk score (0-100)")),
                ("risk_band", models.CharField(
                    choices=[
                        ("low", "Low Risk"),
                        ("medium", "Medium Risk"),
                        ("high", "High Risk"),
                        ("manual_review", "Manual Review"),
                    ],
                    default="manual_review",
                    max_length=20,
                )),
                ("recommended_deposit_percent", models.DecimalField(decimal_places=2, default=20, max_digits=5)),
                ("reasons", models.JSONField(default=list, help_text="List of human-readable reasons for this assessment")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("application", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="credit_assessment",
                    to="applications.financingapplication",
                )),
                ("assessed_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="credit_assessments_performed",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"verbose_name": "Credit Risk Assessment"},
        ),
        migrations.CreateModel(
            name="ExternalCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(
                    choices=[
                        ("emajinet_id", "Emajinet ID"),
                        ("warrant_check", "Warrant Check"),
                        ("credit_bureau", "Credit Bureau"),
                        ("internal_history", "Internal History"),
                    ],
                    max_length=30,
                )),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("completed", "Completed"),
                        ("failed", "Failed"),
                        ("skipped", "Skipped"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("request_reference", models.CharField(blank=True, max_length=120)),
                ("response_summary", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="external_checks",
                    to="applications.financingapplication",
                )),
            ],
            options={"verbose_name": "External Check", "ordering": ["-created_at"]},
        ),
    ]
