from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0001_initial"),
        ("applications", "0009_alter_financingapplication_review_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CallEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stage", models.CharField(
                    choices=[
                        ("customer_call", "Customer Call"),
                        ("guarantor_call", "Guarantor Call"),
                        ("employer_call", "Employer/Income Call"),
                    ],
                    max_length=30,
                )),
                ("audio_file", models.FileField(blank=True, null=True, upload_to="call_recordings/")),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("customer_notified", models.BooleanField(default=False)),
                ("notification_script_confirmed", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="call_evidence",
                    to="applications.financingapplication",
                )),
                ("uploaded_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="uploaded_call_evidence",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"verbose_name": "Call Evidence", "verbose_name_plural": "Call Evidence", "ordering": ["-created_at"]},
        ),
    ]
