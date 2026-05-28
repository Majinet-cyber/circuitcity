"""
integrations/payout_provider.py

Merchant and underwriter payout provider abstraction for TengaSale.
Supports bank transfers and Airtel Money via PayChangu disbursements.

Mock mode is active by default until live credentials are configured.

Configuration:
    PAYCHANGU_SECRET_KEY  (reuses payment keys for payout API)
    MOCK_PAYOUTS=true/false
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def is_mock_mode() -> bool:
    mock_flag = str(getattr(settings, "MOCK_PAYOUTS", "true")).lower()
    if mock_flag == "true":
        return True
    return not bool(getattr(settings, "PAYCHANGU_SECRET_KEY", ""))


def initiate_merchant_payout(merchant_payout) -> Dict[str, Any]:
    """
    Initiate a cash settlement payout to the merchant via PayChangu or bank.

    Updates the MerchantContractPayout record status to 'processing' on success.

    Returns:
        status:              'success' | 'error' | 'mock'
        provider_reference:  Provider transaction ID
        message:             Human-readable result
    """
    ref = f"mpo-{uuid.uuid4().hex[:12]}"

    if is_mock_mode():
        logger.info(
            "MOCK payout: merchant_payout id=%s amount=%s",
            merchant_payout.pk, merchant_payout.total_payable,
        )
        _update_payout(merchant_payout, "processing", ref)
        return {"status": "mock", "provider_reference": ref,
                "message": f"Mock payout initiated (MOCK_PAYOUTS=true). Ref: {ref}"}

    try:
        import requests  # type: ignore
    except ImportError:
        return {"status": "error", "message": "requests not installed."}

    secret_key = getattr(settings, "PAYCHANGU_SECRET_KEY", "")
    base_url = getattr(settings, "PAYCHANGU_API_BASE", "https://api.paychangu.com").rstrip("/")

    payload: Dict[str, Any] = {
        "tx_ref": ref,
        "amount": str(Decimal(merchant_payout.total_payable).quantize(Decimal("1"))),
        "currency": "MWK",
        "description": f"TengaSale merchant settlement — contract {getattr(merchant_payout, 'contract_id', '')}",
    }
    phone = getattr(merchant_payout, "destination_phone", "")
    account = getattr(merchant_payout, "destination_account", "")
    method = getattr(merchant_payout, "payout_method", "manual")

    if method == "airtel_money" and phone:
        payload["mobile"] = phone
        payload["method"] = "airtel_money"
    elif method == "bank" and account:
        payload["bank_account"] = account
        payload["method"] = "bank"
    else:
        _update_payout(merchant_payout, "processing", ref)
        return {"status": "mock", "provider_reference": ref,
                "message": "No payout method configured — marked as processing for manual disbursement."}

    try:
        response = requests.post(
            f"{base_url}/disbursement",
            json=payload,
            headers={"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        provider_ref = data.get("data", {}).get("tx_ref") or data.get("tx_ref") or ref
        _update_payout(merchant_payout, "processing", provider_ref)
        logger.info("Merchant payout initiated: ref=%s id=%s", provider_ref, merchant_payout.pk)
        return {"status": "success", "provider_reference": provider_ref, "message": "Payout initiated."}
    except Exception as exc:
        logger.error("initiate_merchant_payout error: %s", exc)
        return {"status": "error", "message": str(exc)}


def verify_payout(provider_reference: str) -> Dict[str, Any]:
    """
    Verify the status of an initiated payout by provider reference.

    Returns:
        status:   'SUCCESS' | 'PENDING' | 'FAILED' | 'ERROR' | 'MOCK'
        message:  Human-readable
    """
    if is_mock_mode():
        return {"status": "MOCK", "message": "Mock payout verified."}

    try:
        import requests  # type: ignore
    except ImportError:
        return {"status": "ERROR", "message": "requests not installed."}

    secret_key = getattr(settings, "PAYCHANGU_SECRET_KEY", "")
    base_url = getattr(settings, "PAYCHANGU_API_BASE", "https://api.paychangu.com").rstrip("/")

    try:
        response = requests.get(
            f"{base_url}/disbursement/{provider_reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        raw_status = (data.get("data", {}).get("status") or data.get("status") or "").upper()
        if raw_status in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
            return {"status": "SUCCESS", "message": "Payout confirmed.", "raw_response": data}
        if raw_status in ("PENDING", "PROCESSING"):
            return {"status": "PENDING", "message": "Payout still processing.", "raw_response": data}
        return {"status": "FAILED", "message": f"Payout status: {raw_status}", "raw_response": data}
    except Exception as exc:
        logger.error("verify_payout error for %s: %s", provider_reference, exc)
        return {"status": "ERROR", "message": str(exc)}


def handle_payout_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process an incoming payout webhook from PayChangu.
    Idempotent — repeated calls for the same reference are safe.

    Returns:
        processed: bool
        message:   str
    """
    tx_ref = payload.get("tx_ref") or payload.get("data", {}).get("tx_ref", "")
    status = (payload.get("status") or payload.get("data", {}).get("status") or "").upper()

    if not tx_ref:
        return {"processed": False, "message": "No tx_ref in webhook payload."}

    try:
        from commissions.models import MerchantContractPayout
        payout = MerchantContractPayout.objects.filter(provider_reference=tx_ref).first()
        if payout is None:
            logger.warning("Payout webhook: no MerchantContractPayout for ref=%s", tx_ref)
            return {"processed": False, "message": f"No payout record for ref {tx_ref}."}

        if payout.status == "paid":
            return {"processed": True, "message": "Already marked paid — idempotent skip."}

        if status in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
            from django.utils import timezone
            payout.status = "paid"
            payout.paid_at = timezone.now()
            payout.save(update_fields=["status", "paid_at"])
            logger.info("Payout webhook: marked paid ref=%s payout=%s", tx_ref, payout.pk)
            return {"processed": True, "message": "Payout marked as paid."}

        if status in ("FAILED", "CANCELLED"):
            payout.status = "failed"
            payout.save(update_fields=["status"])
            return {"processed": True, "message": "Payout marked as failed."}

        return {"processed": False, "message": f"Unhandled payout webhook status: {status}"}
    except Exception as exc:
        logger.error("handle_payout_webhook error: %s", exc)
        return {"processed": False, "message": str(exc)}


def _update_payout(merchant_payout, status: str, provider_reference: str) -> None:
    try:
        merchant_payout.status = status
        merchant_payout.provider_reference = provider_reference
        merchant_payout.save(update_fields=["status", "provider_reference"])
    except Exception as exc:
        logger.warning("Could not update MerchantContractPayout: %s", exc)
