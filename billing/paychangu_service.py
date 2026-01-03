# billing/paychangu_service.py
"""
PayChangu API integration for mobile money payments in Malawi.
Supports payment initiation, webhook verification, and transaction verification.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import requests  # type: ignore
    from requests.exceptions import HTTPError, RequestException  # type: ignore
except ImportError:
    requests = None  # type: ignore
    HTTPError = Exception  # type: ignore
    RequestException = Exception  # type: ignore


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

        logger.info(f"PayChangu checkout created successfully: tx_ref={tx_ref}, " f"checkout_url={checkout_url}")

        return {
            "status": "success",
            "checkout_url": checkout_url,
            "tx_ref": tx_ref,
            "raw_response": data,
            "message": "Checkout created successfully",
        }

    except HTTPError as e:
        # Get status code
        status_code = e.response.status_code if hasattr(e, "response") else "unknown"

        # Extract error details from response
        error_detail = ""
        response_body = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", error_data.get("error", str(error_data)))
            response_body = str(error_data)
        except Exception:
            # If JSON parsing fails, use raw text
            if hasattr(e.response, "text"):
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

    except RequestException as e:
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

    except HTTPError as e:
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

    except RequestException as e:
        logger.error(f"PayChangu verify request failed: {e}")
        return {"status": "ERROR", "message": f"Request failed: {e}"}

    except Exception as e:
        logger.error(f"Unexpected error verifying PayChangu payment: {e}")
        return {"status": "ERROR", "message": f"Unexpected error: {e}"}


def get_mobile_money_operators() -> Dict[str, Any]:
    """
    Fetch available mobile money operators from PayChangu.

    Returns:
        Dict with:
            - 'status': 'success' or 'error'
            - 'operators': List of operator dicts with {id, name, code, logo_url, ref_id}
            - 'message': Description
    """
    if not requests:
        return {"status": "error", "message": "requests module not installed", "operators": []}

    if not is_paychangu_configured():
        return {"status": "error", "message": "PayChangu not configured", "operators": []}

    base_url = settings.PAYCHANGU_API_BASE.rstrip("/")
    secret_key = settings.PAYCHANGU_SECRET_KEY

    url = f"{base_url}/mobile-money"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Parse operators list - handle different response structures
        operators = []
        if isinstance(data, list):
            operators = data
        elif isinstance(data, dict):
            operators = data.get("data") or data.get("operators") or data.get("result") or []

        logger.info(f"PayChangu operators fetched: {len(operators)} available")

        return {
            "status": "success",
            "operators": operators,
            "message": "Operators fetched successfully",
        }

    except RequestException as e:
        logger.error(f"PayChangu operators fetch failed: {e}")
        return {"status": "error", "message": f"Request failed: {e}", "operators": []}

    except Exception as e:
        logger.error(f"Unexpected error fetching PayChangu operators: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}", "operators": []}


def normalize_malawi_phone(phone: str) -> str:
    """
    Normalize Malawi phone number to 9 digits (no country code, no leading 0).

    Accepts:
        - 0991234567 (10 digits with leading 0)
        - 991234567 (9 digits)
        - +265991234567
        - 265991234567

    Returns:
        9-digit string (e.g. "991234567")

    Raises:
        ValueError if invalid format
    """
    # Remove all non-digits
    digits = "".join(ch for ch in phone if ch.isdigit())

    # Strip country code
    if digits.startswith("265"):
        digits = digits[3:]

    # Strip leading zero
    if digits.startswith("0"):
        digits = digits[1:]

    # Validate length
    if len(digits) != 9:
        raise ValueError(f"Phone number must be 9 digits after normalization, got {len(digits)}")

    return digits


def validate_test_mode_phone(phone: str, method: str) -> Dict[str, Any]:
    """
    Validate phone number for PayChangu test mode.

    Test numbers (9 digits, no leading 0):
    - Airtel success: 990000000
    - Airtel fail:    990000001
    - TNM success:    899817565
    - TNM fail:       899817566

    Args:
        phone: Phone number (any format)
        method: Payment method ('airtel' or 'tnm')

    Returns:
        Dict with 'valid': bool and 'message': str
    """
    try:
        normalized = normalize_malawi_phone(phone)
    except ValueError as e:
        return {"valid": False, "message": str(e)}

    # Test mode valid numbers
    valid_numbers = {
        "airtel": ["990000000", "990000001"],
        "tnm": ["899817565", "899817566"],
    }

    method_lower = method.lower()
    if method_lower in ("airtel_money", "airtel"):
        method_lower = "airtel"
    elif method_lower in ("tnm_mpamba", "tnm", "mpamba"):
        method_lower = "tnm"

    allowed = valid_numbers.get(method_lower, [])

    if normalized not in allowed:
        return {
            "valid": False,
            "message": (
                f"⚠️ Test mode: Please use PayChangu sandbox numbers only. "
                f"For {method.upper()}, use: {', '.join(allowed)}. "
                f"Switch to LIVE mode to use real phone numbers."
            ),
        }

    return {"valid": True, "message": "Test number valid"}


def get_operator_ref_id(method: str) -> Dict[str, Any]:
    """
    Get PayChangu operator ref_id for a given payment method (airtel/tnm).

    Uses caching (24h) and supports env overrides:
    - PAYCHANGU_AIRTEL_REF_ID
    - PAYCHANGU_TNM_REF_ID

    Args:
        method: Payment method name ('airtel', 'tnm', 'AIRTEL_MONEY', 'TNM_MPAMBA')

    Returns:
        Dict with:
            - 'status': 'success' or 'error'
            - 'ref_id': Operator reference ID
            - 'operator_name': Operator name
            - 'message': Description
    """
    import os

    # Normalize method name
    method = method.lower().strip()
    if method in ("airtel_money", "airtel"):
        method = "airtel"
    elif method in ("tnm_mpamba", "tnm", "mpamba"):
        method = "tnm"
    else:
        return {"status": "error", "message": f"Unknown payment method: {method}"}

    # Check env override first
    env_key = f"PAYCHANGU_{method.upper()}_REF_ID"
    env_ref_id = os.getenv(env_key, "").strip()
    if env_ref_id:
        logger.info(f"Using env override for {method}: {env_key}={env_ref_id[:8]}...")
        return {
            "status": "success",
            "ref_id": env_ref_id,
            "operator_name": method.upper(),
            "message": f"Using env override {env_key}",
        }

    # Try cache
    try:
        from django.core.cache import cache

        cache_key = f"paychangu_operators_{method}"
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Using cached operator ref_id for {method}")
            return cached
    except Exception:
        cache = None

    # Fetch operators from API
    result = get_mobile_money_operators()
    if result.get("status") != "success":
        return {
            "status": "error",
            "message": f"Failed to fetch operators: {result.get('message')}",
        }

    operators = result.get("operators", [])
    if not operators:
        return {"status": "error", "message": "No operators returned from PayChangu API"}

    # Find matching operator
    method_keywords = {
        "airtel": ["airtel"],
        "tnm": ["tnm", "mpamba"],
    }
    keywords = method_keywords.get(method, [])

    matched_operator = None
    for op in operators:
        op_name = (op.get("name") or "").lower()
        op_code = (op.get("code") or "").lower()

        for keyword in keywords:
            if keyword in op_name or keyword in op_code:
                matched_operator = op
                break

        if matched_operator:
            break

    if not matched_operator:
        logger.error(f"No operator found for {method}. Available: {[op.get('name') for op in operators]}")
        return {
            "status": "error",
            "message": f"PayChangu operator not found for {method}. Available: {', '.join(op.get('name', 'N/A') for op in operators[:3])}",
        }

    # Extract ref_id (handle different field names)
    ref_id = (
        matched_operator.get("ref_id")
        or matched_operator.get("uuid")
        or matched_operator.get("id")
        or matched_operator.get("operator_id")
    )

    if not ref_id:
        logger.error(
            f"Operator {matched_operator.get('name')} has no ref_id field. Keys: {list(matched_operator.keys())}"
        )
        return {
            "status": "error",
            "message": f"Operator {matched_operator.get('name')} missing ref_id",
        }

    operator_name = matched_operator.get("name", method.upper())

    logger.info(f"Resolved {method} => operator '{operator_name}' with ref_id={ref_id[:8]}...")

    response_data = {
        "status": "success",
        "ref_id": ref_id,
        "operator_name": operator_name,
        "message": f"Operator found: {operator_name}",
    }

    # Cache for 24 hours
    if cache:
        try:
            cache.set(cache_key, response_data, 86400)  # 24h
        except Exception:
            pass

    return response_data


def momo_initialize_payment(
    *,
    operator_ref_id: str,
    mobile: str,
    amount: Decimal,
    currency: str,
    tx_ref: str,
    charge_id: str,
    callback_url: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Initialize a mobile money direct charge payment (push prompt to phone).

    Args:
        operator_ref_id: Mobile money operator ref_id from get_mobile_money_operators()
        mobile: Customer phone number (normalized to 9 digits, e.g. 991234567)
        amount: Payment amount
        currency: Currency code (e.g. 'MWK')
        tx_ref: Unique transaction reference
        charge_id: Unique charge ID
        callback_url: Optional webhook callback URL
        meta: Optional metadata dict
        description: Payment description

    Returns:
        Dict with:
            - 'status': 'success' or 'error'
            - 'charge_id': Charge identifier
            - 'tx_ref': Transaction reference
            - 'raw_response': Full API response
            - 'message': Description
    """
    if not requests:
        return {"status": "error", "message": "requests module not installed"}

    if not is_paychangu_configured():
        return {"status": "error", "message": "PayChangu not configured"}

    # Normalize phone to 9 digits (PayChangu Malawi format)
    # Remove all non-digits
    mobile_digits = "".join(ch for ch in mobile if ch.isdigit())

    # Strip country code and leading zero
    if mobile_digits.startswith("265"):
        mobile_digits = mobile_digits[3:]  # Remove 265
    if mobile_digits.startswith("0"):
        mobile_digits = mobile_digits[1:]  # Remove leading 0

    # Should now be 9 digits
    if len(mobile_digits) != 9:
        return {
            "status": "error",
            "message": f"Invalid phone number format. Expected 9 digits, got {len(mobile_digits)}.",
        }

    # Convert amount to integer (MWK has no decimal places)
    try:
        amount_int = int(Decimal(amount).quantize(Decimal("1")))
    except Exception as e:
        return {"status": "error", "message": f"Invalid amount: {e}"}

    # Build payload - use correct PayChangu field names
    payload = {
        "tx_ref": tx_ref,
        "charge_id": charge_id,
        "amount": amount_int,  # INTEGER, not string
        "currency": currency,
        "mobile": mobile_digits,  # 9 digits without leading 0 or country code
        "mobile_money_operator_ref_id": operator_ref_id,  # Correct field name
        "description": description or "Payment",
    }

    if callback_url:
        payload["callback_url"] = callback_url

    if meta:
        payload["meta"] = meta

    base_url = settings.PAYCHANGU_API_BASE.rstrip("/")
    secret_key = settings.PAYCHANGU_SECRET_KEY

    url = f"{base_url}/mobile-money/payments/initialize"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Mask phone for logging
    masked_mobile = mobile_digits[:3] + "***" + mobile_digits[-2:] if len(mobile_digits) > 5 else "***"
    logger.info(
        f"PayChangu MoMo initialize: POST {url}\n"
        f"  tx_ref={tx_ref}, charge_id={charge_id}, amount={amount_int}, mobile={masked_mobile}, operator_ref_id={operator_ref_id}"
    )

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        logger.info(f"PayChangu MoMo response: HTTP {response.status_code}")

        response.raise_for_status()
        data = response.json()

        logger.info(f"PayChangu MoMo initialized: charge_id={charge_id}, tx_ref={tx_ref}")

        return {
            "status": "success",
            "charge_id": charge_id,
            "tx_ref": tx_ref,
            "raw_response": data,
            "message": "Mobile money payment initialized successfully",
        }

    except HTTPError as e:
        status_code = e.response.status_code if hasattr(e, "response") else "unknown"
        error_detail = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", error_data.get("error", str(error_data)))
        except Exception:
            if hasattr(e.response, "text"):
                error_detail = e.response.text[:200]
            else:
                error_detail = str(e)

        logger.error(f"PayChangu MoMo initialize failed:\n" f"  Status: {status_code}\n" f"  Error: {error_detail}")

        user_message = f"Payment initialization failed: {error_detail}"
        if status_code == 401:
            user_message = "Payment provider authentication failed. Please contact support."
        elif status_code == 400:
            user_message = f"Invalid payment request: {error_detail}"
        elif status_code >= 500:
            user_message = "Payment provider is temporarily unavailable. Please try again later."

        return {
            "status": "error",
            "message": user_message,
            "raw_response": {},
        }

    except RequestException as e:
        logger.error(f"PayChangu MoMo initialize request failed: {e}")
        return {"status": "error", "message": f"Request failed: {e}"}

    except Exception as e:
        logger.error(f"Unexpected error initializing PayChangu MoMo: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}


def momo_verify_payment(charge_id: str) -> Dict[str, Any]:
    """
    Verify a mobile money payment transaction with PayChangu.

    Args:
        charge_id: Charge identifier from momo_initialize_payment

    Returns:
        Dict with:
            - 'status': 'SUCCESS', 'PENDING', 'FAILED', or 'ERROR'
            - 'amount': Transaction amount
            - 'currency': Currency code
            - 'charge_id': Charge identifier
            - 'raw_response': Full API response
            - 'message': Description
    """
    if not requests:
        return {"status": "ERROR", "message": "requests module not installed"}

    if not is_paychangu_configured():
        return {"status": "ERROR", "message": "PayChangu not configured"}

    base_url = settings.PAYCHANGU_API_BASE.rstrip("/")
    secret_key = settings.PAYCHANGU_SECRET_KEY

    url = f"{base_url}/mobile-money/payments/{charge_id}/verify"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        result_data = data.get("data", {})
        status_raw = result_data.get("status", "").upper()

        # Map PayChangu status to our statuses
        if status_raw in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
            status = "SUCCESS"
        elif status_raw in ("PENDING", "PROCESSING"):
            status = "PENDING"
        elif status_raw in ("FAILED", "CANCELLED", "CANCELED"):
            status = "FAILED"
        else:
            status = "PENDING"

        logger.info(f"PayChangu MoMo verify result for {charge_id}: {status} (raw: {status_raw})")

        return {
            "status": status,
            "amount": result_data.get("amount", 0),
            "currency": result_data.get("currency", ""),
            "charge_id": result_data.get("charge_id", charge_id),
            "raw_response": data,
            "message": result_data.get("message", ""),
        }

    except HTTPError as e:
        error_detail = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", str(error_data))
        except Exception:
            error_detail = str(e)

        logger.error(f"PayChangu MoMo verify failed (HTTP {e.response.status_code}): {error_detail}")
        return {
            "status": "ERROR",
            "message": f"PayChangu API error: {error_detail}",
            "raw_response": {},
        }

    except RequestException as e:
        logger.error(f"PayChangu MoMo verify request failed: {e}")
        return {"status": "ERROR", "message": f"Request failed: {e}"}

    except Exception as e:
        logger.error(f"Unexpected error verifying PayChangu MoMo: {e}")
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
    expected_signature = hmac.new(webhook_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

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
            f"PayChangu webhook signature mismatch. " f"Expected: {expected_signature[:8]}..., Got: {signature[:8]}..."
        )

    return is_valid
