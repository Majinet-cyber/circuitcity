# billing/stripe_service.py
"""
Stripe integration for subscription checkout (card payments).
Uses Stripe Checkout Sessions for a hosted payment page.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import stripe  # type: ignore
except ImportError:
    stripe = None  # type: ignore


def is_stripe_configured() -> bool:
    """Check if Stripe keys are configured."""
    return bool(
        getattr(settings, "STRIPE_SECRET_KEY", "")
        and getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
    )


def create_checkout_session(
    *,
    business,
    plan,
    success_url: str,
    cancel_url: str,
    user_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a Stripe Checkout Session for a subscription.
    
    Args:
        business: Business instance
        plan: SubscriptionPlan instance
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels
        user_email: Customer email (optional)
    
    Returns:
        Dict with 'id', 'url', and optionally 'error' key if failed
    
    Raises:
        RuntimeError: If Stripe is not configured or stripe module not installed
    """
    if not stripe:
        raise RuntimeError("Stripe package not installed. Run: pip install stripe")
    
    if not is_stripe_configured():
        raise RuntimeError("Stripe keys not configured in environment variables")
    
    # Ensure we have a Stripe price ID
    stripe_price_id = getattr(plan, "stripe_price_id", None) or plan.meta.get("stripe_price_id")
    
    if not stripe_price_id:
        # Fallback: create price on-the-fly (not recommended for production)
        logger.warning(
            f"Plan {plan.code} has no stripe_price_id; creating ad-hoc price. "
            "For production, pre-create prices in Stripe dashboard and store IDs."
        )
        try:
            # Create a product if needed
            product = stripe.Product.create(
                name=plan.name,
                metadata={"plan_code": plan.code, "business_id": str(business.id)},
            )
            # Create recurring price
            price = stripe.Price.create(
                product=product.id,
                unit_amount=int(plan.amount * 100),  # Stripe uses cents
                currency=plan.currency.lower(),
                recurring={"interval": "month" if plan.interval == "month" else "year"},
                metadata={"plan_code": plan.code},
            )
            stripe_price_id = price.id
        except Exception as e:
            logger.error(f"Failed to create Stripe price: {e}")
            return {"error": f"Failed to create Stripe price: {e}"}
    
    # Create Checkout Session
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[
                {
                    "price": stripe_price_id,
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user_email,
            client_reference_id=str(business.id),
            metadata={
                "business_id": str(business.id),
                "plan_code": plan.code,
                "plan_id": str(plan.id),
            },
        )
        
        logger.info(
            f"Created Stripe Checkout Session {session.id} for business {business.id} plan {plan.code}"
        )
        
        return {
            "id": session.id,
            "url": session.url,
        }
    
    except Exception as e:
        logger.error(f"Stripe checkout session creation failed: {e}")
        return {"error": str(e)}


def construct_webhook_event(payload: bytes, sig_header: str) -> Optional[Any]:
    """
    Verify and construct Stripe webhook event.
    
    Args:
        payload: Raw request body (bytes)
        sig_header: Value of Stripe-Signature header
    
    Returns:
        Stripe Event object or None if verification fails
    """
    if not stripe:
        logger.error("Stripe module not available")
        return None
    
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured; cannot verify webhook")
        return None
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        return event
    except ValueError:
        # Invalid payload
        logger.error("Invalid Stripe webhook payload")
        return None
    except stripe.error.SignatureVerificationError:  # type: ignore
        # Invalid signature
        logger.error("Invalid Stripe webhook signature")
        return None
    except Exception as e:
        logger.error(f"Stripe webhook construction error: {e}")
        return None


def handle_checkout_completed(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process checkout.session.completed event.
    
    Returns dict with:
        - 'business_id': extracted from metadata
        - 'plan_code': extracted from metadata
        - 'stripe_subscription_id': from session
        - 'stripe_customer_id': from session
        - 'status': 'success' or 'error'
        - 'message': description
    """
    session = event_data.get("object", {})
    
    # Extract metadata
    metadata = session.get("metadata", {})
    business_id = metadata.get("business_id")
    plan_code = metadata.get("plan_code")
    
    if not business_id or not plan_code:
        return {
            "status": "error",
            "message": "Missing business_id or plan_code in session metadata",
        }
    
    # Extract Stripe IDs
    stripe_subscription_id = session.get("subscription")
    stripe_customer_id = session.get("customer")
    
    return {
        "status": "success",
        "business_id": business_id,
        "plan_code": plan_code,
        "stripe_subscription_id": stripe_subscription_id,
        "stripe_customer_id": stripe_customer_id,
        "message": "Checkout completed successfully",
    }


def handle_invoice_payment_succeeded(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process invoice.payment_succeeded event (recurring payments).
    
    Returns dict with subscription_id and status.
    """
    invoice = event_data.get("object", {})
    subscription_id = invoice.get("subscription")
    customer_id = invoice.get("customer")
    
    if not subscription_id:
        return {
            "status": "error",
            "message": "No subscription_id in invoice",
        }
    
    return {
        "status": "success",
        "stripe_subscription_id": subscription_id,
        "stripe_customer_id": customer_id,
        "message": "Invoice payment succeeded",
    }


def cancel_stripe_subscription(stripe_subscription_id: str) -> bool:
    """
    Cancel a Stripe subscription immediately.
    
    Returns True if successful, False otherwise.
    """
    if not stripe or not is_stripe_configured():
        logger.error("Stripe not configured")
        return False
    
    try:
        stripe.Subscription.delete(stripe_subscription_id)
        logger.info(f"Canceled Stripe subscription {stripe_subscription_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel Stripe subscription {stripe_subscription_id}: {e}")
        return False


def get_stripe_subscription(stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve subscription details from Stripe.
    
    Returns subscription dict or None.
    """
    if not stripe or not is_stripe_configured():
        return None
    
    try:
        sub = stripe.Subscription.retrieve(stripe_subscription_id)
        return {
            "id": sub.id,
            "status": sub.status,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "customer": sub.customer,
        }
    except Exception as e:
        logger.error(f"Failed to retrieve Stripe subscription {stripe_subscription_id}: {e}")
        return None

