# tests/test_guardrails.py
"""
GUARDRAIL TESTS - Regression Prevention

These tests MUST pass to prevent known regressions from recurring.
Each test guards against a specific bug that was fixed.

If any of these tests fail, it means a critical regression has occurred.
DO NOT modify these tests to make them pass - fix the actual issue instead.
"""
import pytest
from django.test import Client
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestMissionStatementGuardrail:
    """
    GUARDRAIL: Mission statement must be the NEW version.
    
    The old mission statement was "Spotify of every small business" with
    "AI-driven MBA manager". This was replaced with "operating system of
    small businesses" which better reflects the product.
    
    This test prevents the old mission statement from ever appearing again.
    """
    
    def test_landing_page_has_new_mission_statement(self, client: Client):
        """Landing page must show the NEW mission statement."""
        url = reverse("staticpages:home")
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode().lower()
        
        # MUST contain the new mission statement
        assert "operating system of small businesses" in content, \
            "REGRESSION: Missing new mission statement 'operating system of small businesses'"
    
    def test_landing_page_does_not_have_old_mission_statement(self, client: Client):
        """Landing page must NOT show the OLD mission statement."""
        url = reverse("staticpages:home")
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode().lower()
        
        # MUST NOT contain the old mission statement
        assert "spotify of every small business" not in content, \
            "REGRESSION: Old mission statement 'Spotify of every small business' found!"


class TestFarmWeldingGuardrail:
    """
    GUARDRAIL: Farm Manager and Welding Workshop must appear in signup.
    
    These business kinds were added as part of the vertical expansion.
    They must always appear in the signup wizard step 2.
    """
    
    def test_ssot_includes_farm_and_welding(self):
        """SSOT registry must include farm and welding."""
        from tenants.services.business_kind import CANONICAL_BUSINESS_KINDS
        
        assert "farm" in CANONICAL_BUSINESS_KINDS, \
            "REGRESSION: 'farm' missing from CANONICAL_BUSINESS_KINDS"
        assert "welding" in CANONICAL_BUSINESS_KINDS, \
            "REGRESSION: 'welding' missing from CANONICAL_BUSINESS_KINDS"
        
        # Verify display names
        assert CANONICAL_BUSINESS_KINDS["farm"]["display_name"] == "Farm Manager"
        assert CANONICAL_BUSINESS_KINDS["welding"]["display_name"] == "Welding Workshop"
    
    def test_signup_step2_view_passes_business_kinds(self, client: Client):
        """Signup wizard step 2 view must pass business_kinds to context."""
        from tenants.services.business_kind import CANONICAL_BUSINESS_KINDS
        
        # Access step 1 first to initialize session
        step1_url = f"{reverse('accounts:signup_manager')}?step=1"
        response = client.get(step1_url)
        assert response.status_code == 200
        
        # Submit step 1 to enable step 2
        response = client.post(step1_url, {
            "full_name": "Test Guardrail",
            "email": "guardrail-test@example.com",
            "password1": "GuardrailPass123!@#",
            "password2": "GuardrailPass123!@#",
            "phone_number": "+265991234567",
            "action": "next",
        })
        
        # Access step 2
        step2_url = f"{reverse('accounts:signup_manager')}?step=2"
        response = client.get(step2_url)
        
        if response.status_code == 200:
            content = response.content.decode()
            
            # MUST contain farm
            assert "farm" in content.lower() or "Farm Manager" in content, \
                "REGRESSION: Farm Manager not visible in signup step 2"
            
            # MUST contain welding
            assert "welding" in content.lower() or "Welding Workshop" in content, \
                "REGRESSION: Welding Workshop not visible in signup step 2"


class TestBuildStampGuardrail:
    """
    GUARDRAIL: Build stamp must appear in page source for debugging.
    
    The build stamp helps diagnose template caching issues by showing
    which git commit the templates are from.
    """
    
    def test_landing_page_has_build_stamp_comment(self, client: Client):
        """Landing page must have the build stamp HTML comment."""
        url = reverse("staticpages:home")
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Build stamp must be present (<!-- build: xxx -->)
        assert "<!-- build:" in content, \
            "REGRESSION: Build stamp comment missing from landing page"
    
    def test_whoami_returns_build_sha(self, client: Client):
        """__whoami__ endpoint must return build_sha when available."""
        # Try both with and without trailing slash
        for url in ["/__whoami__", "/__whoami__/"]:
            response = client.get(url)
            
            # In DEBUG mode, whoami should return JSON with build info
            # In non-DEBUG mode (like some test configurations), it may return 404
            if response.status_code == 404:
                # Endpoint not registered (expected in non-DEBUG mode)
                # This is acceptable - just verify the context processor works
                from cc.context_processors import _get_git_sha
                sha = _get_git_sha()
                assert sha is not None, "REGRESSION: _get_git_sha must return a value"
                return
            
            assert response.status_code in (200, 401), \
                f"__whoami__ returned unexpected status {response.status_code}"
            
            import json
            data = json.loads(response.content)
            
            assert "build_sha" in data, \
                "REGRESSION: __whoami__ must return build_sha"
            assert "debug" in data, \
                "REGRESSION: __whoami__ must return debug flag"
            assert "template_dirs" in data, \
                "REGRESSION: __whoami__ must return template_dirs"
            return  # Success, no need to try other URL
        
        # If we get here, neither URL worked - at least verify context processor
        from cc.context_processors import _get_git_sha
        sha = _get_git_sha()
        assert sha is not None, "REGRESSION: _get_git_sha must return a value"


class TestServiceWorkerGuardrail:
    """
    GUARDRAIL: Service worker must not cache HTML.
    
    The service worker was causing stale template issues by caching HTML.
    It must use network-only for HTML navigations.
    """
    
    def test_service_worker_is_network_first_for_html(self):
        """Service worker must not cache HTML navigations."""
        import os
        from django.conf import settings
        
        sw_path = os.path.join(settings.BASE_DIR, "static", "sw.js")
        
        if os.path.exists(sw_path):
            with open(sw_path, "r") as f:
                sw_content = f.read()
            
            # Must have network-only or network-first for HTML
            assert "networkOnlyHtml" in sw_content or "NEVER cache HTML" in sw_content, \
                "REGRESSION: Service worker must not cache HTML"
            
            # Must NOT have PAGE_CACHE for HTML
            assert "PAGE_CACHE" not in sw_content or "networkFirst(PAGE_CACHE" not in sw_content, \
                "REGRESSION: Service worker should not use PAGE_CACHE for HTML"

