"""
PHASE 3: Session Metadata Management
Captures and stores device information for active sessions.
"""
from __future__ import annotations

from typing import Optional
from django.contrib.sessions.models import Session
from django.utils import timezone
from user_agents import parse


def capture_session_metadata(request) -> None:
    """
    Capture user agent and IP on login/request.
    Stores metadata in session data for display in settings.
    """
    if not hasattr(request, "session") or not request.session.session_key:
        return

    user_agent_string = request.META.get("HTTP_USER_AGENT", "")
    ip_address = _get_client_ip(request)

    # Parse user agent
    ua = parse(user_agent_string)
    device_info = _format_device_info(ua)

    # Store in session
    request.session["user_agent"] = user_agent_string
    request.session["device_info"] = device_info
    request.session["ip_address"] = ip_address
    request.session["login_time"] = timezone.now().isoformat()
    request.session.modified = True


def _get_client_ip(request) -> str:
    """Get client IP address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "Unknown")
    return ip


def _format_device_info(ua) -> str:
    """
    Format user agent into human-readable device string.
    Examples:
    - "Chrome 123 on Windows 10 (Desktop)"
    - "Safari iOS (iPhone)"
    - "Firefox 120 on macOS (Desktop)"
    """
    browser = ua.browser.family
    browser_version = ua.browser.version_string.split(".")[0] if ua.browser.version_string else ""

    os_name = ua.os.family
    os_version = ua.os.version_string.split(".")[0] if ua.os.version_string else ""

    device_type = "Desktop"
    if ua.is_mobile:
        device_type = "Mobile"
    elif ua.is_tablet:
        device_type = "Tablet"
    elif ua.is_bot:
        device_type = "Bot"

    # Build string
    parts = []
    if browser:
        if browser_version:
            parts.append(f"{browser} {browser_version}")
        else:
            parts.append(browser)

    if os_name:
        if os_version and os_version != "0":
            parts.append(f"on {os_name} {os_version}")
        else:
            parts.append(f"on {os_name}")

    if device_type:
        parts.append(f"({device_type})")

    return " ".join(parts) if parts else "Unknown Device"


def get_session_device_info(session: Session) -> dict:
    """
    Extract device info from a session object.
    Returns dict with device_info, ip_address, login_time, last_activity.
    """
    try:
        data = session.get_decoded()
    except Exception:
        data = {}

    return {
        "device_info": data.get("device_info", "Unknown Device"),
        "ip_address": data.get("ip_address", "Unknown"),
        "login_time": data.get("login_time"),
        "last_activity": session.expire_date,
    }
