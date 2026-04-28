# inventory/migrations/1058_add_iot_and_mobilemoney_models.py
"""Adds IoT device/reading models and Mobile Money transaction/credit/reconciliation models."""
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1057_fix_grocerysale_missing_columns"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── IoT Device ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="IoTDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(db_index=True, max_length=100, unique=True, help_text="Unique device identifier")),
                ("name", models.CharField(max_length=150, help_text="Human-friendly name")),
                ("device_type", models.CharField(choices=[("energy","Energy Monitor"),("weather","Weather Station"),("water","Water Sensor"),("motion","Motion Sensor"),("gps","GPS Tracker"),("custom","Custom Device")], default="energy", max_length=30)),
                ("vertical", models.CharField(blank=True, default="", max_length=50)),
                ("api_key", models.CharField(max_length=64, unique=True, help_text="Secret token")),
                ("status", models.CharField(choices=[("online","Online"),("offline","Offline"),("warning","Warning")], default="offline", max_length=20)),
                ("last_seen", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("business", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iot_devices", to="tenants.business")),
            ],
            options={"ordering": ["-last_seen"]},
        ),
        # ── IoT Reading ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="IoTReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reading_type", models.CharField(db_index=True, max_length=50)),
                ("value", models.FloatField()),
                ("unit", models.CharField(blank=True, default="", max_length=20)),
                ("timestamp", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="readings", to="inventory.iotdevice")),
            ],
            options={"ordering": ["-timestamp"]},
        ),
        migrations.AddIndex(
            model_name="iotreading",
            index=models.Index(fields=["device", "reading_type", "-timestamp"], name="inventory_iot_device_type_ts_idx"),
        ),
        # ── Mobile Money Transaction ─────────────────────────────────────────
        migrations.CreateModel(
            name="MobileMoneyTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tx_type", models.CharField(choices=[("cash_in","Cash In"),("cash_out","Cash Out"),("airtime","Airtime Top-Up"),("bill_payment","Bill Payment"),("reversal","Reversal"),("adjustment","Adjustment")], db_index=True, default="cash_in", max_length=20)),
                ("network", models.CharField(choices=[("airtel","Airtel Money"),("tnm","TNM Mpamba"),("other","Other")], db_index=True, default="airtel", max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("commission", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("customer_phone", models.CharField(blank=True, default="", max_length=20)),
                ("reference_number", models.CharField(blank=True, default="", max_length=50)),
                ("cash_movement", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("float_movement", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_money_transactions", to="tenants.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mm_transactions_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="mobilemoneytransaction",
            index=models.Index(fields=["business", "-created_at"], name="inventory_mm_biz_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilemoneytransaction",
            index=models.Index(fields=["business", "tx_type", "-created_at"], name="inventory_mm_biz_type_ts_idx"),
        ),
        # ── Mobile Money Credit ─────────────────────────────────────────────
        migrations.CreateModel(
            name="MobileMoneyCredit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_name", models.CharField(max_length=150)),
                ("customer_phone", models.CharField(blank=True, default="", max_length=20)),
                ("amount_credited", models.DecimalField(decimal_places=2, max_digits=12)),
                ("amount_repaid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("pending","Pending"),("partial","Partially Paid"),("paid","Fully Paid"),("overdue","Overdue")], db_index=True, default="pending", max_length=20)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_money_credits", to="tenants.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mm_credits_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        # ── Mobile Money Reconciliation ─────────────────────────────────────
        migrations.CreateModel(
            name="MobileMoneyReconciliation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("opening_cash", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("opening_float", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_cash_in", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_cash_out", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_float_in", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_float_out", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("expected_closing_cash", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("actual_closing_cash", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("difference", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_money_reconciliations", to="tenants.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mm_reconciliations_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date"]},
        ),
        migrations.AlterUniqueTogether(
            name="mobilemoneyreconciliation",
            unique_together={("business", "date")},
        ),
    ]
