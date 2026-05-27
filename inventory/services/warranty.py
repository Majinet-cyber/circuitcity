# inventory/services/warranty.py
"""
Carlcare warranty check integration for Tecno & Itel phones.
Checks warranty status via Carlcare website: https://www.carlcare.com/mw/
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Dict, Optional, Tuple
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Carlcare URL for Malawi
CARLCARE_WARRANTY_URL = "https://www.carlcare.com/mw/support/imei-check/"

# User agent to avoid being blocked
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = getattr(settings, "CARLCARE_TIMEOUT", 10)


def is_carlcare_brand(brand: str) -> bool:
    """Check if a phone brand uses Carlcare warranty (Tecno, Itel)."""
    if not brand:
        return False
    brand_lower = brand.lower().strip()
    return brand_lower in {"tecno", "itel", "infinix"}  # Infinix also uses Carlcare


def check_carlcare_warranty(imei: str) -> Dict:
    """
    Check warranty status for an IMEI on Carlcare.

    Args:
        imei: 15-digit IMEI number

    Returns:
        {
            "status": "no_warranty" | "in_warranty" | "expired" | "activated",
            "expiration_date": date|None,
            "message": str,  # human-readable message
            "raw_html": str|None,  # raw HTML response for debugging
            "checked_at": datetime,
        }

    Status meanings:
        - no_warranty: No record found (likely cross-border phone)
        - expired: "Out of warranty" or past expiration date
        - in_warranty: Warranty exists but not yet activated (no expiration date)
        - activated: Warranty active with expiration date
    """
    result = {
        "status": "unknown",
        "expiration_date": None,
        "message": "Warranty check not performed",
        "raw_html": None,
        "checked_at": timezone.now(),
    }

    # Validate IMEI
    imei_clean = re.sub(r"\D", "", imei)
    if len(imei_clean) != 15:
        result["status"] = "unknown"
        result["message"] = f"Invalid IMEI length: {len(imei_clean)} digits (expected 15)"
        return result

    try:
        # Make HTTP request to Carlcare
        # NOTE: This is a placeholder implementation. The actual Carlcare API/form
        # may require different parameters or a POST request.
        # You'll need to inspect the actual Carlcare warranty check page to see
        # what parameters it expects.

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.carlcare.com/mw/",
        }

        # This is a placeholder - actual implementation depends on Carlcare's form structure
        # Option 1: GET request with IMEI in URL
        # Option 2: POST request with form data

        # Example (needs to be adapted based on actual Carlcare implementation):
        response = requests.get(
            CARLCARE_WARRANTY_URL,
            params={"imei": imei_clean},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            verify=True,  # Verify SSL certificate
        )

        response.raise_for_status()
        html = response.text
        result["raw_html"] = html

        # Parse the HTML response
        # This is where you'd extract warranty status from the page
        # The exact parsing logic depends on Carlcare's HTML structure

        html_lower = html.lower()

        # Check for common patterns (these are examples - adjust based on actual HTML)
        if "no record found" in html_lower or "not found" in html_lower:
            result["status"] = "no_warranty"
            result["message"] = "No warranty record found (likely cross-border phone)"

        elif "out of warranty" in html_lower or "warranty expired" in html_lower:
            result["status"] = "expired"
            result["message"] = "Warranty has expired"

        elif "under warranty" in html_lower or "valid warranty" in html_lower:
            # Try to extract expiration date
            # Pattern: look for dates like "2025-12-31", "31/12/2025", etc.
            date_patterns = [
                r"(\d{4})-(\d{2})-(\d{2})",  # YYYY-MM-DD
                r"(\d{2})/(\d{2})/(\d{4})",  # DD/MM/YYYY
                r"(\d{2})-(\d{2})-(\d{4})",  # DD-MM-YYYY
            ]

            expiration_found = None
            for pattern in date_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    try:
                        # Try to parse the date
                        match = matches[0]
                        if len(match[0]) == 4:  # YYYY-MM-DD
                            expiration_found = date(int(match[0]), int(match[1]), int(match[2]))
                        else:  # DD/MM/YYYY or DD-MM-YYYY
                            expiration_found = date(int(match[2]), int(match[1]), int(match[0]))
                        break
                    except (ValueError, IndexError):
                        continue

            if expiration_found:
                result["status"] = "activated"
                result["expiration_date"] = expiration_found
                result["message"] = f"Warranty active until {expiration_found.isoformat()}"
            else:
                result["status"] = "in_warranty"
                result["message"] = "Warranty exists but not yet activated"

        else:
            result["status"] = "unknown"
            result["message"] = "Could not parse warranty status from response"
            logger.warning(f"Unknown warranty response format for IMEI {imei_clean[:5]}***")

    except requests.Timeout:
        result["status"] = "unknown"
        result["message"] = "Warranty check timed out"
        logger.error(f"Carlcare warranty check timeout for IMEI {imei_clean[:5]}***")

    except requests.RequestException as e:
        result["status"] = "unknown"
        result["message"] = f"Network error: {str(e)}"
        logger.error(f"Carlcare warranty check failed for IMEI {imei_clean[:5]}***: {e}")

    except Exception as e:
        result["status"] = "unknown"
        result["message"] = f"Unexpected error: {str(e)}"
        logger.exception(f"Unexpected error checking warranty for IMEI {imei_clean[:5]}***")

    return result


def update_stock_warranty(stock_item, check_result: Dict) -> None:
    """
    Update an InventoryItem with warranty check results.

    Args:
        stock_item: InventoryItem instance
        check_result: Result dict from check_carlcare_warranty()
    """
    from inventory.models import InventoryItem
    from notifications.models import Notification

    stock_item.warranty_status = check_result["status"]
    stock_item.warranty_expiration = check_result.get("expiration_date")
    stock_item.warranty_checked_at = check_result["checked_at"]
    stock_item.warranty_raw = {
        "message": check_result["message"],
        "html_snippet": (check_result.get("raw_html") or "")[:500],  # Store first 500 chars
    }
    stock_item.save(
        update_fields=[
            "warranty_status",
            "warranty_expiration",
            "warranty_checked_at",
            "warranty_raw",
        ]
    )

    # Create manager alert if warranty is already activated
    if check_result["status"] == "activated":
        try:
            # Get business managers
            business = getattr(stock_item, "business", None)
            if business:
                from tenants.models import Membership

                manager_memberships = Membership.objects.filter(business=business, role="MANAGER", status="ACTIVE")

                for membership in manager_memberships:
                    Notification.objects.create(
                        user=membership.user,
                        title="⚠️ Activated Warranty Detected",
                        message=f"Phone IMEI {stock_item.imei} has active warranty (already activated). "
                        f"Expiration: {check_result['expiration_date']}. "
                        f"Confirm if this phone is sold or verify its source.",
                        link=f"/inventory/stock/{stock_item.id}/",
                        category="warranty_alert",
                    )
        except Exception as e:
            logger.exception(f"Failed to create warranty alert notification: {e}")


def check_warranty_async(stock_item_id: int) -> None:
    """
    Celery task wrapper for async warranty checking.
    Call this from a Celery task if you have Celery configured.
    """
    from inventory.models import InventoryItem

    try:
        stock = InventoryItem.objects.get(id=stock_item_id)

        # Only check for Tecno/Itel
        brand = getattr(stock.product, "brand", "") if stock.product else ""
        if not is_carlcare_brand(brand):
            logger.info(f"Skipping warranty check for non-Carlcare brand: {brand}")
            return

        if not stock.imei or len(re.sub(r"\D", "", stock.imei)) != 15:
            logger.info(f"Skipping warranty check for invalid IMEI: {stock.imei}")
            return

        result = check_carlcare_warranty(stock.imei)
        update_stock_warranty(stock, result)

    except InventoryItem.DoesNotExist:
        logger.error(f"InventoryItem {stock_item_id} not found for warranty check")
    except Exception as e:
        logger.exception(f"Async warranty check failed for stock {stock_item_id}: {e}")
