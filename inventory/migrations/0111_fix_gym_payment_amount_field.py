# Generated manually to fix GymPayment.amount field
"""
This migration fixes the GymPayment.amount field to:
1. Make it nullable (null=True, blank=True) to handle legacy data
2. Backfill any NULL values with membership_amount + trainer_fee
3. Ensure all future payments have amount populated via model save()
"""

from decimal import Decimal
from django.db import migrations, models
import django.core.validators


def backfill_null_amounts(apps, schema_editor):
    """
    Backfill any GymPayment records where amount is NULL.
    Calculate amount = membership_amount + trainer_fee
    """
    GymPayment = apps.get_model("inventory", "GymPayment")
    
    # Find all payments with NULL amount
    null_amount_payments = GymPayment.objects.filter(amount__isnull=True)
    count = null_amount_payments.count()
    
    if count > 0:
        print(f"Backfilling {count} GymPayment records with NULL amount...")
        
        # Update each payment
        for payment in null_amount_payments:
            # Calculate total from membership_amount + trainer_fee
            membership = payment.membership_amount or Decimal("0.00")
            trainer = payment.trainer_fee or Decimal("0.00")
            payment.amount = membership + trainer
            payment.save(update_fields=["amount"])
        
        print(f"Successfully backfilled {count} GymPayment records.")
    else:
        print("No GymPayment records with NULL amount found. Migration complete.")


def reverse_backfill(apps, schema_editor):
    """
    Reverse migration: no-op since we're just fixing data consistency.
    We don't want to set amount back to NULL.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0110_gymmember_qr_uuid_and_more"),
        ("inventory", "1018_clothingbarcodeunit"),
    ]

    operations = [
        # Step 1: Make amount field nullable
        migrations.AlterField(
            model_name="gympayment",
            name="amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Total amount paid (membership + trainer fee)",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        # Step 2: Backfill NULL amounts
        migrations.RunPython(backfill_null_amounts, reverse_backfill),
    ]

