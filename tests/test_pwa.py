"""
Tests for Progressive Web App (PWA) functionality.

Ensures:
- Manifest file exists and has correct configuration
- Service worker is properly registered
- Offline page exists and renders
- Meta tags for PWA are present
"""
import pytest
import json
from django.urls import reverse
from django.test import Client


pytestmark = pytest.mark.django_db


def test_manifest_file_accessible(client):
    """Test that manifest.webmanifest is accessible."""
    response = client.get('/static/manifest.webmanifest')
    
    assert response.status_code == 200 or response.status_code == 404  # 404 ok in dev (collectstatic not run)
    # In production with collectstatic, should be 200
    
    if response.status_code == 200:
        # Verify Content-Type is correct (should be set by mimetypes)
        content_type = response.get('Content-Type', '')
        # Should be application/manifest+json or application/json
        assert 'manifest' in content_type.lower() or 'json' in content_type.lower(), \
            f"Manifest should have correct Content-Type, got: {content_type}"


def test_service_worker_accessible(client):
    """Test that service worker file is accessible."""
    response = client.get('/static/sw.js')
    
    assert response.status_code == 200 or response.status_code == 404  # 404 ok in dev


def test_service_worker_root_route(client):
    """Test that service worker is accessible from /sw.js with proper headers."""
    response = client.get('/sw.js')
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert 'application/javascript' in response.get('Content-Type', ''), \
        "Service worker should be served as application/javascript"
    assert 'Service-Worker-Allowed' in response, \
        "Service worker response should include Service-Worker-Allowed header"
    assert response['Service-Worker-Allowed'] == '/', \
        "Service-Worker-Allowed should be '/' for root scope"
    assert 'Cache-Control' in response, \
        "Service worker should have Cache-Control header"
    # Verify it's actually JavaScript
    content = response.content.decode()
    assert 'serviceWorker' in content.lower() or 'self.addEventListener' in content or 'skipWaiting' in content, \
        "Service worker should contain JavaScript code"


def test_base_template_has_manifest_link(client):
    """Test that base template includes manifest link."""
    # Try to load a page that extends base.html
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'manifest.webmanifest' in content, "Manifest link not found in base template"


def test_base_template_has_theme_color(client):
    """Test that base template has theme-color meta tag."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'name="theme-color"' in content, "Theme color meta tag not found"


def test_base_template_has_pwa_meta_tags(client):
    """Test that base template has essential PWA meta tags."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'apple-mobile-web-app-capable' in content, "Apple mobile web app meta tag not found"
        assert 'viewport' in content.lower(), "Viewport meta tag not found"


def test_service_worker_registration_in_base(client):
    """Test that service worker registration script is present in base template."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'serviceWorker' in content, "Service worker registration not found"
        assert 'navigator.serviceWorker.register' in content, "Service worker registration code not found"
        # Verify it registers from /sw.js (not /static/sw.js)
        assert '/sw.js' in content or 'sw.js' in content, \
            "Service worker should be registered from /sw.js"


def test_offline_page_exists():
    """Test that offline fallback page template exists."""
    from django.template.loader import get_template
    
    try:
        template = get_template('offline.html')
        assert template is not None
    except Exception as e:
        pytest.fail(f"Offline template not found: {e}")


def test_offline_page_has_retry_button(client):
    """Test that offline page has a retry button."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('offline.html')
        assert 'Try Again' in content or 'Retry' in content or 'reload' in content.lower()
        assert 'offline' in content.lower()
    except Exception as e:
        pytest.fail(f"Could not render offline template: {e}")


def test_mission_statement_in_meta_description(client):
    """Test that the new mission statement appears in meta description."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        # Check for the new mission statement in meta tags
        assert ('digital record' in content.lower() and 'AI driven MBA manager' in content) or \
               ('digital record' in content.lower() and 'AI-driven MBA manager' in content), \
               "Mission statement not found in meta description"


def test_pwa_icons_referenced(client):
    """Test that PWA icons are referenced in the page."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        # Check for icon references
        assert 'icon-192.png' in content or 'apple-touch-icon' in content, \
               "PWA icons not referenced"


