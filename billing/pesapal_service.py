# billing/pesapal_service.py
"""
Pesapal API v3 integration for mobile money and card payments in Africa.
Supports submitting orders and checking transaction status via IPN.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore


# Access token caching (tokens typically valid for ~5 minutes)
PESAPAL_TOKEN_CACHE_KEY = "pesapal_access_token"
PESAPAL_TOKEN_CACHE_TTL = 240  # 4 minutes (tokens valid for 5, cache slightly less)


def is_pesapal_configured() -> bool:
    """Check if Pesapal credentials are configured."""
    return bool(
        getattr(settings, "PESAPAL_CONSUMER_KEY", "")
        and getattr(settings, "PESAPAL_CONSUMER_SECRET", "")
        and getattr(settings, "PESAPAL_BASE_URL", "")
    )


def get_access_token(force_refresh: bool = False) -> Optional[str]:
    """
    Get Pesapal access token (cached for efficiency).

    Args:
        force_refresh: If True, bypass cache and request new token

    Returns:
        Access token string or None if failed
    """
    if not requests:
        logger.error("requests module not installed")
        return None

    if not is_pesapal_configured():
        logger.error("Pesapal not configured (missing consumer key/secret/base URL)")
        return None

    # Try cache first
    if not force_refresh:
        cached = cache.get(PESAPAL_TOKEN_CACHE_KEY)
        if cached:
            return cached

    # Request new token
    base_url = settings.PESAPAL_BASE_URL
    consumer_key = settings.PESAPAL_CONSUMER_KEY
    consumer_secret = settings.PESAPAL_CONSUMER_SECRET

    url = f"{base_url.rstrip('/')}/Auth/RequestToken"
    payload = {
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        token = data.get("token")
        if not token:
            logger.error(f"Pesapal token response missing 'token': {data}")
            return None

        # Cache token
        cache.set(PESAPAL_TOKEN_CACHE_KEY, token, PESAPAL_TOKEN_CACHE_TTL)
        logger.info("Pesapal access token obtained and cached")
        return token

    except requests.exceptions.RequestException as e:
        logger.error(f"Pesapal token request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting Pesapal token: {e}")
        return None


def submit_order_request(
    *,
    business,
    plan,
    callback_url: str,
    notification_url: Optional[str] = None,
    user_email: Optional[str] = None,
    user_phone: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit an order to Pesapal for payment.

    Args:
        business: Business instance
        plan: SubscriptionPlan instance
        callback_url: URL to redirect user after payment (browser callback)
        notification_url: IPN URL (optional, uses PESAPAL_IPN_ID from settings if not provided)
        user_email: Customer email
        user_phone: Customer phone

    Returns:
        Dict with:
            - 'redirect_url': URL to redirect user for payment
            - 'order_tracking_id': Pesapal tracking ID
            - 'merchant_reference': Our unique order reference
            - 'status': 'success' or 'error'
            - 'message': description
    """
    if not requests:
        return {"status": "error", "message": "requests module not installed"}

    if not is_pesapal_configured():
        return {"status": "error", "message": "Pesapal not configured"}

    access_token = get_access_token()
    if not access_token:
        return {"status": "error", "message": "Failed to obtain Pesapal access token"}

    # Build merchant reference (unique per order)
    timestamp = int(time.time())
    merchant_reference = f"sub-{business.id}-{plan.code}-{timestamp}"

    # Amount in Pesapal format (decimal)
    amount = float(plan.amount)
    currency = plan.currency

    # Build billing address (use business or defaults)
    billing_address = {
        "email_address": user_email or getattr(business, "email", "") or "noreply@example.com",
        "phone_number": user_phone or getattr(business, "phone", "") or "",
        "country_code": "MW",  # Malawi
        "first_name": getattr(business, "manager_name", "") or business.name[:50],
        "last_name": "",
        "line_1": "",
        "line_2": "",
        "city": "",
        "state": "",
        "postal_code": "",
        "zip_code": "",
    }

    # Notification ID (IPN)
    ipn_id = getattr(settings, "PESAPAL_IPN_ID", "")

    # Build payload
    payload = {
        "id": merchant_reference,
        "currency": currency,
        "amount": amount,
        "description": f"{plan.name} subscription for {business.name}",
        "callback_url": callback_url,
        "notification_id": ipn_id,
        "branch": business.name[:50],  # Branch name
        "billing_address": billing_address,
    }

    # Submit order
    base_url = settings.PESAPAL_BASE_URL
    url = f"{base_url.rstrip('/')}/Transactions/SubmitOrderRequest"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        # Extract response fields
        order_tracking_id = data.get("order_tracking_id")
        redirect_url = data.get("redirect_url")

        if not order_tracking_id or not redirect_url:
            logger.error(f"Pesapal order response missing fields: {data}")
            return {
                "status": "error",
                "message": f"Invalid Pesapal response: {data}",
            }

        logger.info(f"Pesapal order submitted: tracking_id={order_tracking_id}, " f"merchant_ref={merchant_reference}")

        return {
            "status": "success",
            "redirect_url": redirect_url,
            "order_tracking_id": order_tracking_id,
            "merchant_reference": merchant_reference,
            "message": "Order submitted successfully",
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Pesapal order submission failed: {e}")
        return {"status": "error", "message": f"Request failed: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error submitting Pesapal order: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}


def get_transaction_status(
    order_tracking_id: str,
    merchant_reference: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get transaction status from Pesapal.

    Args:
        order_tracking_id: Pesapal order tracking ID
        merchant_reference: Our merchant reference (optional but recommended)

    Returns:
        Dict with:
            - 'payment_method': e.g. 'Mobile Money', 'Card'
            - 'status_code': Pesapal status code (0=pending, 1=completed, 2=failed, etc.)
            - 'status': 'PENDING', 'COMPLETED', 'FAILED', 'CANCELLED', etc.
            - 'amount': transaction amount
            - 'currency': transaction currency
            - 'payment_account': masked account/phone
            - 'error': error message if any
    """
    if not requests:
        return {"status": "ERROR", "error": "requests module not installed"}

    if not is_pesapal_configured():
        return {"status": "ERROR", "error": "Pesapal not configured"}

    access_token = get_access_token()
    if not access_token:
        return {"status": "ERROR", "error": "Failed to obtain Pesapal access token"}

    base_url = settings.PESAPAL_BASE_URL
    url = f"{base_url.rstrip('/')}/Transactions/GetTransactionStatus"

    params = {"orderTrackingId": order_tracking_id}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Parse status
        status_code = data.get("payment_status_code", -1)

        # Map status codes to readable statuses
        # Pesapal status codes (from documentation):
        # 0 = Invalid, 1 = Completed, 2 = Failed, 3 = Reversed
        status_map = {
            0: "PENDING",
            1: "COMPLETED",
            2: "FAILED",
            3: "REVERSED",
        }
        status = status_map.get(status_code, "UNKNOWN")

        return {
            "status": status,
            "status_code": status_code,
            "payment_method": data.get("payment_method", ""),
            "amount": data.get("amount", 0),
            "currency": data.get("currency", ""),
            "payment_account": data.get("payment_account", ""),
            "description": data.get("description", ""),
            "message": data.get("message", ""),
            "confirmation_code": data.get("confirmation_code", ""),
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Pesapal status check failed: {e}")
        return {"status": "ERROR", "error": f"Request failed: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error checking Pesapal status: {e}")
        return {"status": "ERROR", "error": f"Unexpected error: {e}"}


def parse_ipn_notification(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse IPN notification query parameters from Pesapal.

    Pesapal sends GET request with:
        - OrderTrackingId
        - OrderMerchantReference
        - OrderNotificationType (e.g. 'COMPLETED')

    Returns:
        Dict with parsed fields
    """
    return {
        "order_tracking_id": query_params.get("OrderTrackingId", ""),
        "merchant_reference": query_params.get("OrderMerchantReference", ""),
        "notification_type": query_params.get("OrderNotificationType", ""),
    }


def register_ipn_url(ipn_url: str, notification_type: str = "POST") -> Dict[str, Any]:
    """
    Register IPN URL with Pesapal (optional, usually done once via dashboard).

    Args:
        ipn_url: Full IPN URL (e.g. https://example.com/billing/pesapal/ipn/)
        notification_type: 'POST' or 'GET' (Pesapal uses GET by default)

    Returns:
        Dict with 'ipn_id' and 'status'
    """
    if not requests:
        return {"status": "error", "message": "requests module not installed"}

    if not is_pesapal_configured():
        return {"status": "error", "message": "Pesapal not configured"}

    access_token = get_access_token()
    if not access_token:
        return {"status": "error", "message": "Failed to obtain Pesapal access token"}

    base_url = settings.PESAPAL_BASE_URL
    url = f"{base_url.rstrip('/')}/URLSetup/RegisterIPN"

    payload = {
        "url": ipn_url,
        "ipn_notification_type": notification_type,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        ipn_id = data.get("ipn_id")
        if not ipn_id:
            logger.error(f"Pesapal IPN registration missing ipn_id: {data}")
            return {"status": "error", "message": f"Invalid response: {data}"}

        logger.info(f"Pesapal IPN registered: ipn_id={ipn_id}, url={ipn_url}")
        return {
            "status": "success",
            "ipn_id": ipn_id,
            "url": ipn_url,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Pesapal IPN registration failed: {e}")
        return {"status": "error", "message": f"Request failed: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error registering Pesapal IPN: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}
