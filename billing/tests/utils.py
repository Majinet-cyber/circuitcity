# billing/tests/utils.py
"""
Test utilities for billing tests.
Ensures tests work with --reuse-db and avoid unique constraint errors.
"""
from decimal import Decimal

from billing.models import SubscriptionPlan


def ensure_plan(code: str, *, name: str, amount: Decimal, **defaults) -> SubscriptionPlan:
    """
    Create or update a SubscriptionPlan, avoiding unique constraint errors.

    Uses update_or_create to ensure tests work with --reuse-db.

    Args:
        code: Unique plan code
        name: Plan name
        amount: Plan amount
        **defaults: Additional fields (currency, interval, etc.)

    Returns:
        SubscriptionPlan instance
    """
    # Set sensible defaults
    defaults.setdefault("currency", "MWK")
    defaults.setdefault("interval", SubscriptionPlan.Interval.MONTH)
    defaults.setdefault("is_active", True)

    plan, created = SubscriptionPlan.objects.update_or_create(
        code=code,
        defaults={"name": name, "amount": amount, **defaults},
    )
    return plan
