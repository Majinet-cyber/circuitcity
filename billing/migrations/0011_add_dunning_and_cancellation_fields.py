# Generated migration for subscription cancellation + auto-billing/dunning

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0010_add_payment_failure_reason"),
    ]

    operations = [
        # Add dunning fields to BusinessSubscription
        migrations.AddField(
            model_name="businesssubscription",
            name="billing_phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Phone number (MSISDN) for automated billing prompts. Format: +265991234567",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="businesssubscription",
            name="grace_until",
            field=models.DateTimeField(
                blank=True,
                help_text="Grace period end (period_end + 2 days when renewal unpaid)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="businesssubscription",
            name="past_due_since",
            field=models.DateTimeField(
                blank=True,
                help_text="When subscription became past_due",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="businesssubscription",
            name="suspended_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When subscription was suspended",
                null=True,
            ),
        ),
        # Add dunning fields to Invoice
        migrations.AddField(
            model_name="invoice",
            name="next_attempt_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When to attempt next billing retry (dunning)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="attempt_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of billing attempts made",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="locked_for_dunning",
            field=models.BooleanField(
                default=False,
                help_text="Lock to prevent concurrent dunning processing",
            ),
        ),
        # Create BillingAttempt model
        migrations.CreateModel(
            name="BillingAttempt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "attempt_no",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Attempt number (1-6 for dunning retries)",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("initiated", "Initiated"),
                            ("failed", "Failed"),
                            ("succeeded", "Succeeded"),
                        ],
                        default="initiated",
                        max_length=20,
                    ),
                ),
                (
                    "provider_ref",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Payment provider reference (tx_ref, etc.)",
                        max_length=255,
                    ),
                ),
                (
                    "payment_session_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Payment session/checkout ID",
                        max_length=255,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Error message if failed",
                    ),
                ),
                (
                    "meta",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional metadata (method, amount, etc.)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="billing_attempts",
                        to="billing.invoice",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="billing_attempts",
                        to="billing.businesssubscription",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        # Add indexes for BillingAttempt
        migrations.AddIndex(
            model_name="billingattempt",
            index=models.Index(
                fields=["invoice", "attempt_no"],
                name="billing_bil_invoice_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="billingattempt",
            index=models.Index(
                fields=["subscription", "status"],
                name="billing_bil_subscri_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="billingattempt",
            index=models.Index(
                fields=["status", "created_at"],
                name="billing_bil_status_idx",
            ),
        ),
    ]
