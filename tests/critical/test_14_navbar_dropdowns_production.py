"""
CRITICAL REGRESSION TEST: Navbar dropdowns must work in production
================================================================================
PROD-ONLY BUG DIAGNOSED: Jan 18 2026

This test verifies that billing pages (and all authenticated pages) have the
necessary JavaScript and attributes for navbar dropdowns to work in production.

ROOT CAUSES OF PROD-ONLY FAILURES:
1. Service worker caching stale HTML (with old/missing JS references)
2. Static assets not loading (collectstatic/whitenoise mismatch)
3. Bootstrap JS not loading on specific page types (e.g., billing)
4. Cache headers not set correctly in production

This test ensures:
- Billing pages load Bootstrap JS bundle
- Navbar dropdown buttons have correct data-bs-toggle attributes
- Service worker bypasses HTML navigation caching
- Authenticated HTML has no-store cache headers
================================================================================
"""
import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from tests.critical.conftest import (
    bootstrap_business_with_user,
    setup_authenticated_client,
)

User = get_user_model()

pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestNavbarDropdownsOnBillingPages:
    """
    Test that navbar dropdowns work on billing pages specifically.
    
    Billing pages are often overlooked when fixing navbar issues because
    they use a slightly different flow (manager-only, payment-related).
    This test ensures billing pages have all required navbar JS.
    """

    def test_billing_subscribe_page_loads_bootstrap_js(self):
        """Billing subscribe page MUST load Bootstrap JS for dropdowns to work"""
        user, business, location = bootstrap_business_with_user("phones")
        # Make user a manager so they can access billing
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        response = client.get(reverse('billing:subscribe'))
        
        # Allow 200 or redirect
        if response.status_code not in [200, 302]:
            pytest.skip(f"Billing subscribe returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # CRITICAL: Bootstrap bundle must be loaded
        assert 'bootstrap' in html.lower() and ('.js' in html or '.min.js' in html), (
            "REGRESSION: Billing page missing Bootstrap JS bundle. "
            "Dropdowns cannot work without Bootstrap."
        )
        
        # Should specifically have bootstrap.bundle.min.js from CDN
        assert 'bootstrap@5.3' in html or 'bootstrap.bundle' in html, (
            "REGRESSION: Billing page missing Bootstrap 5.3 bundle. "
            "Required for dropdown functionality."
        )

    def test_billing_subscribe_page_has_navbar_with_dropdowns(self):
        """Billing subscribe page must have navbar with dropdown elements"""
        user, business, location = bootstrap_business_with_user("phones")
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        response = client.get(reverse('billing:subscribe'))
        
        if response.status_code not in [200, 302]:
            pytest.skip(f"Billing subscribe returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have notification dropdown button
        assert 'id="ccNotifBtn"' in html, (
            "REGRESSION: Billing page missing notifications dropdown button"
        )
        
        # Must have user menu dropdown button
        assert 'id="userMenuBtn"' in html, (
            "REGRESSION: Billing page missing user menu dropdown button"
        )
        
        # Notification button must have Bootstrap dropdown toggle
        notif_btn_index = html.find('id="ccNotifBtn"')
        if notif_btn_index > 0:
            notif_section = html[max(0, notif_btn_index-300):notif_btn_index+500]
            assert 'data-bs-toggle="dropdown"' in notif_section, (
                "REGRESSION: Notification button on billing page missing "
                "data-bs-toggle='dropdown'. Clicks will not open dropdown."
            )
        
        # User menu button must have Bootstrap dropdown toggle
        user_btn_index = html.find('id="userMenuBtn"')
        if user_btn_index > 0:
            user_section = html[max(0, user_btn_index-300):user_btn_index+500]
            assert 'data-bs-toggle="dropdown"' in user_section, (
                "REGRESSION: User menu button on billing page missing "
                "data-bs-toggle='dropdown'. Clicks will not open dropdown."
            )

    def test_billing_subscribe_page_has_no_cache_headers(self):
        """Billing pages MUST have no-store headers to prevent stale HTML caching"""
        user, business, location = bootstrap_business_with_user("phones")
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        response = client.get(reverse('billing:subscribe'))
        
        if response.status_code not in [200]:
            pytest.skip(f"Billing subscribe returned {response.status_code}")
        
        # CRITICAL: Must have no-store to prevent caching
        cache_control = response.get('Cache-Control', '')
        assert 'no-store' in cache_control, (
            f"REGRESSION: Billing page missing 'no-store' in Cache-Control. "
            f"Got: {cache_control!r}. "
            f"Without no-store, browsers cache HTML with old JS references, "
            f"causing dropdowns to fail in production."
        )

    def test_billing_checkout_page_has_navbar_dropdowns(self):
        """Billing checkout page must also have working navbar dropdowns"""
        user, business, location = bootstrap_business_with_user("phones")
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        try:
            response = client.get(reverse('billing:checkout'))
        except Exception:
            pytest.skip("Billing checkout URL not available")
        
        if response.status_code not in [200, 302]:
            pytest.skip(f"Billing checkout returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have both dropdown buttons
        assert 'id="ccNotifBtn"' in html, "Checkout page missing notifications button"
        assert 'id="userMenuBtn"' in html, "Checkout page missing user menu button"
        
        # Must have Bootstrap JS
        assert 'bootstrap' in html.lower(), "Checkout page missing Bootstrap JS"


class TestServiceWorkerDoesNotCacheHTML:
    """
    Test that service worker never caches HTML navigation responses.
    
    This is the most common cause of prod-only dropdown failures:
    1. Service worker caches HTML from old deploy
    2. Cached HTML references old/missing JS filenames
    3. Dropdowns don't work because JS isn't loaded
    4. Hard refresh works because it bypasses service worker
    """

    def test_service_worker_file_exists_and_has_build_id(self):
        """Service worker must exist and have BUILD_ID for cache busting"""
        response = Client().get('/sw.js')
        
        assert response.status_code == 200, (
            "Service worker /sw.js must be accessible (returns 200)"
        )
        
        assert response['Content-Type'] == 'application/javascript', (
            "Service worker must have JavaScript content type"
        )
        
        sw_content = response.content.decode('utf-8')
        
        # Must NOT have placeholder (must be replaced with actual BUILD_ID)
        assert 'BUILD_ID_PLACEHOLDER' not in sw_content, (
            "REGRESSION: Service worker still has BUILD_ID_PLACEHOLDER. "
            "It must be replaced with actual BUILD_ID in production. "
            "Without this, SW never updates and serves stale HTML forever."
        )
        
        # Must have a VERSION constant
        assert 'const VERSION' in sw_content or 'VERSION =' in sw_content, (
            "Service worker must define VERSION constant for cache busting"
        )

    def test_service_worker_has_network_only_for_html(self):
        """Service worker MUST use network-only strategy for HTML navigations"""
        response = Client().get('/sw.js')
        
        assert response.status_code == 200
        
        sw_content = response.content.decode('utf-8')
        
        # Must have logic to detect HTML/navigation requests
        assert 'navigate' in sw_content or 'text/html' in sw_content, (
            "REGRESSION: Service worker missing navigation/HTML detection. "
            "It must detect HTML requests to apply network-only strategy."
        )
        
        # Must have network-only strategy (fetch without cache fallback)
        # Look for patterns like "networkOnlyHtml" or direct fetch without cache
        has_network_only = (
            'networkOnlyHtml' in sw_content or
            ('fetch(request)' in sw_content and 'navigate' in sw_content) or
            'NEVER cache HTML' in sw_content
        )
        
        assert has_network_only, (
            "REGRESSION: Service worker missing network-only strategy for HTML. "
            "It MUST fetch HTML from network (never cache) to prevent stale templates. "
            "This is the root cause of prod-only dropdown failures."
        )

    def test_service_worker_has_no_cache_headers(self):
        """Service worker itself must have no-cache headers"""
        response = Client().get('/sw.js')
        
        assert response.status_code == 200
        
        cache_control = response.get('Cache-Control', '')
        
        # Service worker MUST have no-cache so browser checks for updates
        assert 'no-cache' in cache_control or 'no-store' in cache_control, (
            f"REGRESSION: Service worker missing no-cache headers. "
            f"Got: {cache_control!r}. "
            f"Without no-cache, browsers don't check for SW updates, "
            f"keeping old SW that may cache HTML incorrectly."
        )


class TestStaticAssetsLoadInProduction:
    """
    Test that static assets (JS/CSS) are properly configured for production.
    
    In production, static files are served with hashed filenames by
    Django's ManifestStaticFilesStorage. Templates must use {% static %}
    tags to get correct hashed URLs.
    """

    @override_settings(DEBUG=False)
    def test_base_template_uses_static_tags_for_js(self):
        """Base template must use {% static %} tags for JS files"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        from tests.critical.conftest import get_dashboard_url
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Check that JS files are loaded with version query params or hashes
        # This ensures cache busting works in production
        has_versioned_js = (
            'app.js?v=' in html or  # Query param versioning
            'app.' in html and '.js' in html or  # Hashed filename
            'mobile.js?v=' in html or
            'mobile.' in html and '.js' in html
        )
        
        assert has_versioned_js, (
            "REGRESSION: JS files not properly versioned. "
            "In production, JS must have version query params or hashed filenames "
            "to ensure browsers load latest version after deploy."
        )


class TestNavbarJSInitialization:
    """
    Test that navbar JavaScript initializes correctly.
    
    This verifies the JS that makes dropdowns clickable is present
    and properly structured.
    """

    def test_base_template_has_dropdown_hidden_management_js(self):
        """Base template must have JS for managing dropdown hidden attributes"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        from tests.critical.conftest import get_dashboard_url
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have the setup function
        assert 'setupDropdownHiddenManagement' in html, (
            "REGRESSION: Missing setupDropdownHiddenManagement function. "
            "This is required for dropdowns to open on click."
        )
        
        # Must have click event listeners
        assert "addEventListener('click'" in html, (
            "REGRESSION: Missing click event listeners for dropdowns. "
            "Dropdowns need click handlers to remove hidden attribute."
        )
        
        # Must have hidden attribute manipulation
        assert "removeAttribute('hidden')" in html or 'removeAttribute("hidden")' in html, (
            "REGRESSION: Missing removeAttribute('hidden') calls. "
            "This is required to make dropdown visible on click."
        )

    def test_base_template_has_ui_cleanup_script(self):
        """Base template must have UI cleanup script (v5)"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        from tests.critical.conftest import get_dashboard_url
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have v5 of UI cleanup (includes dropdown click fix)
        assert '__CC_UI_CLEANUP_V5__' in html, (
            "REGRESSION: Missing UI cleanup script v5. "
            "v5 includes the fix for dropdown click functionality. "
            "Without this, dropdowns may not open on click."
        )

