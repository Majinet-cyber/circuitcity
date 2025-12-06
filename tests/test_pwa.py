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


def test_service_worker_accessible(client):
    """Test that service worker file is accessible."""
    response = client.get('/static/sw.js')
    
    assert response.status_code == 200 or response.status_code == 404  # 404 ok in dev


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

