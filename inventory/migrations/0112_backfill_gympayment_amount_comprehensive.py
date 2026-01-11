# Generated manually to comprehensively fix GymPayment.amount field
"""
This migration comprehensively fixes the GymPayment.amount field by:
1. Backfilling amount=NULL cases (already done in 0111, but repeating for safety)
2. Backfilling amount=0 cases where membership_amount OR trainer_fee > 0
3. Using Django F expressions + Coalesce for robust calculation
4. Being idempotent (safe to run multiple times)

This ensures the dashboard ALWAYS shows correct revenue when payments exist.
"""

from decimal import Decimal
from django.db import migrations
from django.db.models import F, Q, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce


def backfill_gympayment_amount_comprehensive(apps, schema_editor):
    """
    Comprehensively backfill GymPayment.amount for BOTH:
    - amount IS NULL
    - amount == 0 AND (membership_amount > 0 OR trainer_fee > 0)
    
    Uses F expressions + Coalesce for efficiency and correctness.
    """
    GymPayment = apps.get_model("inventory", "GymPayment")
    
    # Find all problematic payments:
    # 1. amount is NULL, OR
    # 2. amount is 0 but membership_amount or trainer_fee is > 0
    problematic_payments = GymPayment.objects.filter(
        Q(amount__isnull=True) | 
        Q(
            Q(amount=0),
            Q(membership_amount__gt=0) | Q(trainer_fee__gt=0)
        )
    )
    
    count = problematic_payments.count()
    
    if count > 0:
        print(f"\n{'=' * 80}")
        print(f"BACKFILLING {count} GymPayment records with incorrect amount field...")
        print(f"{'=' * 80}\n")
        
        # Update using F expressions for efficiency
        # amount = membership_amount + trainer_fee (with Coalesce to handle NULL)
        problematic_payments.update(
            amount=ExpressionWrapper(
                Coalesce(F('membership_amount'), Decimal('0.00')) +
                Coalesce(F('trainer_fee'), Decimal('0.00')),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )
        
        print(f"[OK] Successfully backfilled {count} GymPayment records.")
        print(f"   Formula: amount = membership_amount + trainer_fee")
        print(f"{'=' * 80}\n")
    else:
        print("\n[OK] No GymPayment records need backfilling. All amount fields are correct.\n")


def reverse_backfill(apps, schema_editor):
    """
    Reverse migration: no-op since we're fixing data consistency.
    We don't want to break data by reverting the fix.
    """
    print("Reverse migration: No-op (preserving data integrity)")


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0111_fix_gym_payment_amount_field"),
    ]

    operations = [
        migrations.RunPython(
            backfill_gympayment_amount_comprehensive,
            reverse_backfill
        ),
    ]

