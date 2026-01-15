# tests/critical/test_10_no_domain_redirect_loops.py
"""
CRITICAL TEST 10: No Domain/HTTPS Redirect Loops

These tests ensure that production domains don't have redirect loops when accessed
behind a proxy (like Render). This prevents ERR_TOO_MANY_REDIRECTS in production.

FAILURE HERE = Production site inaccessible = Critical incident

Key scenarios tested:
1. Both www and apex domains work without redirect loops
2. HTTPS detection works correctly behind proxy (X-Forwarded-Proto header)
3. No canonical host redirects fighting with proxy redirects
4. All public routes work on both domains

Fix History:
- 2026-01-15: Added tests to catch ERR_TOO_MANY_REDIRECTS in production.
  Fixed by disabling CanonicalHostMiddleware and ensuring SECURE_PROXY_SSL_HEADER
  and USE_X_FORWARDED_HOST are set in production.
"""
import pytest
from django.test import Client, override_settings
from django.test.client import RedirectCycleError
from django.contrib.auth import get_user_model

User = get_user_model()

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]

# Production domains to test
PRODUCTION_DOMAINS = [
    "emajinet.africa",
    "www.emajinet.africa",
]

# Staging domains to test
STAGING_DOMAINS = [
    "emajinet-staging.onrender.com",
]

# Maximum allowed redirects before considering it a loop
# For domain canonicalization, we allow up to 2 redirects (one for domain, one for path)
# But production should have 0 domain redirects (both www and apex should work)
MAX_ALLOWED_REDIRECTS = 2

# Public paths that should work without authentication
PUBLIC_PATHS = [
    "/",
    "/accounts/login/",
    "/accounts/signup/",
]

# Authenticated paths that should redirect to login but not loop
AUTHENTICATED_PATHS = [
    "/inventory/dashboard/",
    "/dashboard/",
]


def _check_no_redirect_loop(client, path, host, extra_headers=None):
    """
    Helper to check for redirect loops on a specific host+path.
    
    Args:
        client: Django test client
        path: URL path to test
        host: Host header value
        extra_headers: Additional headers (e.g., X-Forwarded-Proto)
    
    Returns:
        Response object
    
    Raises:
        AssertionError if redirect loop detected
    """
    headers = {"HTTP_HOST": host}
    if extra_headers:
        headers.update(extra_headers)
    
    try:
        response = client.get(path, follow=True, **headers)
    except RedirectCycleError as e:
        pytest.fail(
            f"Redirect loop detected for {host}{path}: {e}"
        )
    
    # Check redirect chain length
    if hasattr(response, "redirect_chain"):
        redirect_count = len(response.redirect_chain)
        if redirect_count > MAX_ALLOWED_REDIRECTS:
            chain_details = "\n".join(
                f"  {i+1}. {url} [{status}]" 
                for i, (url, status) in enumerate(response.redirect_chain)
            )
            pytest.fail(
                f"Excessive redirects for {host}{path} "
                f"({redirect_count} > {MAX_ALLOWED_REDIRECTS}):\n{chain_details}"
            )
    
    return response


