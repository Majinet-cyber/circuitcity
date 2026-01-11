# tenants/signals.py
"""
Signals for tenant lifecycle management.

CRITICAL: These signals ensure SSOT for business creation side-effects.

IMPORTANT CHANGES (fix/cypress-pharmacy):
- Trial subscription creation now uses transaction.on_commit() to avoid
  poisoning the signup transaction with IntegrityError
- Uses SSOT plan resolver that GUARANTEES a valid plan
- Idempotent and never-fail design to prevent signup breakage
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from tenants.models import Business

logger = logging.getLogger(__name__)


def _safe_start_trial(business_id: int) -> None:
    """
    Safely create a trial subscription for a business.
    
    This function is designed to be called via transaction.on_commit()
    after the business creation transaction has completed.
    
    CRITICAL PROPERTIES:
    1. NEVER raises exceptions (logs errors instead)
    2. Uses SSOT plan resolver (always gets a valid plan)
    3. Idempotent (won't create duplicate subscriptions)
    4. Transaction-safe (runs outside the signup atomic block)
    
    Args:
        business_id: The ID of the business to create trial for
    """
    try:
        from tenants.models import Business
        
        # Fetch the business fresh (we're in a new transaction context)
        try:
            business = Business.objects.get(pk=business_id)
        except Business.DoesNotExist:
            logger.warning(
                "Business %s does not exist when trying to create trial. "
                "May have been deleted or rolled back.",
                business_id,
            )
            return
        
        _ensure_trial_subscription(business)
        
    except Exception as e:
        # NEVER let this fail the business creation
        logger.error(
            "Failed to create trial subscription for business %s: %s",
            business_id,
            e,
            exc_info=True,
        )


def _ensure_trial_subscription(business: "Business") -> None:
    """
    Ensure a trial subscription exists for the business.
    
    Uses the SSOT plan resolver to guarantee a valid plan is always used.
    
    IMPORTANT: This is idempotent and never fails.
    - If subscription already exists, returns immediately
    - If no plans exist, creates a fallback plan
    - Always creates subscription with a valid plan_id
    
    Args:
        business: The Business instance to create trial for
    """
    try:
        from billing.models import BusinessSubscription
    except ImportError:
        # Billing app not installed
        logger.debug("Billing app not installed, skipping trial creation")
        return
    
    # Check if subscription already exists (idempotent)
    try:
        existing = getattr(business, "subscription", None)
        if existing is not None:
            logger.debug(
                "Business %s already has subscription (status=%s), skipping trial creation",
                business.id,
                existing.status,
            )
            return
    except Exception:
        # No subscription relation, continue to create
        pass
    
    # Also check via direct query (more reliable)
    if BusinessSubscription.objects.filter(business=business).exists():
        logger.debug(
            "Business %s already has subscription (found via query), skipping",
            business.id,
        )
        return
    
    # Get trial days from settings
    trial_days = getattr(settings, "BILLING_TRIAL_DAYS", 30)
    
    # Use SSOT plan resolver - GUARANTEED to return a valid plan
    try:
        from billing.services.plan_resolver import get_default_trial_plan
        
        plan = get_default_trial_plan(
            business_kind=getattr(business, "business_kind", None),
            create_if_missing=True,  # CRITICAL: Always create fallback if needed
        )
    except Exception as e:
        logger.error(
            "CRITICAL: Plan resolver failed for business %s: %s. "
            "Attempting fallback plan creation.",
            business.id,
            e,
            exc_info=True,
        )
        # Last resort: try to get any plan or create one
        try:
            from billing.models import SubscriptionPlan
            from decimal import Decimal
            
            plan = SubscriptionPlan.objects.filter(is_active=True).first()
            if not plan:
                plan, _ = SubscriptionPlan.objects.get_or_create(
                    code="starter",
                    defaults={
                        "name": "Starter",
                        "amount": Decimal("0.00"),
                        "is_active": True,
                    },
                )
        except Exception as fallback_error:
            logger.error(
                "CRITICAL: Even fallback plan creation failed for business %s: %s",
                business.id,
                fallback_error,
                exc_info=True,
            )
            return  # Give up but don't crash
    
    # Create trial subscription with guaranteed plan
    try:
        if hasattr(BusinessSubscription, "start_trial"):
            subscription = BusinessSubscription.start_trial(
                business=business,
                plan=plan,
                days=trial_days,
            )
            logger.info(
                "Created trial subscription for business %s with plan %s (days=%d)",
                business.id,
                plan.code,
                trial_days,
            )
        else:
            # Fallback: create subscription manually
            from datetime import timedelta
            from django.utils import timezone
            
            now = timezone.now()
            trial_end = now + timedelta(days=trial_days)
            
            subscription = BusinessSubscription.objects.create(
                business=business,
                plan=plan,
                status="trial",
                trial_end=trial_end,
                current_period_start=now,
                current_period_end=trial_end,
            )
            logger.info(
                "Created trial subscription (manual) for business %s with plan %s",
                business.id,
                plan.code,
            )
            
    except Exception as e:
        logger.error(
            "Failed to create trial subscription for business %s (plan=%s): %s",
            business.id,
            plan.code if plan else "None",
            e,
            exc_info=True,
        )


@receiver(post_save, sender="tenants.Business", dispatch_uid="tenants.ensure_trial_on_business_creation")
def ensure_trial_on_business_creation(sender, instance, created, **kwargs):
    """
    Signal handler: schedule trial subscription creation after business is committed.
    
    CRITICAL DESIGN DECISIONS:
    1. Uses transaction.on_commit() to avoid poisoning signup transactions
    2. Never raises exceptions (all errors are logged, not thrown)
    3. Respects BILLING_ENFORCE and TESTING settings
    
    This prevents the IntegrityError + TransactionManagementError cascade
    that was breaking manager signup.
    """
    if not created:
        return  # Only run on creation
    
    # Skip in local tests if BILLING_ENFORCE is False
    # (tests that need subscriptions should create them explicitly)
    billing_enforce = getattr(settings, "BILLING_ENFORCE", False)
    testing = getattr(settings, "TESTING", False)
    ci = getattr(settings, "CI", False)
    
    if not billing_enforce and testing and not ci:
        logger.debug(
            "Skipping trial creation for business %s (BILLING_ENFORCE=%s, TESTING=%s, CI=%s)",
            instance.id,
            billing_enforce,
            testing,
            ci,
        )
        return
    
    # Schedule trial creation AFTER the transaction commits
    # This is CRITICAL - it ensures:
    # 1. Business is fully saved and committed
    # 2. Default location creation (also in signals) can complete
    # 3. Any IntegrityError in trial creation won't roll back the business
    business_id = instance.id
    
    def _deferred_trial_creation():
        """Closure to capture business_id and call safe trial creation."""
        _safe_start_trial(business_id)
    
    try:
        transaction.on_commit(_deferred_trial_creation)
        logger.debug(
            "Scheduled trial creation for business %s via on_commit",
            business_id,
        )
    except Exception as e:
        # Even scheduling should never fail, but log if it does
        logger.error(
            "Failed to schedule trial creation for business %s: %s",
            business_id,
            e,
            exc_info=True,
        )


def register_signals():
    """
    Explicit signal registration (can be called from AppConfig.ready()).
    
    Signals are auto-registered via @receiver decorator, but this function
    can be used for explicit registration if needed.
    """
    # Signals are already registered via @receiver decorator
    pass
