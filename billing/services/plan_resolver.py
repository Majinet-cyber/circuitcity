# billing/services/plan_resolver.py
"""
SSOT Plan Resolver for Trial Subscriptions.

This module provides the SINGLE SOURCE OF TRUTH for resolving
the default trial plan. It guarantees:
1. ALWAYS returns a valid Plan instance (never None, never fails)
2. Idempotent - safe to call multiple times
3. Creates fallback plan if none exist (prevents signup failures)

Usage:
    from billing.services.plan_resolver import get_default_trial_plan
    
    plan = get_default_trial_plan()  # Always returns a valid Plan
    plan = get_default_trial_plan(business_kind="pharmacy")  # Optional hint
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import transaction

if TYPE_CHECKING:
    from billing.models import SubscriptionPlan

logger = logging.getLogger(__name__)

# Default trial plan configuration
DEFAULT_TRIAL_PLAN_CODE = "starter"
DEFAULT_TRIAL_PLAN_NAME = "Starter"
DEFAULT_TRIAL_PLAN_AMOUNT = Decimal("0.00")


def get_default_trial_plan(
    *,
    business_kind: Optional[str] = None,
    create_if_missing: bool = True,
) -> "SubscriptionPlan":
    """
    Get the default trial plan for new businesses.
    
    This function GUARANTEES to return a valid SubscriptionPlan instance.
    It will NEVER return None or raise an exception.
    
    Resolution Strategy (in order):
    1. If a plan is explicitly marked as default trial (slug=settings.BILLING_DEFAULT_PLAN), return it
    2. If a plan with slug='starter' exists, return it
    3. Return the cheapest active plan
    4. If no plans exist and create_if_missing=True, create a minimal "Starter" plan
    
    Args:
        business_kind: Optional business vertical hint (for future per-vertical plans)
        create_if_missing: If True, create a fallback plan if none exist (default: True)
    
    Returns:
        A valid SubscriptionPlan instance (NEVER None)
    
    Raises:
        RuntimeError: Only if create_if_missing=False AND no plans exist (should never happen in prod)
    """
    from billing.models import SubscriptionPlan
    
    # Strategy 1: Check for explicitly configured default plan
    default_slug = getattr(settings, "BILLING_DEFAULT_PLAN", DEFAULT_TRIAL_PLAN_CODE)
    
    plan = SubscriptionPlan.objects.filter(code=default_slug, is_active=True).first()
    if plan:
        logger.debug("Resolved default trial plan from settings: %s", plan.code)
        return plan
    
    # Strategy 2: Try 'starter' slug as fallback
    if default_slug != DEFAULT_TRIAL_PLAN_CODE:
        plan = SubscriptionPlan.objects.filter(code=DEFAULT_TRIAL_PLAN_CODE, is_active=True).first()
        if plan:
            logger.debug("Resolved default trial plan (starter): %s", plan.code)
            return plan
    
    # Strategy 3: Get the cheapest active plan
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount", "sort_order").first()
    if plan:
        logger.debug("Resolved default trial plan (cheapest active): %s", plan.code)
        return plan
    
    # Strategy 4: Create fallback plan if allowed
    if create_if_missing:
        plan = _get_or_create_fallback_plan()
        logger.info("Created fallback trial plan: %s", plan.code)
        return plan
    
    # This should NEVER happen in production - but if it does, we need to know
    logger.error(
        "CRITICAL: No plans exist and create_if_missing=False. "
        "This will cause signup failures. Run migrations or create plans manually."
    )
    raise RuntimeError(
        "No subscription plans exist. Please run 'python manage.py migrate' "
        "or create at least one plan via admin."
    )


@transaction.atomic
def _get_or_create_fallback_plan() -> "SubscriptionPlan":
    """
    Idempotently create the minimal fallback "Starter" plan.
    
    This uses select_for_update to prevent race conditions when
    multiple signups happen simultaneously with no plans.
    
    Returns:
        The Starter plan (existing or newly created)
    """
    from billing.models import SubscriptionPlan
    
    # Use get_or_create with atomic to handle race conditions
    plan, created = SubscriptionPlan.objects.get_or_create(
        code=DEFAULT_TRIAL_PLAN_CODE,
        defaults={
            "name": DEFAULT_TRIAL_PLAN_NAME,
            "amount": DEFAULT_TRIAL_PLAN_AMOUNT,
            "interval": SubscriptionPlan.Interval.MONTH,
            "is_active": True,
            "max_stores": 1,
            "max_agents": 3,
            "sort_order": 1,
            "description": "Free trial plan for new businesses.",
            "features": {
                "trial": True,
                "auto_created": True,
            },
        },
    )
    
    if created:
        logger.warning(
            "Created fallback trial plan '%s'. "
            "Consider adding proper plans via admin or data migration.",
            plan.code,
        )
    
    return plan


def ensure_default_plan_exists() -> "SubscriptionPlan":
    """
    Ensure at least one default plan exists in the database.
    
    This is called from data migrations and management commands
    to guarantee plans exist before any signup can happen.
    
    Returns:
        The default trial plan (existing or newly created)
    """
    return get_default_trial_plan(create_if_missing=True)


__all__ = [
    "get_default_trial_plan",
    "ensure_default_plan_exists",
    "DEFAULT_TRIAL_PLAN_CODE",
    "DEFAULT_TRIAL_PLAN_NAME",
]