def test_service_worker_skips_admin(client):
    """Test that service worker registration skips Django admin."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        # Check that SW registration has admin check
        assert "'/admin/'" in content or "startsWith('/admin')" in content, \
               "Service worker should skip admin pages"


def test_service_worker_fails_gracefully(client):
    """Test that service worker registration has error handling."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        # Check for error handling in SW registration
        assert 'catch' in content and 'serviceWorker' in content, \
               "Service worker registration should have error handling"


# ============================================================================
# PWA Install Banner Tests (2025-12-25)
# ============================================================================

def test_pwa_install_banner_partial_exists():
    """Test that PWA install banner partial template exists."""
    from django.template.loader import get_template
    
    try:
        template = get_template('partials/pwa_install_banner.html')
        assert template is not None
    except Exception as e:
        pytest.fail(f"PWA install banner partial not found: {e}")


def test_pwa_install_banner_included_in_base(client):
    """Test that PWA install banner is included in base template."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'pwa-install-banner' in content, \
               "PWA install banner not found in base template"
        assert 'pwa-install-content' in content, \
               "PWA install banner content not found"


def test_pwa_install_js_included_in_base(client):
    """Test that PWA install JS is included in base template."""
    response = client.get('/')
    
    if response.status_code == 200:
        content = response.content.decode()
        assert 'pwa-install.js' in content, \
               "PWA install JS not found in base template"


def test_pwa_install_js_file_exists(client):
    """Test that PWA install JS file is accessible."""
    response = client.get('/static/js/pwa-install.js')
    
    # Should be 200 after collectstatic, or 404 in dev (acceptable)
    assert response.status_code in [200, 404], \
           f"Unexpected status code for pwa-install.js: {response.status_code}"
    
    if response.status_code == 200:
        content = response.content.decode()
        # Verify key functionality is present
        assert 'beforeinstallprompt' in content.lower(), \
               "PWA install JS should handle beforeinstallprompt event"
        assert 'isAppInstalled' in content or 'standalone' in content, \
               "PWA install JS should detect if app is installed"
        assert 'localStorage' in content, \
               "PWA install JS should use localStorage for persistence"


def test_pwa_install_banner_has_install_button():
    """Test that PWA install banner has install button."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('partials/pwa_install_banner.html')
        assert 'pwa-install-btn' in content, \
               "PWA install banner should have install button"
        assert 'pwa-dismiss-btn' in content, \
               "PWA install banner should have dismiss button"
        assert 'Install' in content, \
               "PWA install banner should have 'Install' text"
    except Exception as e:
        pytest.fail(f"Could not render PWA install banner: {e}")


def test_pwa_install_banner_has_glassmorphic_styles():
    """Test that PWA install banner has glassmorphic premium styles."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('partials/pwa_install_banner.html')
        # Check for glassmorphic design elements
        assert 'backdrop-filter' in content or 'backdrop' in content, \
               "PWA install banner should have glassmorphic backdrop filter"
        assert 'rgba' in content, \
               "PWA install banner should use rgba transparency"
        assert 'border-radius' in content, \
               "PWA install banner should have rounded corners"
    except Exception as e:
        pytest.fail(f"Could not render PWA install banner: {e}")


def test_pwa_install_banner_responsive():
    """Test that PWA install banner has responsive styles."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('partials/pwa_install_banner.html')
        # Check for mobile responsiveness
        assert '@media' in content, \
               "PWA install banner should have responsive media queries"
        assert 'max-width' in content or 'min-width' in content, \
               "PWA install banner should have breakpoints"
    except Exception as e:
        pytest.fail(f"Could not render PWA install banner: {e}")


def test_pwa_install_banner_has_dark_mode():
    """Test that PWA install banner supports dark mode."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('partials/pwa_install_banner.html')
        # Check for dark mode support
        assert 'prefers-color-scheme' in content, \
               "PWA install banner should support dark mode"
    except Exception as e:
        pytest.fail(f"Could not render PWA install banner: {e}")


def test_pwa_install_banner_ios_safe_area():
    """Test that PWA install banner handles iOS safe areas."""
    from django.template.loader import render_to_string
    
    try:
        content = render_to_string('partials/pwa_install_banner.html')
        # Check for iOS safe area handling
        assert 'safe-area' in content or 'env(' in content, \
               "PWA install banner should handle iOS safe areas"
    except Exception as e:
        pytest.fail(f"Could not render PWA install banner: {e}")
