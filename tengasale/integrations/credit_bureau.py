"""
integrations/credit_bureau.py

External credit bureau integration abstraction for TengaSale.
Supports querying credit risk scores, adverse history, and exposure data.

Mock mode by default until live credentials are configured.

Configuration:
    CREDIT_BUREAU_API_KEY
    CREDIT_BUREAU_API_BASE
    MOCK_CREDIT_BUREAU=true/false
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(
        getattr(settings, "CREDIT_BUREAU_API_KEY", "")
        and getattr(settings, "CREDIT_BUREAU_API_BASE", "")
    )


def is_mock_mode() -> bool:
    mock_flag = str(getattr(settings, "MOCK_CREDIT_BUREAU", "true")).lower()
    if mock_flag == "true":
        return True
    return not is_configured()


def run_credit_check(application_or_customer) -> Dict[str, Any]:
    """
    Run a credit bureau check for the given application or customer.

    If an ExternalCheck record exists, records the result there.

    Returns:
        status:         'completed' | 'failed' | 'not_found' | 'mock' | 'error'
        risk_score:     0-100
        adverse_count:  number of adverse records found
        summary:        Human-readable summary
        raw_response:   Full provider response
    """
    national_id = getattr(application_or_customer, "national_id", "") or ""

    if is_mock_mode():
        logger.info("Credit bureau MOCK: run_credit_check")
        result = {
            "status": "mock",
            "risk_score": 60,
            "adverse_count": 0,
            "summary": "Mock credit check — no live bureau connected. Configure CREDIT_BUREAU_API_KEY to go live.",
            "raw_response": {},
        }
        _record_check(application_or_customer, result)
        return result

    try:
        import requests  # type: ignore
    except ImportError:
        return {"status": "error", "message": "requests not installed.", "raw_response": {}}

    api_key = getattr(settings, "CREDIT_BUREAU_API_KEY", "")
    base_url = getattr(settings, "CREDIT_BUREAU_API_BASE", "").rstrip("/")

    try:
        response = requests.post(
            f"{base_url}/check",
            json={"national_id": national_id},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        result = {
            "status": "completed",
            "risk_score": data.get("risk_score", 0),
            "adverse_count": data.get("adverse_count", 0),
            "summary": data.get("summary", ""),
            "raw_response": data,
        }
        _record_check(application_or_customer, result)
        return result
    except Exception as exc:
        logger.error("Credit bureau run_credit_check error: %s", exc)
        return {"status": "error", "message": str(exc), "raw_response": {}}


def get_risk_score(application_or_customer) -> Optional[int]:
    """Return just the numeric risk score (0-100) or None on failure."""
    result = run_credit_check(application_or_customer)
    return result.get("risk_score")


def get_adverse_history(application_or_customer) -> Dict[str, Any]:
    """
    Return adverse credit history for the customer.

    Returns:
        status:    'found' | 'clean' | 'mock' | 'error'
        records:   List of adverse records
        summary:   Human-readable
    """
    if is_mock_mode():
        return {"status": "mock", "records": [], "summary": "Mock: no adverse history (mock mode)."}

    result = run_credit_check(application_or_customer)
    adverse_count = result.get("adverse_count", 0)
    return {
        "status": "found" if adverse_count > 0 else "clean",
        "records": result.get("raw_response", {}).get("adverse_records", []),
        "summary": result.get("summary", ""),
    }


def _record_check(application_or_customer, result: Dict) -> None:
    """Record the check result in ExternalCheck if possible."""
    try:
        from risk.models import ExternalCheck
        ExternalCheck.objects.create(
            application=application_or_customer,
            provider=ExternalCheck.PROVIDER_CREDIT_BUREAU,
            status=ExternalCheck.STATUS_COMPLETED if result.get("status") == "completed" else ExternalCheck.STATUS_SKIPPED,
            response_summary=result.get("summary", "")[:500],
        )
    except Exception:
        pass
