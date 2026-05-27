"""
WhatsApp Cloud API helper using Meta's Cloud API.

This module provides a simple interface to send WhatsApp text messages
using environment variables for configuration (no hardcoded tokens).

Environment Variables:
    WHATSAPP_TOKEN: Cloud API access token
    WHATSAPP_PHONE_NUMBER_ID: Phone number ID (e.g. 812090425331217)
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")


class WhatsAppError(Exception):
    """Raised when the WhatsApp Cloud API call fails."""

    pass


def send_whatsapp_text(to_number: str, body: str) -> dict:
    """
    Send a simple WhatsApp text message using Meta's Cloud API.

    :param to_number: WhatsApp number in international format, digits only
                      e.g. '265883596135'
    :param body: message body text
    :return: JSON response from the WhatsApp API
    :raises WhatsAppError: if env vars are not configured or API call fails
    """
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppError("WhatsApp env vars not configured")

    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": body},
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code >= 400:
        logger.error("WhatsApp API error %s: %s", resp.status_code, resp.text)
        raise WhatsAppError(f"WhatsApp API error {resp.status_code}: {resp.text}")
    return resp.json()
