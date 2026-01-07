"""
PHASE 3 Tests: Session Metadata (Real Device Identification)
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.contrib.sessions.models import Session
from circuitcity.accounts.session_metadata import (
    capture_session_metadata,
    _format_device_info,
    get_session_device_info,
)
from user_agents import parse

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.mark.django_db
class TestSessionMetadataCapture:
    """Test session metadata is captured on login."""

    def test_capture_session_metadata_stores_device_info(self, user):
        """Session metadata should be stored in session data."""
        factory = RequestFactory()
        request = factory.get("/")
        request.META[
            "HTTP_USER_AGENT"
        ] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        # Create session
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()
        request.session.create()

        # Capture metadata
        capture_session_metadata(request)

        # Check session data
        assert "device_info" in request.session
        assert "ip_address" in request.session
        assert "login_time" in request.session
        assert "Chrome" in request.session["device_info"]
        assert "Windows" in request.session["device_info"]
        assert request.session["ip_address"] == "192.168.1.100"

    def test_login_captures_metadata_automatically(self, user):
        """Logging in should automatically capture session metadata."""
        client = Client()
        client.post(
            "/accounts/login/",
            {
                "username": "testuser",
                "password": "testpass123",
            },
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        )

        # Check session has metadata
        session = client.session
        assert "device_info" in session
        assert "Safari" in session["device_info"] or "Mobile" in session["device_info"]


@pytest.mark.django_db
class TestDeviceInfoFormatting:
    """Test device info formatting from user agent strings."""

    def test_chrome_windows_desktop(self):
        """Chrome on Windows should be formatted correctly."""
        ua_string = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ua = parse(ua_string)
        device_info = _format_device_info(ua)

        assert "Chrome" in device_info
        assert "Windows" in device_info
        assert "Desktop" in device_info

    def test_safari_iphone(self):
        """Safari on iPhone should be formatted correctly."""
        ua_string = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ua = parse(ua_string)
        device_info = _format_device_info(ua)

        assert "Safari" in device_info or "Mobile Safari" in device_info
        assert "iOS" in device_info or "iPhone" in device_info
        assert "Mobile" in device_info

    def test_firefox_macos(self):
        """Firefox on macOS should be formatted correctly."""
        ua_string = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0"
        ua = parse(ua_string)
        device_info = _format_device_info(ua)

        assert "Firefox" in device_info
        assert "Mac OS X" in device_info or "macOS" in device_info
        assert "Desktop" in device_info

    def test_unknown_device_fallback(self):
        """Unknown user agent should return fallback or 'Other'."""
        ua_string = ""
        ua = parse(ua_string)
        device_info = _format_device_info(ua)

        # Library returns "Other" for unknown, which is acceptable
        assert "Other" in device_info or device_info == "Unknown Device"


@pytest.mark.django_db
class TestSessionsPage:
    """Test sessions page displays device info correctly."""

    def test_sessions_page_shows_device_info(self, user):
        """Sessions page should display device information (basic check)."""
        client = Client()
        client.force_login(user)

        response = client.get("/accounts/settings/sessions/")
        assert response.status_code == 200

        # Basic check that page renders without error
        content = response.content.decode()
        assert "Active Sessions" in content or "Sessions" in content

    def test_sessions_page_no_unknown_device(self, user):
        """Sessions page should not show 'Unknown Device' when metadata exists."""
        client = Client()
        client.post(
            "/accounts/login/",
            {
                "username": "testuser",
                "password": "testpass123",
            },
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        response = client.get("/accounts/settings/sessions/")
        assert response.status_code == 200

        content = response.content.decode()
        # Should show actual device info, not "Unknown Device"
        assert "Unknown Device" not in content
        assert "Chrome" in content or "Windows" in content
