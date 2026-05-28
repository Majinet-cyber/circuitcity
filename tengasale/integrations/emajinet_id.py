"""
integrations/emajinet_id.py

Emajinet ID integration abstraction for TengaSale.
Provides identity verification and customer profile lookup.

Mock mode is active by default until live credentials are configured.

Configuration:
    EMAJINET_API_KEY
    EMAJINET_API_BASE
    MOCK_EMAJINET=true/false
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(
        getattr(settings, "EMAJINET_API_KEY", "")
        and getattr(settings, "EMAJINET_API_BASE", "")
    )


def is_mock_mode() -> bool:
    mock_flag = str(getattr(settings, "MOCK_EMAJINET", "true")).lower()
    if mock_flag == "true":
        return True
    return not is_configured()


def verify_identity(
    national_id: str,
    phone: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify a customer's identity against the Emajinet ID provider.

    Returns:
        status:            'verified' | 'failed' | 'not_found' | 'error' | 'mock'
        match_score:       0-100 confidence
        verified_name:     Name as returned by provider
        national_id:       Echo of input
        message:           Human-readable result
        raw_response:      Full provider response (may be empty dict)
    """
    if is_mock_mode():
        logger.info("Emajinet ID MOCK: verify_identity national_id=%s", national_id[:4] + "****")
        return {
            "status": "mock",
            "match_score": 85,
            "verified_name": name or "Mock Customer",
            "national_id": national_id,
            "message": "Mock mode — Emajinet ID not connected. Configure EMAJINET_API_KEY to go live.",
            "raw_response": {},
        }

    try:
        import requests  # type: ignore
    except ImportError:
        return {"status": "error", "message": "requests not installed.", "raw_response": {}}

    api_key = getattr(settings, "EMAJINET_API_KEY", "")
    base_url = getattr(settings, "EMAJINET_API_BASE", "").rstrip("/")

    try:
        payload: Dict[str, Any] = {"national_id": national_id}
        if phone:
            payload["phone"] = phone
        if name:
            payload["name"] = name
        response = requests.post(
            f"{base_url}/verify",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status", "unknown")
        return {
            "status": status,
            "match_score": data.get("match_score", 0),
            "verified_name": data.get("name", ""),
            "national_id": national_id,
            "message": data.get("message", ""),
            "raw_response": data,
        }
    except Exception as exc:
        logger.error("Emajinet ID verify_identity error: %s", exc)
        return {"status": "error", "message": str(exc), "raw_response": {}}


def get_customer_profile(national_id: str) -> Dict[str, Any]:
    """
    Retrieve a customer's full profile from Emajinet.

    Returns:
        status:    'found' | 'not_found' | 'error' | 'mock'
        profile:   Dict with customer data
        message:   Human-readable
    """
    if is_mock_mode():
        logger.info("Emajinet ID MOCK: get_customer_profile")
        return {
            "status": "mock",
            "profile": {"national_id": national_id, "name": "Mock Customer", "verified": False},
            "message": "Mock mode.",
        }

    try:
        import requests  # type: ignore
    except ImportError:
        return {"status": "error", "message": "requests not installed.", "profile": {}}

    api_key = getattr(settings, "EMAJINET_API_KEY", "")
    base_url = getattr(settings, "EMAJINET_API_BASE", "").rstrip("/")

    try:
        response = requests.get(
            f"{base_url}/customer/{national_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if response.status_code == 404:
            return {"status": "not_found", "profile": {}, "message": "Customer not found."}
        response.raise_for_status()
        data = response.json()
        return {"status": "found", "profile": data, "message": "OK"}
    except Exception as exc:
        logger.error("Emajinet ID get_customer_profile error: %s", exc)
        return {"status": "error", "message": str(exc), "profile": {}}


def link_emajinet_id(customer_or_application) -> Dict[str, Any]:
    """
    Attempt to link an Emajinet ID to a customer application.
    Creates/updates the CustomerIdentityProfile if found.

    Returns dict with status and emajinet_id.
    """
    national_id = getattr(customer_or_application, "national_id", "") or ""
    if not national_id:
        return {"status": "error", "message": "No national_id on record."}

    result = verify_identity(national_id)
    if result["status"] in ("verified", "mock"):
        try:
            from risk.models import CustomerIdentityProfile
            profile, _ = CustomerIdentityProfile.objects.get_or_create(
                application=customer_or_application
            )
            if result["status"] == "verified":
                profile.emajinet_id = result.get("raw_response", {}).get("emajinet_id", "")
                profile.verification_status = CustomerIdentityProfile.VERIFICATION_VERIFIED
            else:
                profile.verification_status = CustomerIdentityProfile.VERIFICATION_PENDING
            profile.set_national_id_hash(national_id)
            if hasattr(customer_or_application, "customer_phone"):
                profile.set_phone_hash(customer_or_application.customer_phone or "")
            profile.save()
        except Exception as exc:
            logger.warning("Could not update CustomerIdentityProfile: %s", exc)

    return result
