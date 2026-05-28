from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("imei", models.CharField(max_length=40)),
                ("provider", models.CharField(default="mock", max_length=60)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("passed", "Passed"),
                        ("failed", "Failed"),
                        ("skipped", "Skipped"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("warranty_status", models.CharField(blank=True, max_length=40)),
                ("lock_eligible", models.BooleanField(default=False)),
                ("response_summary", models.TextField(blank=True)),
                ("checked_at", models.DateTimeField(auto_now_add=True)),
                ("contract", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="device_checks",
                    to="financing.financingcontract",
                )),
                ("checked_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="device_checks",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"verbose_name": "Device Check", "ordering": ["-checked_at"]},
        ),
    ]
