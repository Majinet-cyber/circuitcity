"""
integrations/paychangu_client.py

PayChangu mobile-money payment integration for TengaSale.
Supports checkout initiation, transaction verification, webhook signature
validation, and mobile-money direct charges (Airtel / TNM).

Configuration (settings.py / .env):
    PAYCHANGU_PUBLIC_KEY
    PAYCHANGU_SECRET_KEY
    PAYCHANGU_WEBHOOK_SECRET
    PAYCHANGU_API_BASE          default: https://api.paychangu.com
    PAYCHANGU_CALLBACK_URL      optional backend webhook URL
    MOCK_PAYMENTS               set to "true" to use mock mode
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import requests
    from requests.exceptions import HTTPError, RequestException
except ImportError:
    requests = None  # type: ignore
    HTTPError = Exception  # type: ignore
    RequestException = Exception  # type: ignore


PAYCHANGU_API_BASE_DEFAULT = "https://api.paychangu.com"


# ──────────────────────────────────────────────────────────────────────────────
# Configuration helpers
# ──────────────────────────────────────────────────────────────────────────────


def is_configured() -> bool:
    """Return True when all required PayChangu credentials are present."""
    return bool(
        getattr(settings, "PAYCHANGU_PUBLIC_KEY", "")
        and getattr(settings, "PAYCHANGU_SECRET_KEY", "")
    )


def is_mock_mode() -> bool:
    """Return True when MOCK_PAYMENTS=true or credentials are missing."""
    mock_flag = str(getattr(settings, "MOCK_PAYMENTS", "true")).lower()
    if mock_flag == "true":
        return True
    return not is_configured()


def _api_base() -> str:
    return getattr(settings, "PAYCHANGU_API_BASE", PAYCHANGU_API_BASE_DEFAULT).rstrip("/")


def _secret_key() -> str:
    return getattr(settings, "PAYCHANGU_SECRET_KEY", "")


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_secret_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Phone normalisation (Malawi)
# ──────────────────────────────────────────────────────────────────────────────


def normalize_phone(phone: str) -> str:
    """
    Normalise a Malawi phone number to 9 digits (no leading 0, no +265).
    Raises ValueError for invalid formats.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("265"):
        digits = digits[3:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9:
        raise ValueError(f"Phone must be 9 digits after normalisation, got {len(digits)}: {phone!r}")
    return digits


# ──────────────────────────────────────────────────────────────────────────────
# Checkout / standard payment
# ──────────────────────────────────────────────────────────────────────────────


def initiate_payment(
    *,
    amount: Decimal,
    currency: str = "MWK",
    tx_ref: Optional[str] = None,
    return_url: str,
    callback_url: Optional[str] = None,
    customer_name: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    description: str = "TengaSale Payment",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a PayChangu checkout session.

    Returns dict:
        status        : 'success' | 'error'
        checkout_url  : redirect URL for user (on success)
        tx_ref        : transaction reference
        message       : human-readable result
        raw_response  : full API response
    """
    tx_ref = tx_ref or f"ts-{uuid.uuid4().hex}"

    if is_mock_mode():
        logger.warning("PayChangu MOCK MODE: returning fake checkout URL for tx_ref=%s", tx_ref)
        return {
            "status": "success",
            "checkout_url": f"/pay/mock-payment/?tx_ref={tx_ref}",
            "tx_ref": tx_ref,
            "message": "Mock payment initiated (MOCK_PAYMENTS=true).",
            "raw_response": {},
        }

    if not requests:
        return {"status": "error", "message": "requests library not installed.", "tx_ref": tx_ref}

    payload: Dict[str, Any] = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": currency,
        "return_url": return_url,
        "description": description,
        "customization": {"title": "TengaSale", "description": description},
    }
    if callback_url:
        payload["callback_url"] = callback_url
    if customer_email:
        payload.setdefault("customer", {})["email"] = customer_email
    if customer_phone:
        payload.setdefault("customer", {})["phone"] = customer_phone
    if customer_name:
        payload.setdefault("customer", {})["name"] = customer_name
    if meta:
        payload["meta"] = meta

    try:
        response = requests.post(f"{_api_base()}/payment", json=payload, headers=_headers(), timeout=20)
        response.raise_for_status()
        data = response.json()
        checkout_url = data.get("data", {}).get("checkout_url") or data.get("checkout_url", "")
        if not checkout_url:
            logger.error("PayChangu checkout response missing checkout_url: %s", data)
            return {"status": "error", "message": "PayChangu returned no checkout URL.", "tx_ref": tx_ref, "raw_response": data}
        logger.info("PayChangu checkout created: tx_ref=%s", tx_ref)
        return {"status": "success", "checkout_url": checkout_url, "tx_ref": tx_ref, "message": "OK", "raw_response": data}
    except HTTPError as exc:
        _log_http_error("initiate_payment", exc)
        return {"status": "error", "message": _friendly_error(exc), "tx_ref": tx_ref, "raw_response": {}}
    except Exception as exc:
        logger.error("PayChangu initiate_payment unexpected error: %s", exc)
        return {"status": "error", "message": str(exc), "tx_ref": tx_ref, "raw_response": {}}


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────


def verify_transaction(tx_ref: str) -> Dict[str, Any]:
    """
    Verify a payment with PayChangu.

    Returns dict:
        status  : 'SUCCESS' | 'PENDING' | 'FAILED' | 'ERROR'
        amount  : decimal amount
        currency
        tx_ref
        message
        raw_response
    """
    if is_mock_mode():
        return {"status": "SUCCESS", "amount": 0, "currency": "MWK", "tx_ref": tx_ref, "message": "Mock verified.", "raw_response": {}}

    if not requests:
        return {"status": "ERROR", "message": "requests library not installed.", "tx_ref": tx_ref}

    try:
        response = requests.get(f"{_api_base()}/verify/{tx_ref}", headers=_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        result = data.get("data", {})
        raw_status = result.get("status", "").upper()
        status = _map_status(raw_status)
        logger.info("PayChangu verify tx_ref=%s status=%s", tx_ref, status)
        return {
            "status": status,
            "amount": result.get("amount", 0),
            "currency": result.get("currency", "MWK"),
            "tx_ref": result.get("tx_ref", tx_ref),
            "message": result.get("message", ""),
            "raw_response": data,
        }
    except Exception as exc:
        logger.error("PayChangu verify_transaction error for %s: %s", tx_ref, exc)
        return {"status": "ERROR", "message": str(exc), "tx_ref": tx_ref, "raw_response": {}}


# ──────────────────────────────────────────────────────────────────────────────
# Mobile-money direct charge
# ──────────────────────────────────────────────────────────────────────────────


def momo_initialize(
    *,
    operator_ref_id: str,
    mobile: str,
    amount: Decimal,
    currency: str = "MWK",
    tx_ref: Optional[str] = None,
    charge_id: Optional[str] = None,
    callback_url: Optional[str] = None,
    description: str = "TengaSale Payment",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Push a mobile-money payment prompt to a customer's phone."""
    tx_ref = tx_ref or f"ts-{uuid.uuid4().hex}"
    charge_id = charge_id or f"ch-{uuid.uuid4().hex}"

    if is_mock_mode():
        return {"status": "success", "charge_id": charge_id, "tx_ref": tx_ref, "message": "Mock MoMo initialized.", "raw_response": {}}

    if not requests:
        return {"status": "error", "message": "requests library not installed."}

    try:
        mobile_digits = normalize_phone(mobile)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    try:
        amount_int = int(Decimal(amount).quantize(Decimal("1")))
    except Exception as exc:
        return {"status": "error", "message": f"Invalid amount: {exc}"}

    payload: Dict[str, Any] = {
        "tx_ref": tx_ref,
        "charge_id": charge_id,
        "amount": amount_int,
        "currency": currency,
        "mobile": mobile_digits,
        "mobile_money_operator_ref_id": operator_ref_id,
        "description": description,
    }
    if callback_url:
        payload["callback_url"] = callback_url
    if meta:
        payload["meta"] = meta

    try:
        response = requests.post(f"{_api_base()}/mobile-money/payments/initialize", json=payload, headers=_headers(), timeout=20)
        response.raise_for_status()
        data = response.json()
        logger.info("PayChangu MoMo initialized: tx_ref=%s charge_id=%s", tx_ref, charge_id)
        return {"status": "success", "charge_id": charge_id, "tx_ref": tx_ref, "message": "OK", "raw_response": data}
    except HTTPError as exc:
        _log_http_error("momo_initialize", exc)
        return {"status": "error", "message": _friendly_error(exc), "raw_response": {}}
    except Exception as exc:
        logger.error("PayChangu momo_initialize unexpected error: %s", exc)
        return {"status": "error", "message": str(exc)}


def momo_verify(charge_id: str) -> Dict[str, Any]:
    """Verify a mobile-money payment by charge_id."""
    if is_mock_mode():
        return {"status": "SUCCESS", "charge_id": charge_id, "message": "Mock MoMo verified.", "raw_response": {}}

    if not requests:
        return {"status": "ERROR", "message": "requests library not installed."}

    try:
        response = requests.get(f"{_api_base()}/mobile-money/payments/{charge_id}/verify", headers=_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        result = data.get("data", {})
        status = _map_status(result.get("status", "").upper())
        logger.info("PayChangu MoMo verify charge_id=%s status=%s", charge_id, status)
        return {"status": status, "charge_id": charge_id, "amount": result.get("amount", 0), "message": "", "raw_response": data}
    except Exception as exc:
        logger.error("PayChangu momo_verify error for %s: %s", charge_id, exc)
        return {"status": "ERROR", "message": str(exc), "raw_response": {}}


# ──────────────────────────────────────────────────────────────────────────────
# Webhook
# ──────────────────────────────────────────────────────────────────────────────


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify a PayChangu webhook signature using HMAC-SHA256.
    Returns True if valid, False otherwise.
    """
    signature = signature.strip()
    if not signature:
        logger.warning("PayChangu webhook: missing signature header")
        return False

    secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "").strip().strip('"').strip("'")
    if not secret:
        logger.error("PayChangu webhook: PAYCHANGU_WEBHOOK_SECRET not configured — treating as invalid")
        return False

    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(expected, signature)
    if not valid:
        logger.warning("PayChangu webhook: signature mismatch")
    return valid


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _map_status(raw: str) -> str:
    if raw in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
        return "SUCCESS"
    if raw in ("PENDING", "PROCESSING"):
        return "PENDING"
    if raw in ("FAILED", "CANCELLED", "CANCELED"):
        return "FAILED"
    return "PENDING"


def _log_http_error(context: str, exc: Any) -> None:
    code = getattr(getattr(exc, "response", None), "status_code", "?")
    try:
        detail = exc.response.json()
    except Exception:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
    logger.error("PayChangu %s HTTP %s: %s", context, code, detail)


def _friendly_error(exc: Any) -> str:
    code = getattr(getattr(exc, "response", None), "status_code", "?")
    try:
        msg = exc.response.json().get("message", str(exc))
    except Exception:
        msg = str(exc)
    if code == 401:
        return "Payment provider authentication failed. Contact support."
    if code == 400:
        return f"Invalid payment request: {msg}"
    if isinstance(code, int) and code >= 500:
        return "Payment provider temporarily unavailable. Please try again."
    return f"Payment error ({code}): {msg}"
