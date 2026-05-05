from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1073_marketplacelisting_verification_takedown"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RecurringCost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Short name for this cost (e.g. 'Office Rent', 'ESCOM Bill')", max_length=200)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("rent", "Rent"),
                            ("salaries", "Salaries"),
                            ("utilities", "Utilities"),
                            ("transport", "Transport"),
                            ("internet", "Internet & Communications"),
                            ("maintenance", "Maintenance & Repairs"),
                            ("loan_repayment", "Loan Repayments"),
                            ("subscription", "Subscriptions"),
                            ("fuel", "Fuel"),
                            ("insurance", "Insurance"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=30,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Amount per cycle (in business currency)",
                        max_digits=14,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                            ("quarterly", "Quarterly"),
                            ("annually", "Annually"),
                        ],
                        db_index=True,
                        default="monthly",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Paused recurring costs are not auto-posted.",
                    ),
                ),
                (
                    "next_run_date",
                    models.DateField(
                        blank=True,
                        db_index=True,
                        help_text="Date this cost will next be auto-posted.",
                        null=True,
                    ),
                ),
                (
                    "last_posted_date",
                    models.DateField(
                        blank=True,
                        help_text="Date this cost was last auto-posted.",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recurring_costs",
                        to="tenants.business",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recurring_costs_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Recurring Cost",
                "verbose_name_plural": "Recurring Costs",
                "ordering": ["category", "name"],
                "indexes": [
                    models.Index(fields=["business", "is_active"], name="inv_recurr_biz_active_idx"),
                    models.Index(fields=["business", "next_run_date"], name="inv_recurr_biz_nextrun_idx"),
                ],
            },
        ),
    ]
