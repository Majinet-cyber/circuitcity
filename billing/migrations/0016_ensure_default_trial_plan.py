# billing/migrations/0016_ensure_default_trial_plan.py
"""
Data migration to ensure a default trial plan exists.

This migration is IDEMPOTENT and safe to run multiple times.
It prevents signup failures caused by missing plans.

CRITICAL: This must run before any signup can happen in a fresh deployment.
"""
from decimal import Decimal

from django.db import migrations


def ensure_default_plan_exists(apps, schema_editor):
    """
    Create the 'starter' plan if no plans exist.
    
    This is idempotent - it only creates the plan if:
    1. No plan with code='starter' exists, AND
    2. No other active plans exist
    """
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")
    
    # Check if 'starter' plan already exists
    if SubscriptionPlan.objects.filter(code="starter").exists():
        print("  [OK] 'starter' plan already exists")
        return
    
    # Check if any active plans exist
    if SubscriptionPlan.objects.filter(is_active=True).exists():
        print("  [OK] Active plans exist, skipping default plan creation")
        return
    
    # Create the default starter plan
    SubscriptionPlan.objects.create(
        code="starter",
        name="Starter",
        description="Free trial plan for new businesses. Upgrade anytime.",
        currency="MWK",
        amount=Decimal("0.00"),
        interval="month",
        max_stores=1,
        max_agents=3,
        features={
            "trial": True,
            "auto_created": True,
            "created_by_migration": "0016_ensure_default_trial_plan",
        },
        is_active=True,
        sort_order=1,
    )
    print("  [CREATED] Default 'starter' trial plan")


def noop_reverse(apps, schema_editor):
    """
    Reverse migration is a no-op.
    
    We don't delete the plan on reverse because:
    1. Businesses may already be using it
    2. Deleting it could cause IntegrityErrors
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0015_rename_billing_pen_busines_idx_billing_pen_busines_dc3b9f_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(
            ensure_default_plan_exists,
            noop_reverse,
            elidable=True,  # Can be optimized away if no-op
        ),
    ]

