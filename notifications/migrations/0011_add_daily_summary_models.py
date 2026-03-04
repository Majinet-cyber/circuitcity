# notifications/migrations/0011_add_daily_summary_models.py
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0010_add_email_delivery_log"),
        ("tenants", "0031_car_hire_models"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # BusinessEmailRecipient
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="BusinessEmailRecipient",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_summary_recipients",
                        to="tenants.business",
                    ),
                ),
                ("email", models.EmailField(help_text="Email address to receive the daily summary.")),
                ("name", models.CharField(blank=True, default="", help_text="Display name (optional, for personalisation).", max_length=120)),
                ("is_active", models.BooleanField(db_index=True, default=True, help_text="Uncheck to stop sending to this address without deleting it.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Daily Summary Recipient",
                "verbose_name_plural": "Daily Summary Recipients",
                "ordering": ["email"],
            },
        ),
        migrations.AddConstraint(
            model_name="businessemailrecipient",
            constraint=models.UniqueConstraint(
                fields=["business", "email"],
                name="uniq_daily_recipient_biz_email",
            ),
        ),
        # ------------------------------------------------------------------
        # DailySummarySettings
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="DailySummarySettings",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "business",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_summary_settings",
                        to="tenants.business",
                    ),
                ),
                ("is_enabled", models.BooleanField(db_index=True, default=False, help_text="Enable daily summary emails for this business.")),
                (
                    "send_hour",
                    models.PositiveSmallIntegerField(
                        choices=[(h, f"{h:02d}:00") for h in range(24)],
                        default=7,
                        help_text="Hour of day (local timezone) to send the summary (0–23).",
                    ),
                ),
                (
                    "timezone",
                    models.CharField(
                        choices=[
                            ("Africa/Blantyre", "Africa/Blantyre (UTC+2)"),
                            ("Africa/Nairobi", "Africa/Nairobi (UTC+3)"),
                            ("Africa/Johannesburg", "Africa/Johannesburg (UTC+2)"),
                            ("Africa/Lagos", "Africa/Lagos (UTC+1)"),
                            ("UTC", "UTC"),
                            ("Europe/London", "Europe/London"),
                            ("America/New_York", "America/New_York (EST)"),
                        ],
                        default="Africa/Blantyre",
                        max_length=64,
                        help_text="Timezone for scheduling and date labels.",
                    ),
                ),
                ("last_sent_date", models.DateField(blank=True, db_index=True, help_text="Date (in the business timezone) of the last successfully dispatched summary.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Daily Summary Settings",
                "verbose_name_plural": "Daily Summary Settings",
            },
        ),
    ]
