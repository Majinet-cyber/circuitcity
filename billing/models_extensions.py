# billing/models_extensions.py
"""
Extensions and helper methods for BusinessSubscription model.
Provides subscription management utilities with audit trail support.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from billing.models import BusinessSubscription
    from tenants.models import Business
    from django.contrib.auth.models import User


def get_subscription_state(subscription: "BusinessSubscription") -> dict:
    """
    Get comprehensive subscription state for a business.

    Returns a dict with:
        - status: current status
        - is_active: boolean indicating if subscription allows access
        - days_remaining: days until expiration (if applicable)
        - trial_ends_at: trial end datetime
        - period_ends_at: current period end datetime
        - is_expired: boolean
        - is_in_grace: boolean
        - needs_payment: boolean
    """
    now = timezone.now()
    sub = subscription

    status = sub.status
    trial_end = sub.trial_end
    period_end = sub.current_period_end

    # Determine if subscription is active (allows access)
    is_active = status in ["trial", "active", "grace"]

    # Check if expired
    is_expired = False
    if status == "expired":
        is_expired = True
    elif period_end and period_end < now:
        is_expired = True
    elif status == "trial" and trial_end and trial_end < now:
        is_expired = True

    # Check if in grace period
    is_in_grace = status == "grace"

    # Needs payment
    needs_payment = status in ["past_due", "canceled"] or (status == "grace" and period_end and period_end < now)

    # Days remaining
    days_remaining = None
    if trial_end and status == "trial":
        delta = trial_end - now
        days_remaining = max(0, delta.days)
    elif period_end and status in ["active", "grace"]:
        delta = period_end - now
        days_remaining = max(0, delta.days)

    # Get plan name if available
    plan_name = "None"
    try:
        if hasattr(sub, "plan") and sub.plan:
            plan_name = sub.plan.name
    except Exception:
        pass

    # Get start date
    started_on = None
    try:
        if hasattr(sub, "created_at"):
            started_on = sub.created_at
    except Exception:
        pass

    # Get renewal date (current_period_end as the renewal date)
    renews_on = period_end

    return {
        "status": status,
        "is_active": is_active and not is_expired,
        "is_expired": is_expired,
        "is_in_grace": is_in_grace,
        "needs_payment": needs_payment,
        "days_remaining": days_remaining if days_remaining is not None else 0,
        "trial_ends_at": trial_end,
        "period_ends_at": period_end,
        "plan_name": plan_name,
        "renews_on": renews_on,
        "started_on": started_on,
    }


def extend_subscription_days(
    subscription: "BusinessSubscription", days: int, *, reason: str, actor: "User", create_audit: bool = True
) -> dict:
    """
    Extend (or reduce) subscription by a number of days.

    Args:
        subscription: BusinessSubscription instance
        days: Number of days to add (positive) or subtract (negative)
        reason: Required explanation for the change
        actor: HQ staff member performing the action
        create_audit: Whether to create SupportActionLog entry

    Returns:
        dict with before/after state
    """
    from billing.models import BusinessSubscription

    if not reason or not reason.strip():
        raise ValueError("Reason is required for subscription changes")

    now = timezone.now()

    # Capture before state
    before_state = {
        "status": subscription.status,
        "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "next_billing_date": subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
    }

    # Determine which date to extend
    if subscription.status == BusinessSubscription.Status.TRIAL:
        # Extend trial_end
        if subscription.trial_end:
            new_trial_end = subscription.trial_end + timedelta(days=days)
        else:
            new_trial_end = now + timedelta(days=days)

        subscription.trial_end = new_trial_end
        subscription.current_period_end = new_trial_end
        subscription.next_billing_date = new_trial_end

    elif subscription.status in [BusinessSubscription.Status.ACTIVE, BusinessSubscription.Status.GRACE]:
        # Extend current_period_end
        if subscription.current_period_end:
            new_period_end = subscription.current_period_end + timedelta(days=days)
        else:
            new_period_end = now + timedelta(days=days)

        subscription.current_period_end = new_period_end
        subscription.next_billing_date = new_period_end

        # If was in grace, move back to active
        if subscription.status == BusinessSubscription.Status.GRACE and days > 0:
            subscription.status = BusinessSubscription.Status.ACTIVE

    else:
        # For canceled/expired, activate with the specified days
        new_period_end = now + timedelta(days=abs(days))
        subscription.status = BusinessSubscription.Status.ACTIVE
        subscription.current_period_start = now
        subscription.current_period_end = new_period_end
        subscription.next_billing_date = new_period_end
        subscription.trial_end = None
        subscription.canceled_at = None
        subscription.canceled_by = None

    subscription.save()

    # Capture after state
    after_state = {
        "status": subscription.status,
        "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "next_billing_date": subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
    }

    # Create audit log
    if create_audit:
        try:
            from hq.models import SupportActionLog, SupportActionType

            SupportActionLog.objects.create(
                actor=actor,
                business=subscription.business,
                action_type=SupportActionType.EXTEND_SUBSCRIPTION,
                reason=reason,
                payload_before=before_state,
                payload_after=after_state,
                entity_type="BusinessSubscription",
                entity_id=str(subscription.id),
            )
        except Exception:
            # Don't fail the operation if audit logging fails
            pass

    return {"before": before_state, "after": after_state}


def revoke_subscription(
    subscription: "BusinessSubscription", *, reason: str, actor: "User", create_audit: bool = True
) -> dict:
    """
    Revoke/cancel a subscription immediately (hard stop).

    Args:
        subscription: BusinessSubscription instance
        reason: Required explanation
        actor: HQ staff member
        create_audit: Whether to create audit log

    Returns:
        dict with before/after state
    """
    from billing.models import BusinessSubscription

    if not reason or not reason.strip():
        raise ValueError("Reason is required for revoking subscriptions")

    now = timezone.now()

    # Capture before state
    before_state = {
        "status": subscription.status,
        "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "canceled_at": subscription.canceled_at.isoformat() if subscription.canceled_at else None,
        "canceled_by_id": subscription.canceled_by_id,
    }

    # Revoke
    subscription.status = BusinessSubscription.Status.CANCELED
    subscription.canceled_at = now
    subscription.canceled_by = actor

    # Set period end to now (immediate revocation)
    subscription.current_period_end = now
    subscription.next_billing_date = None

    subscription.save()

    # Capture after state
    after_state = {
        "status": subscription.status,
        "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "canceled_at": subscription.canceled_at.isoformat() if subscription.canceled_at else None,
        "canceled_by_id": subscription.canceled_by_id,
    }

    # Create audit log
    if create_audit:
        try:
            from hq.models import SupportActionLog, SupportActionType

            SupportActionLog.objects.create(
                actor=actor,
                business=subscription.business,
                action_type=SupportActionType.REVOKE_SUBSCRIPTION,
                reason=reason,
                payload_before=before_state,
                payload_after=after_state,
                entity_type="BusinessSubscription",
                entity_id=str(subscription.id),
            )
        except Exception:
            pass

    return {"before": before_state, "after": after_state}


def suspend_subscription(
    subscription: "BusinessSubscription", *, reason: str, actor: "User", days: int = 0, create_audit: bool = True
) -> dict:
    """
    Temporarily suspend a subscription.
    Similar to revoke but can specify when it expires.

    Args:
        subscription: BusinessSubscription instance
        reason: Required explanation
        actor: HQ staff member
        days: Days until suspension expires (0 = indefinite)
        create_audit: Whether to create audit log

    Returns:
        dict with before/after state
    """
    from billing.models import BusinessSubscription

    if not reason or not reason.strip():
        raise ValueError("Reason is required for suspending subscriptions")

    now = timezone.now()

    before_state = {
        "status": subscription.status,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
    }

    # Suspend (use CANCELED status with metadata)
    subscription.status = BusinessSubscription.Status.CANCELED
    subscription.canceled_at = now
    subscription.canceled_by = actor

    if days > 0:
        # Temporary suspension
        suspension_end = now + timedelta(days=days)
        subscription.meta = subscription.meta or {}
        subscription.meta["suspension_end"] = suspension_end.isoformat()
        subscription.meta["suspension_reason"] = reason
    else:
        # Indefinite suspension
        subscription.current_period_end = now

    subscription.save()

    after_state = {
        "status": subscription.status,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "suspension_info": subscription.meta.get("suspension_end"),
    }

    if create_audit:
        try:
            from hq.models import SupportActionLog, SupportActionType

            SupportActionLog.objects.create(
                actor=actor,
                business=subscription.business,
                action_type=SupportActionType.SUSPEND_SUBSCRIPTION,
                reason=reason,
                payload_before=before_state,
                payload_after=after_state,
                entity_type="BusinessSubscription",
                entity_id=str(subscription.id),
            )
        except Exception:
            pass

    return {"before": before_state, "after": after_state}


def activate_subscription(
    subscription: "BusinessSubscription", *, reason: str, actor: "User", days: int = 30, create_audit: bool = True
) -> dict:
    """
    Activate (or reactivate) a subscription.

    Args:
        subscription: BusinessSubscription instance
        reason: Required explanation
        actor: HQ staff member
        days: Number of days to activate for (default 30)
        create_audit: Whether to create audit log

    Returns:
        dict with before/after state
    """
    from billing.models import BusinessSubscription

    if not reason or not reason.strip():
        raise ValueError("Reason is required for activating subscriptions")

    now = timezone.now()

    before_state = {
        "status": subscription.status,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
    }

    # Activate
    subscription.status = BusinessSubscription.Status.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=days)
    subscription.next_billing_date = now + timedelta(days=days)
    subscription.canceled_at = None
    subscription.canceled_by = None

    # Clear suspension metadata
    if subscription.meta and "suspension_end" in subscription.meta:
        subscription.meta.pop("suspension_end", None)
        subscription.meta.pop("suspension_reason", None)

    subscription.save()

    after_state = {
        "status": subscription.status,
        "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
    }

    if create_audit:
        try:
            from hq.models import SupportActionLog, SupportActionType

            SupportActionLog.objects.create(
                actor=actor,
                business=subscription.business,
                action_type=SupportActionType.ACTIVATE_SUBSCRIPTION,
                reason=reason,
                payload_before=before_state,
                payload_after=after_state,
                entity_type="BusinessSubscription",
                entity_id=str(subscription.id),
            )
        except Exception:
            pass

    return {"before": before_state, "after": after_state}


def set_subscription_plan(
    subscription: "BusinessSubscription", plan_code: str, *, reason: str, actor: "User", create_audit: bool = True
) -> dict:
    """
    Change subscription plan.

    Args:
        subscription: BusinessSubscription instance
        plan_code: New plan code (starter/pro/promax)
        reason: Required explanation
        actor: HQ staff member
        create_audit: Whether to create audit log

    Returns:
        dict with before/after state
    """
    from billing.models import SubscriptionPlan

    if not reason or not reason.strip():
        raise ValueError("Reason is required for changing plans")

    # Get old plan info
    old_plan = subscription.plan
    before_state = {
        "plan_code": old_plan.code if old_plan else None,
        "plan_name": old_plan.name if old_plan else None,
        "plan_amount": str(old_plan.amount) if old_plan else None,
    }

    # Get new plan
    try:
        new_plan = SubscriptionPlan.objects.get(code=plan_code, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        raise ValueError(f"Plan with code '{plan_code}' not found or inactive")

    # Update subscription
    subscription.plan = new_plan
    subscription.save()

    after_state = {
        "plan_code": new_plan.code,
        "plan_name": new_plan.name,
        "plan_amount": str(new_plan.amount),
    }

    if create_audit:
        try:
            from hq.models import SupportActionLog, SupportActionType

            SupportActionLog.objects.create(
                actor=actor,
                business=subscription.business,
                action_type=SupportActionType.CHANGE_PLAN,
                reason=reason,
                payload_before=before_state,
                payload_after=after_state,
                entity_type="BusinessSubscription",
                entity_id=str(subscription.id),
            )
        except Exception:
            pass

    return {"before": before_state, "after": after_state}