class TestProductionDomainsNoRedirectLoops:
    """Test that production domains work without redirect loops."""
    
    @pytest.mark.parametrize("host", PRODUCTION_DOMAINS)
    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_public_path_no_redirect_loop_https(self, host, path):
        """
        Public paths should work on both www and apex domains with HTTPS.
        This simulates how Render sends requests to Django.
        """
        client = Client()
        
        # Simulate Render proxy headers (HTTPS request)
        extra_headers = {
            "HTTP_X_FORWARDED_PROTO": "https",
            "HTTP_X_FORWARDED_HOST": host,
        }
        
        response = _check_no_redirect_loop(client, path, host, extra_headers)
        
        # Must return 200 (or 302 for paths that need auth, but not a loop)
        assert response.status_code in (200, 302), (
            f"{host}{path} returned {response.status_code}"
        )
        
        # If redirected, check it's not bouncing between hosts/schemes
        if hasattr(response, "redirect_chain") and response.redirect_chain:
            # Extract hosts from redirect chain
            from urllib.parse import urlparse
            redirect_hosts = set()
            redirect_schemes = set()
            for url, _ in response.redirect_chain:
                parsed = urlparse(url)
                if parsed.netloc:
                    redirect_hosts.add(parsed.netloc)
                if parsed.scheme:
                    redirect_schemes.add(parsed.scheme)
            
            # Should not bounce between multiple hosts or schemes
            # (One redirect www->apex or apex->www is OK, but not both)
            if len(redirect_hosts) > 1:
                pytest.fail(
                    f"Bouncing between hosts: {redirect_hosts}. "
                    f"Chain: {response.redirect_chain}"
                )
            if len(redirect_schemes) > 1:
                pytest.fail(
                    f"Bouncing between schemes: {redirect_schemes}. "
                    f"Chain: {response.redirect_chain}"
                )
    
    @pytest.mark.parametrize("host", PRODUCTION_DOMAINS)
    def test_login_page_no_redirect_loop(self, host):
        """
        Login page is the most critical public endpoint.
        It must work on both domains without redirect loops.
        """
        client = Client()
        
        # Simulate Render proxy headers (HTTPS request)
        extra_headers = {
            "HTTP_X_FORWARDED_PROTO": "https",
            "HTTP_X_FORWARDED_HOST": host,
        }
        
        response = _check_no_redirect_loop(client, "/accounts/login/", host, extra_headers)
        
        # Must return 200 (login page rendered successfully)
        assert response.status_code == 200, (
            f"Login page on {host} returned {response.status_code}"
        )
        
        # Must have minimal redirects (ideally 0)
        if hasattr(response, "redirect_chain"):
            assert len(response.redirect_chain) == 0, (
                f"Login page should not redirect: {response.redirect_chain}"
            )


