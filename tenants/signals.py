# tenants/signals.py
"""
Signals for tenant lifecycle management.

CRITICAL: These signals ensure SSOT for business creation side-effects.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


def _ensure_trial_subscription(business):
    """
    Ensure a trial subscription exists for the business.
    
    This is called on business creation to prevent 403 errors due to
    missing subscriptions in both tests and production.
    
    IMPORTANT: Only creates trial if no subscription exists.
    Does NOT override existing subscriptions.
    """
    try:
        from billing.models import BusinessSubscription
    except ImportError:
        # Billing app not installed
        return
    
    # Skip if subscription already exists
    try:
        existing = business.subscription
        if existing:
            return  # Already has subscription
    except Exception:
        pass  # No subscription, continue to create
    
    # Get trial days from settings (default 30)
    trial_days = getattr(settings, "BILLING_TRIAL_DAYS", 30)
    
    # Create trial subscription
    try:
        # Use the subscription model's built-in trial creation
        plan_name = getattr(settings, "BILLING_DEFAULT_PLAN", "standard")
        
        # Import the plan model to get default plan
        try:
            from billing.models import Plan
            plan = Plan.objects.filter(slug=plan_name).first()
            if not plan:
                # Create default plan if it doesn't exist
                plan = Plan.objects.create(
                    name="Standard Plan",
                    slug=plan_name,
                    price=0,  # Will be updated by billing logic
                )
        except Exception:
            plan = None
        
        # Create trial subscription
        if hasattr(BusinessSubscription, "start_trial"):
            BusinessSubscription.start_trial(
                business=business,
                plan=plan,
                days=trial_days,
            )
        else:
            # Fallback: create trial manually
            from django.utils import timezone
            from datetime import timedelta
            
            BusinessSubscription.objects.create(
                business=business,
                plan=plan,
                status="trial",
                trial_end=timezone.now() + timedelta(days=trial_days),
                current_period_start=timezone.now(),
                current_period_end=timezone.now() + timedelta(days=trial_days),
            )
    except Exception as e:
        # Log but don't fail business creation
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Failed to create trial subscription for business %s: %s",
            business.id,
            e,
            exc_info=True,
        )


@receiver(post_save, sender="tenants.Business", dispatch_uid="tenants.ensure_trial_on_business_creation")
def ensure_trial_on_business_creation(sender, instance, created, **kwargs):
    """
    Signal handler: ensure trial subscription exists after business creation.
    
    This prevents the subscription gate middleware from blocking access
    for newly created businesses in both tests and production.
    
    CRITICAL: This must be idempotent and never fail (catches all exceptions).
    """
    if not created:
        return  # Only run on creation
    
    # Skip in tests if BILLING_ENFORCE is False (tests should not need trials)
    # But still create trial in production and CI
    if not getattr(settings, "BILLING_ENFORCE", False):
        # Check if we're in testing mode
        testing = getattr(settings, "TESTING", False)
        if testing and not getattr(settings, "CI", False):
            return  # Skip trial creation in local tests
    
    _ensure_trial_subscription(instance)


def register_signals():
    """
    Explicit signal registration (can be called from AppConfig.ready()).
    
    Signals are auto-registered via @receiver decorator, but this function
    can be used for explicit registration if needed.
    """
    # Signals are already registered via @receiver decorator
    pass

