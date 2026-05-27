# Generated migration for gym membership enhancements

from django.conf import settings
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0043_add_assigned_role_index"),
        ("tenants", "0014_add_case_insensitive_unique_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add trainer and fee fields to GymMember
        migrations.AddField(
            model_name="gymmember",
            name="has_trainer",
            field=models.BooleanField(default=False, help_text="Whether this member has a trainer"),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="membership_fee",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                null=True,
                blank=True,
                help_text="Snapshot of membership fee at signup/renewal",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="trainer_fee",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                null=True,
                blank=True,
                help_text="Snapshot of trainer fee if has_trainer=True",
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="last_payment_date",
            field=models.DateField(null=True, blank=True, help_text="Date of most recent payment"),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="membership_start",
            field=models.DateField(null=True, blank=True, help_text="Start date of current membership period"),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="membership_end",
            field=models.DateField(
                null=True,
                blank=True,
                help_text="End date of current membership period (start + 30 days)",
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="gymmember",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("PENDING_PAYMENT", "Pending Payment"),
                    ("ACTIVE", "Active"),
                    ("BEHIND_SCHEDULE", "Behind Schedule"),
                    ("EXPIRED", "Expired"),
                ],
                default="PENDING_PAYMENT",
                db_index=True,
                help_text="Current membership status",
            ),
        ),
        # Add default_trainer_fee to GymSettings
        migrations.AddField(
            model_name="gymsettings",
            name="default_trainer_fee",
            field=models.DecimalField(
                decimal_places=2, max_digits=10, default=Decimal("30000.00"), help_text="Default trainer fee per month"
            ),
        ),
        # Create GymCheckIn model for check-in tracking
        migrations.CreateModel(
            name="GymCheckIn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "business",
                    models.ForeignKey(on_delete=models.CASCADE, related_name="gym_checkins", to="tenants.business"),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="gym_checkins",
                        to="inventory.location",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(on_delete=models.CASCADE, related_name="checkins", to="inventory.gymmember"),
                ),
                (
                    "checked_in_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="gym_checkins_performed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-timestamp"],
                "indexes": [
                    models.Index(fields=["business", "-timestamp"], name="gymcheckin_biz_ts_idx"),
                    models.Index(fields=["member", "-timestamp"], name="gymcheckin_mem_ts_idx"),
                ],
            },
        ),
    ]
