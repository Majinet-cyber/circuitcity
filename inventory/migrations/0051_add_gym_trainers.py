# Generated migration for gym trainers

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0050_add_global_imei_uniqueness"),
    ]

    operations = [
        # Create GymTrainer model
        migrations.CreateModel(
            name="GymTrainer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("phone", models.CharField(blank=True, default="", max_length=20)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "business",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gym_trainers",
                        to="tenants.business",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("business", "name")},
            },
        ),
        # Add trainer FK to GymMember
        migrations.AddField(
            model_name="gymmember",
            name="trainer",
            field=models.ForeignKey(
                blank=True,
                help_text="Assigned trainer for this member",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="members",
                to="inventory.gymtrainer",
            ),
        ),
        # Add indexes
        migrations.AddIndex(
            model_name="gymtrainer",
            index=models.Index(fields=["business", "is_active"], name="inventory_g_busines_gym_trainer_idx"),
        ),
    ]
