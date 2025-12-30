# billing/paychangu_service.py
"""
PayChangu API integration for mobile money payments in Malawi.
Supports payment initiation, webhook verification, and transaction verification.
"""
from __future__ import annotations

import logging
import hmac
import hashlib
import time
from typing import Optional, Dict, Any
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore


def is_paychangu_configured() -> bool:
    """Check if PayChangu credentials are configured."""
    return bool(
        getattr(settings, "PAYCHANGU_PUBLIC_KEY", "")
        and getattr(settings, "PAYCHANGU_SECRET_KEY", "")
        and getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")
        and getattr(settings, "PAYCHANGU_API_BASE", "")
    )


def create_checkout(
    *,
    business,
    location,
    amount: Decimal,
    currency: str,
    tx_ref: str,
    return_url: str,
    callback_url: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    user_email: Optional[str] = None,
    user_phone: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Create a PayChangu checkout session.
    
    Args:
        business: Business instance
        location: Location instance
        amount: Payment amount
        currency: Currency code (e.g. 'MWK')
        tx_ref: Unique transaction reference
        return_url: URL to redirect user after payment
        callback_url: Optional callback URL (for backend notifications)
        meta: Optional metadata dict (will include business_id, location_id)
        user_email: Customer email
        user_phone: Customer phone
        description: Payment description
    
    Returns:
        Dict with:
            - 'status': 'success' or 'error'
            - 'checkout_url': URL to redirect user for payment
            - 'tx_ref': Transaction reference
            - 'raw_response': Full API response
            - 'message': Description
    """
    if not requests:
        return {"status": "error", "message": "requests module not installed"}
    
    if not is_paychangu_configured():
        return {"status": "error", "message": "PayChangu not configured"}
    
    # Build metadata (include tenant isolation data)
    payment_meta = {
        "business_id": str(business.id),
        "location_id": str(location.id) if location else "",
        "business_name": business.name,
    }
    if meta:
        payment_meta.update(meta)
    
    # Build payload per PayChangu Standard Checkout API
    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": currency,
        "return_url": return_url,
        "description": description or f"Payment for {business.name}",
        "customization": {
            "title": business.name,
            "description": description or "Payment",
        },
        "meta": payment_meta,
    }
    
    # Add optional fields
    if callback_url:
        payload["callback_url"] = callback_url
    
    if user_email:
        payload["email"] = user_email
        # Also add to customer object for compatibility
        payload.setdefault("customer", {})["email"] = user_email
    
    if user_phone:
        payload.setdefault("customer", {})["phone"] = user_phone
    
    # API request - PayChangu Standard Checkout endpoint
    base_url = settings.PAYCHANGU_API_BASE.rstrip("/")
    secret_key = settings.PAYCHANGU_SECRET_KEY
    
    # Correct endpoint: /payment (not /v1/payments)
    url = f"{base_url}/payment"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # Log exact URL and headers (mask secret key for security)
    masked_secret = f"{secret_key[:8]}...{secret_key[-4:]}" if len(secret_key) > 12 else "***"
    logger.info(
        f"PayChangu create_checkout: POST {url}\n"
        f"  Headers: Authorization: Bearer {masked_secret}, Content-Type: application/json\n"
        f"  Payload: tx_ref={tx_ref}, amount={amount}, currency={currency}"
    )
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        
        # Log response status
        logger.info(f"PayChangu response: HTTP {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        # Extract checkout URL
        checkout_url = data.get("data", {}).get("checkout_url") or data.get("checkout_url")
        
        if not checkout_url:
            logger.error(f"PayChangu checkout response missing checkout_url: {data}")
            return {
                "status": "error",
                "message": "Invalid PayChangu response: missing checkout_url. Please contact support.",
                "raw_response": data,
            }
        
        logger.info(
            f"PayChangu checkout created successfully: tx_ref={tx_ref}, "
            f"checkout_url={checkout_url}"
        )
        
        return {
            "status": "success",
            "checkout_url": checkout_url,
            "tx_ref": tx_ref,
            "raw_response": data,
            "message": "Checkout created successfully",
        }
    
    except requests.exceptions.HTTPError as e:
        # Get status code
        status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
        
        # Extract error details from response
        error_detail = ""
        response_body = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", error_data.get("error", str(error_data)))
            response_body = str(error_data)
        except Exception:
            # If JSON parsing fails, use raw text
            if hasattr(e.response, 'text'):
                response_body = e.response.text
                error_detail = response_body[:200]  # First 200 chars
            else:
                error_detail = str(e)
                response_body = error_detail
        
        # Log full error details
        logger.error(
            f"PayChangu checkout failed:\n"
            f"  URL: POST {url}\n"
            f"  Status Code: {status_code}\n"
            f"  Error: {error_detail}\n"
            f"  Response Body: {response_body[:500]}"
        )
        
        # Return user-friendly error message
        user_message = f"Payment provider error (HTTP {status_code}): {error_detail}"
        if status_code == 401:
            user_message = "Payment provider authentication failed. Please contact support."
        elif status_code == 400:
            user_message = f"Invalid payment request: {error_detail}"
        elif status_code == 405:
            user_message = "Payment provider endpoint error. Please contact support."
        elif status_code >= 500:
            user_message = "Payment provider is temporarily unavailable. Please try again later."
        
        return {
            "status": "error",
            "message": user_message,
            "raw_response": {},
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"PayChangu checkout request failed: {e}")
        return {"status": "error", "message": f"Request failed: {e}"}
    
    except Exception as e:
        logger.error(f"Unexpected error creating PayChangu checkout: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}


def verify_payment(tx_ref: str) -> Dict[str, Any]:
    """
    Verify a payment transaction with PayChangu.
    
    Args:
        tx_ref: Transaction reference
    
    Returns:
        Dict with:
            - 'status': 'SUCCESS', 'PENDING', 'FAILED', or 'ERROR'
            - 'amount': Transaction amount
            - 'currency': Currency code
            - 'tx_ref': Transaction reference
            - 'raw_response': Full API response
            - 'message': Description
    """
    if not requests:
        return {"status": "ERROR", "message": "requests module not installed"}
    
    if not is_paychangu_configured():
        return {"status": "ERROR", "message": "PayChangu not configured"}
    
    base_url = settings.PAYCHANGU_API_BASE.rstrip("/")
    secret_key = settings.PAYCHANGU_SECRET_KEY
    
    url = f"{base_url}/verify/{tx_ref}"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Parse response
        # Adjust based on actual PayChangu API response structure
        result_data = data.get("data", {})
        status_raw = result_data.get("status", "").upper()
        
        # Map PayChangu status to our statuses
        # Common statuses: 'successful', 'pending', 'failed'
        if status_raw in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
            status = "SUCCESS"
        elif status_raw in ("PENDING", "PROCESSING"):
            status = "PENDING"
        elif status_raw in ("FAILED", "CANCELLED", "CANCELED"):
            status = "FAILED"
        else:
            status = "PENDING"  # Default to pending for unknown statuses
        
        logger.info(f"PayChangu verify result for {tx_ref}: {status} (raw: {status_raw})")
        
        return {
            "status": status,
            "amount": result_data.get("amount", 0),
            "currency": result_data.get("currency", ""),
            "tx_ref": result_data.get("tx_ref", tx_ref),
            "raw_response": data,
            "message": result_data.get("message", ""),
        }
    
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", str(error_data))
        except Exception:
            error_detail = str(e)
        
        logger.error(f"PayChangu verify failed (HTTP {e.response.status_code}): {error_detail}")
        return {
            "status": "ERROR",
            "message": f"PayChangu API error: {error_detail}",
            "raw_response": {},
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"PayChangu verify request failed: {e}")
        return {"status": "ERROR", "message": f"Request failed: {e}"}
    
    except Exception as e:
        logger.error(f"Unexpected error verifying PayChangu payment: {e}")
        return {"status": "ERROR", "message": f"Unexpected error: {e}"}


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify PayChangu webhook signature using HMAC-SHA256.
    
    Args:
        payload: Raw request body (bytes)
        signature: Signature from request headers
    
    Returns:
        True if signature is valid, False otherwise
    """
    # Clean received signature
    signature = signature.strip()
    
    if not signature:
        logger.warning("PayChangu webhook missing signature")
        return False
    
    # Get and clean webhook secret (remove whitespace, quotes, newlines)
    webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")
    webhook_secret = webhook_secret.strip().strip('"').strip("'")
    
    if not webhook_secret:
        logger.error("PayChangu webhook secret not configured")
        return False
    
    # Compute HMAC-SHA256 signature over raw bytes
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Debug logging (safe - no raw secret)
    if getattr(settings, "DEBUG", False) or getattr(settings, "PAYCHANGU_WEBHOOK_DEBUG", False):
        secret_hash = hashlib.sha256(webhook_secret.encode("utf-8")).hexdigest()
        payload_hash = hashlib.sha256(payload).hexdigest()
        logger.debug(
            f"PayChangu webhook signature verification:\n"
            f"  payload_len={len(payload)}\n"
            f"  payload_sha256={payload_hash}\n"
            f"  secret_sha256={secret_hash}\n"
            f"  received_sig={signature}\n"
            f"  computed_sig={expected_signature}"
        )
    
    # Compare using constant-time comparison
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.warning(
            f"PayChangu webhook signature mismatch. "
            f"Expected: {expected_signature[:8]}..., Got: {signature[:8]}..."
        )
    
    return is_valid

