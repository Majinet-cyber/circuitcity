# Generated migration for Alert model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        (
            "inventory",
            "0010_agentprofile_joined_on_location_geofence_radius_m_and_more",
        ),  # Adjust to your latest migration
        ("tenants", "0011_agentinvite_temp_password_hash_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("out_of_stock", "Out of Stock"),
                            ("low_stock", "Low Stock"),
                            ("top_agent", "Top Agent"),
                            ("high_sales", "High Sales Day"),
                            ("payment_received", "Payment Received"),
                            ("new_customer", "New Customer"),
                            ("system", "System Alert"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("message", models.TextField()),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("related_object_id", models.IntegerField(blank=True, null=True)),
                ("related_object_type", models.CharField(blank=True, max_length=50)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("is_dismissed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="tenants.business"
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="inventory.location",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["business", "is_read", "-created_at"], name="inventory_a_busines_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["business", "alert_type", "-created_at"], name="inventory_a_busines_type_idx"),
        ),
    ]