class TestHTTPSDetectionBehindProxy:
    """Test that HTTPS detection works correctly behind proxy."""
    
    def test_is_secure_with_proxy_header(self):
        """
        Django must detect HTTPS correctly when X-Forwarded-Proto: https
        is present (Render proxy scenario).
        """
        client = Client()
        
        # Create a simple test view to check request.is_secure()
        # We'll test this via an actual endpoint that would redirect if
        # SECURE_SSL_REDIRECT is on and is_secure() is false
        
        # Simulate Render proxy headers (HTTPS request)
        extra_headers = {
            "HTTP_HOST": "emajinet.africa",
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        
        response = client.get("/accounts/login/", follow=False, **extra_headers)
        
        # With correct proxy settings, this should NOT redirect to https://
        # (because request.is_secure() should return True)
        # If it redirects, it means Django doesn't detect HTTPS correctly
        assert response.status_code == 200, (
            f"Expected 200 (page rendered), got {response.status_code}. "
            f"If 301/302, Django may not be detecting HTTPS correctly behind proxy."
        )
    
    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_no_https_redirect_loop_with_proxy_header(self):
        """
        With SECURE_SSL_REDIRECT=True and correct proxy settings,
        requests with X-Forwarded-Proto: https should NOT redirect.
        """
        client = Client()
        
        # Simulate Render proxy headers (HTTPS request)
        extra_headers = {
            "HTTP_HOST": "emajinet.africa",
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        
        try:
            response = client.get("/accounts/login/", follow=True, **extra_headers)
        except RedirectCycleError:
            pytest.fail(
                "Redirect loop detected with SECURE_SSL_REDIRECT=True. "
                "This means SECURE_PROXY_SSL_HEADER is not working correctly."
            )
        
        # Should render the page, not redirect
        assert response.status_code == 200


class TestStagingDomainsNoRedirectLoops:
    """Test that staging domains work without redirect loops."""
    
    @pytest.mark.parametrize("host", STAGING_DOMAINS)
    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_staging_public_path_no_redirect_loop(self, host, path):
        """
        Staging domains should work without redirect loops.
        .onrender.com hosts should never be redirected by canonical host middleware.
        """
        client = Client()
        
        # Simulate Render proxy headers (HTTPS request)
        extra_headers = {
            "HTTP_X_FORWARDED_PROTO": "https",
            "HTTP_X_FORWARDED_HOST": host,
        }
        
        response = _check_no_redirect_loop(client, path, host, extra_headers)
        
        # Must return 200 or 302 (auth redirect), but not loop
        assert response.status_code in (200, 302), (
            f"Staging {host}{path} returned {response.status_code}"
        )


class TestBothDomainsAllowedInSettings:
    """Test that both www and apex domains are in ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS."""
    
    def test_both_domains_in_allowed_hosts(self, settings):
        """Both emajinet.africa and www.emajinet.africa must be in ALLOWED_HOSTS."""
        from django.conf import settings
        
        allowed_hosts = settings.ALLOWED_HOSTS
        
        # Check for explicit domain entries or wildcards
        has_apex = (
            "emajinet.africa" in allowed_hosts
            or ".emajinet.africa" in allowed_hosts
            or "*" in allowed_hosts
        )
        has_www = (
            "www.emajinet.africa" in allowed_hosts
            or ".emajinet.africa" in allowed_hosts
            or "*" in allowed_hosts
        )
        
        assert has_apex, (
            "emajinet.africa must be in ALLOWED_HOSTS to prevent DisallowedHost errors"
        )
        assert has_www, (
            "www.emajinet.africa must be in ALLOWED_HOSTS to prevent DisallowedHost errors"
        )
    
    def test_both_domains_in_csrf_trusted_origins(self, settings):
        """Both domains must be in CSRF_TRUSTED_ORIGINS for form submissions."""
        from django.conf import settings
        
        csrf_origins = settings.CSRF_TRUSTED_ORIGINS
        
        has_apex = any(
            "emajinet.africa" in origin
            for origin in csrf_origins
        )
        has_www = any(
            "www.emajinet.africa" in origin
            for origin in csrf_origins
        )
        
        assert has_apex, (
            "https://emajinet.africa must be in CSRF_TRUSTED_ORIGINS"
        )
        assert has_www, (
            "https://www.emajinet.africa must be in CSRF_TRUSTED_ORIGINS"
        )


class TestProxySettingsCorrect:
    """Test that proxy SSL header settings are correct."""
    
    def test_secure_proxy_ssl_header_set(self, settings):
        """
        SECURE_PROXY_SSL_HEADER must be set to detect HTTPS behind proxy.
        This is critical for preventing redirect loops.
        """
        from django.conf import settings
        
        # In tests, this might be None (which is OK for tests)
        # But we can check it's set correctly if DEBUG=False
        if not settings.DEBUG and not settings.TESTING:
            assert settings.SECURE_PROXY_SSL_HEADER is not None, (
                "SECURE_PROXY_SSL_HEADER must be set in production to detect HTTPS behind proxy"
            )
            assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https"), (
                f"SECURE_PROXY_SSL_HEADER has unexpected value: {settings.SECURE_PROXY_SSL_HEADER}"
            )
    
    def test_use_x_forwarded_host_set(self, settings):
        """
        USE_X_FORWARDED_HOST should be True in production for correct host detection.
        """
        from django.conf import settings
        
        # In tests, this might be False (which is OK for tests)
        # But we can check it's set correctly if DEBUG=False
        if not settings.DEBUG and not settings.TESTING:
            assert settings.USE_X_FORWARDED_HOST is True, (
                "USE_X_FORWARDED_HOST must be True in production for correct host detection behind proxy"
            )


class TestNoCanonicalHostRedirects:
    """Test that canonical host redirects are disabled to prevent fighting with Render."""
    
    def test_canonical_host_empty_or_disabled(self, settings):
        """
        CANONICAL_HOST should be empty or middleware should be disabled.
        If set, it can cause redirect loops if Render has its own canonicalization.
        """
        from django.conf import settings
        
        canonical_host = getattr(settings, "CANONICAL_HOST", "")
        
        # If CANONICAL_HOST is set, check that the middleware is NOT active
        if canonical_host:
            middleware = settings.MIDDLEWARE
            canonical_middleware_active = any(
                "CanonicalHostMiddleware" in mw
                for mw in middleware
            )
            
            if canonical_middleware_active:
                pytest.fail(
                    "CANONICAL_HOST is set AND CanonicalHostMiddleware is active. "
                    "This can cause redirect loops if Render also does canonicalization. "
                    "Either set CANONICAL_HOST='' or disable the middleware."
                )

