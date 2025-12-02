# notifications/whatsapp_service.py
"""
WhatsApp Cloud API integration for real-time business notifications.
Sends alerts to managers and agents about sales, profits, stock, and commissions.
"""
from __future__ import annotations

import logging
from typing import Optional
from decimal import Decimal

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore


def is_whatsapp_configured() -> bool:
    """Check if WhatsApp API is configured."""
    return bool(
        getattr(settings, "WHATSAPP_API_BASE_URL", "")
        and getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
        and getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    )


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to international format.
    
    If the number doesn't start with +, prepend the default country code.
    
    Args:
        phone: Phone number (e.g. "0888123456" or "+265888123456")
    
    Returns:
        Normalized phone number in international format
    """
    phone = phone.strip()
    
    # Remove common prefixes
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # If already has +, return as is
    if phone.startswith("+"):
        return phone
    
    # Remove leading 0 (common in local numbers)
    if phone.startswith("0"):
        phone = phone[1:]
    
    # Prepend country code
    country_code = getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "+265")
    return f"{country_code}{phone}"


def send_whatsapp_message(phone_number: str, body: str) -> bool:
    """
    Send a WhatsApp message using the Cloud API.
    
    Args:
        phone_number: Recipient phone number (will be normalized)
        body: Message text
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not requests:
        logger.warning("requests module not installed; cannot send WhatsApp message")
        return False
    
    if not is_whatsapp_configured():
        logger.debug("WhatsApp not configured; skipping message send")
        return False
    
    if not phone_number or not body:
        logger.warning("Missing phone_number or body for WhatsApp message")
        return False
    
    # Normalize phone
    phone = normalize_phone_number(phone_number)
    
    # Build API request
    base_url = settings.WHATSAPP_API_BASE_URL.rstrip("/")
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    
    url = f"{base_url}/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body,
        },
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        logger.info(f"WhatsApp message sent to {phone[:8]}...")
        return True
    
    except requests.exceptions.RequestException as e:
        logger.error(f"WhatsApp API error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp: {e}")
        return False


# ==============================================================================
# High-level notification helpers
# ==============================================================================

def _get_user_preference(user):
    """Get WhatsApp preference for user (cached in memory if possible)."""
    from .models import WhatsAppPreference
    
    try:
        return WhatsAppPreference.objects.get(user=user, is_enabled=True)
    except WhatsAppPreference.DoesNotExist:
        return None


def _build_dashboard_url(business) -> str:
    """Build dashboard URL (try to make it absolute if possible)."""
    try:
        from django.contrib.sites.models import Site
        domain = Site.objects.get_current().domain
        path = reverse("dashboard:index")
        return f"https://{domain}{path}"
    except Exception:
        return "https://emajinet.africa/dashboard/"


def notify_manager_sale(manager_user, business, sale_info: dict) -> bool:
    """
    Notify manager about a sale.
    
    Args:
        manager_user: User instance (manager)
        business: Business instance
        sale_info: Dict with keys: product_name, quantity, amount, location_name
    
    Returns:
        True if sent, False otherwise
    """
    pref = _get_user_preference(manager_user)
    if not pref or not pref.receive_sale_alerts:
        return False
    
    product_name = sale_info.get("product_name", "Item")
    quantity = sale_info.get("quantity", 1)
    amount = sale_info.get("amount", 0)
    location_name = sale_info.get("location_name", "your store")
    
    dashboard_url = _build_dashboard_url(business)
    
    body = (
        f"🛒 Sale Alert!\n\n"
        f"{quantity}x {product_name} sold at {location_name}\n"
        f"Amount: MWK {amount:,.0f}\n\n"
        f"View dashboard: {dashboard_url}"
    )
    
    return send_whatsapp_message(pref.phone_number, body)


def notify_manager_profit_milestone(manager_user, business, milestone_amount: Decimal) -> bool:
    """
    Notify manager when a profit milestone is reached.
    
    Args:
        manager_user: User instance (manager)
        business: Business instance
        milestone_amount: Milestone amount reached
    
    Returns:
        True if sent, False otherwise
    """
    pref = _get_user_preference(manager_user)
    if not pref or not pref.receive_profit_milestones:
        return False
    
    dashboard_url = _build_dashboard_url(business)
    
    body = (
        f"🎉 Milestone Reached!\n\n"
        f"Profit has reached MWK {milestone_amount:,.0f}!\n"
        f"Great work, keep it up!\n\n"
        f"View details: {dashboard_url}"
    )
    
    return send_whatsapp_message(pref.phone_number, body)


def notify_manager_low_stock(manager_user, business, product_name: str, current_qty: int, reorder_level: int = 10) -> bool:
    """
    Notify manager about low stock.
    
    Args:
        manager_user: User instance (manager)
        business: Business instance
        product_name: Product name
        current_qty: Current quantity in stock
        reorder_level: Reorder threshold
    
    Returns:
        True if sent, False otherwise
    """
    pref = _get_user_preference(manager_user)
    if not pref or not pref.receive_low_stock_alerts:
        return False
    
    dashboard_url = _build_dashboard_url(business)
    
    body = (
        f"⚠️ Low Stock Alert!\n\n"
        f"{product_name} is running low\n"
        f"Current stock: {current_qty}\n"
        f"Reorder level: {reorder_level}\n\n"
        f"Restock soon: {dashboard_url}"
    )
    
    return send_whatsapp_message(pref.phone_number, body)


def notify_agent_commission(agent_user, business, sale_info: dict, commission_amount: Decimal) -> bool:
    """
    Notify agent about commission earned.
    
    Args:
        agent_user: User instance (agent)
        business: Business instance
        sale_info: Dict with sale details
        commission_amount: Commission earned
    
    Returns:
        True if sent, False otherwise
    """
    pref = _get_user_preference(agent_user)
    if not pref or not pref.receive_commission_alerts:
        return False
    
    product_name = sale_info.get("product_name", "Item")
    quantity = sale_info.get("quantity", 1)
    
    dashboard_url = _build_dashboard_url(business)
    
    body = (
        f"💰 Commission Earned!\n\n"
        f"Great job! You just earned MWK {commission_amount:,.0f}\n"
        f"Sale: {quantity}x {product_name}\n\n"
        f"Keep up the great work!\n"
        f"View details: {dashboard_url}"
    )
    
    return send_whatsapp_message(pref.phone_number, body)


def notify_near_expiry(manager_user, business, product_name: str, batch_number: str, expiry_date: str, days_left: int) -> bool:
    """
    Notify manager about near-expiry products (pharmacy).
    
    Args:
        manager_user: User instance (manager)
        business: Business instance
        product_name: Product name
        batch_number: Batch number
        expiry_date: Expiry date string
        days_left: Days until expiry
    
    Returns:
        True if sent, False otherwise
    """
    pref = _get_user_preference(manager_user)
    if not pref or not pref.receive_low_stock_alerts:  # Reuse low_stock flag for expiry
        return False
    
    dashboard_url = _build_dashboard_url(business)
    
    body = (
        f"⚠️ Expiry Alert!\n\n"
        f"{product_name} (Batch {batch_number})\n"
        f"Expires in {days_left} days ({expiry_date})\n\n"
        f"Take action: {dashboard_url}"
    )
    
    return send_whatsapp_message(pref.phone_number, body)

