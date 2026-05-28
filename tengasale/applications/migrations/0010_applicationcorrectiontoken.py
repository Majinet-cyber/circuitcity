from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0009_alter_financingapplication_review_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApplicationCorrectionToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(blank=True, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("application", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="correction_token_obj",
                    to="applications.financingapplication",
                )),
            ],
            options={"verbose_name": "Application Correction Token"},
        ),
    ]
