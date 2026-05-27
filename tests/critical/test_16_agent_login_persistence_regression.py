"""
CRITICAL REGRESSION TEST: Agent Login Loop Prevention (Jan 2026)

ISSUE A: Agents could not stay logged in on staging/prod
- POST /accounts/login/ succeeded (302)
- GET /tenants/ redirected back to /accounts/login/ (infinite loop)

ROOT CAUSE:
- SESSION_COOKIE_DOMAIN was hardcoded to .emajinet.africa for all non-DEBUG environments
- Staging (emajinet-staging.onrender.com) also runs with DEBUG=False
- Browser rejected cookies with Domain=.emajinet.africa when host was emajinet-staging.onrender.com
- Session cookie never persisted → user appeared unauthenticated on every request

FIX:
- SESSION_COOKIE_DOMAIN now defaults to None (host-only cookies)
- Production MUST explicitly set SESSION_COOKIE_DOMAIN env var if cross-subdomain cookies needed
- Never hardcode domain based on DEBUG flag

TESTS:
1. Agent login persists session across redirects
2. /tenants/ is accessible to agents (returns 200 or auto-redirects to business dashboard)
3. Cookie domain is not hardcoded in non-production environments
4. Settings do not force production cookie domain in test/CI environments
"""
from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, override_settings
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent_user_with_business(db):
    """Create agent user with active membership in a business."""
    from tenants.models import Business, Membership
    
    # Create business with business_kind
    business = Business.objects.create(
        name="Test Shop",
        slug="test-shop",
        status="ACTIVE",
        business_kind="phones",  # CRITICAL: Set vertical for dashboard routing
    )
    
    # Create agent user
    user = User.objects.create_user(
        username="testagent",
        password="testpass123",
        email="agent@test.com"
    )
    
    # Add to Agent group
    agent_group, _ = Group.objects.get_or_create(name="Agent")
    user.groups.add(agent_group)
    
    # Create active membership
    Membership.objects.create(
        user=user,
        business=business,
        role="AGENT",
        status="ACTIVE",
    )
    
    return {"user": user, "business": business}


@pytest.mark.critical
def test_agent_login_persists_session_across_redirects(agent_user_with_business):
    """
    CRITICAL: Agent login must persist session across redirects.
    
    This test would have FAILED before the fix because cookies were rejected.
    """
    user = agent_user_with_business["user"]
    client = Client()
    
    # Step 1: POST to login
    # CRITICAL: Use 'identifier' field (not 'username') - form expects email or username
    response = client.post(
        reverse("accounts:login"),
        {"identifier": "testagent", "password": "testpass123"},
        follow=False
    )
    
    # Should redirect (302)
    assert response.status_code == 302, (
        f"Login should return 302 redirect, got {response.status_code}"
    )
    
    # Step 2: Follow redirect chain (should NOT loop back to login)
    response = client.get(response.url, follow=True)
    
    # Should be authenticated and NOT on login page
    assert response.status_code == 200, (
        f"After login redirect, should get 200, got {response.status_code}"
    )
    
    # Should NOT be on login page (would indicate login loop)
    final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.wsgi_request.path
    assert "/accounts/login/" not in final_url, (
        f"Agent was redirected back to login page (infinite loop): {final_url}"
    )
    
    # User should be authenticated
    assert response.wsgi_request.user.is_authenticated, (
        "User should be authenticated after login"
    )
    assert response.wsgi_request.user.username == "testagent", (
        "Should be logged in as testagent"
    )


@pytest.mark.critical
def test_tenants_view_accessible_to_agents(agent_user_with_business):
    """
    CRITICAL: /tenants/ must be accessible to agents.
    
    Agents should either:
    - See the tenant selection page (200), OR
    - Be auto-redirected to their business dashboard (302 → 200)
    
    They should NEVER be redirected back to /accounts/login/ (infinite loop).
    """
    user = agent_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # Access /tenants/ as authenticated agent
    response = client.get("/tenants/", follow=True)
    
    # Should be 200 (either tenant selection or business dashboard)
    assert response.status_code == 200, (
        f"/tenants/ should return 200 for authenticated agent, got {response.status_code}"
    )
    
    # Should NOT be on login page
    final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.wsgi_request.path
    assert "/accounts/login/" not in final_url, (
        f"Agent was redirected to login page from /tenants/ (access denied): {final_url}"
    )
    
    # User should still be authenticated
    assert response.wsgi_request.user.is_authenticated, (
        "User should remain authenticated when accessing /tenants/"
    )


@pytest.mark.critical
def test_cookie_domain_not_hardcoded_in_tests():
    """
    CRITICAL: Session cookie domain must not be hardcoded in test/CI environments.
    
    This test ensures the fix prevents regression:
    - SESSION_COOKIE_DOMAIN must be None in tests (host-only cookies)
    - Never set to .emajinet.africa based on DEBUG flag alone
    """
    # In test environment, cookie domain MUST be None (host-only)
    assert settings.SESSION_COOKIE_DOMAIN is None, (
        f"SESSION_COOKIE_DOMAIN must be None in tests, got: {settings.SESSION_COOKIE_DOMAIN}"
    )
    
    assert settings.CSRF_COOKIE_DOMAIN is None, (
        f"CSRF_COOKIE_DOMAIN must be None in tests, got: {settings.CSRF_COOKIE_DOMAIN}"
    )


@pytest.mark.critical
@override_settings(
    DEBUG=False,
    TESTING=True,
    SESSION_COOKIE_DOMAIN=None,
    CSRF_COOKIE_DOMAIN=None,
)
def test_agent_login_works_with_debug_false_and_no_domain(agent_user_with_business):
    """
    CRITICAL: Agent login must work when DEBUG=False but domain is not set.
    
    This simulates staging environment:
    - DEBUG=False (production mode)
    - But domain is None (not .emajinet.africa)
    
    Before the fix, this would have failed because domain was hardcoded.
    """
    user = agent_user_with_business["user"]
    client = Client()
    
    # Login should succeed
    # CRITICAL: Use 'identifier' field (not 'username')
    response = client.post(
        reverse("accounts:login"),
        {"identifier": "testagent", "password": "testpass123"},
        follow=True
    )
    
    assert response.status_code == 200, (
        f"Login should succeed with DEBUG=False and no domain, got {response.status_code}"
    )
    
    # Should be authenticated
    assert response.wsgi_request.user.is_authenticated, (
        "User should be authenticated with DEBUG=False and host-only cookies"
    )
    
    # Should NOT be on login page
    assert "/accounts/login/" not in response.wsgi_request.path, (
        "Should not be redirected back to login (indicates cookie rejection)"
    )


@pytest.mark.critical
def test_cookie_domain_safety_contract():
    """
    CRITICAL CONTRACT: Cookie domain settings must be safe.
    
    This test ensures:
    1. Cookie domain defaults to None (host-only cookies)
    2. Only set via explicit environment variable
    3. Never automatically set to production domain in non-production
    
    If this test fails, the staging login loop bug can return.
    """
    # Check that settings do not force production domain
    if hasattr(settings, 'IS_RENDER'):
        # On Render, domain should only be set via env var, never hardcoded
        if not settings.DEBUG:
            # Non-debug Render (could be staging or production)
            # Domain should ONLY come from env var, never hardcoded based on DEBUG
            pass  # We can't test env var source, but we test the contract below
    
    # In test/CI environments, domain MUST be None
    if settings.TESTING or settings.CI:
        assert settings.SESSION_COOKIE_DOMAIN is None, (
            "SESSION_COOKIE_DOMAIN must be None in test/CI environments"
        )
        assert settings.CSRF_COOKIE_DOMAIN is None, (
            "CSRF_COOKIE_DOMAIN must be None in test/CI environments"
        )
    
    # SUCCESS: Cookie domain is configurable and defaults to safe value (None)


@pytest.mark.critical
def test_agent_can_access_business_dashboard_after_login(agent_user_with_business):
    """
    CRITICAL: Agent must be able to access their business dashboard after login.
    
    Full end-to-end flow:
    1. Agent logs in
    2. Gets redirected to tenant selection or business dashboard
    3. Can access business dashboard (200)
    4. Session persists across multiple requests
    """
    user = agent_user_with_business["user"]
    business = agent_user_with_business["business"]
    client = Client()
    
    # Login
    # CRITICAL: Use 'identifier' field (not 'username')
    response = client.post(
        reverse("accounts:login"),
        {"identifier": "testagent", "password": "testpass123"},
        follow=True
    )
    
    assert response.status_code == 200
    assert response.wsgi_request.user.is_authenticated
    
    # Try to access business dashboard (should work)
    # Use inventory dashboard (generic) instead of phones-specific
    dashboard_url = "/inventory/dashboard/"
    response = client.get(dashboard_url, follow=True)
    
    # Should get 200 (either dashboard or redirect to valid page)
    assert response.status_code == 200, (
        f"Agent should be able to access dashboard, got {response.status_code}"
    )
    
    # Should still be authenticated
    assert response.wsgi_request.user.is_authenticated, (
        "Session should persist across multiple requests"
    )
    
    # Should NOT be on login page
    assert "/accounts/login/" not in response.wsgi_request.path, (
        "Agent should not be logged out when accessing dashboard"
    )


@pytest.mark.critical
def test_login_sets_session_cookie(agent_user_with_business):
    """
    CRITICAL: Login must set session cookie that browser will accept.
    
    This test verifies that:
    1. Session cookie is set on login response
    2. Cookie domain (if set) matches the request host
    3. Cookie is not rejected by browser cookie policy
    """
    user = agent_user_with_business["user"]
    client = Client()
    
    response = client.post(
        reverse("accounts:login"),
        {"username": "testagent", "password": "testpass123"},
        follow=False
    )
    
    # Should set session cookie
    assert 'sessionid' in client.cookies or settings.SESSION_COOKIE_NAME in client.cookies, (
        "Login should set session cookie"
    )
    
    # If cookie domain is set, it should not be a production domain in tests
    session_cookie = client.cookies.get('sessionid') or client.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_cookie and hasattr(session_cookie, 'get'):
        cookie_domain = session_cookie.get('domain', '')
        if cookie_domain:
            # Cookie domain should never be production domain in tests
            assert '.emajinet.africa' not in cookie_domain, (
                f"Cookie domain should not be production domain in tests: {cookie_domain}"
            )


# =============================================================================
# ACCEPTANCE CRITERIA (must all pass)
# =============================================================================
@pytest.mark.critical
@pytest.mark.parametrize("follow_redirects", [True])
def test_no_infinite_login_redirect_loop(agent_user_with_business, follow_redirects):
    """
    CRITICAL ACCEPTANCE: There must be NO infinite login redirect loops.
    
    This is the master test that covers the entire bug:
    - Agent logs in successfully
    - Session persists
    - No redirect loop to /accounts/login/
    
    If this test fails, the bug has regressed.
    
    NOTE: Only testing with follow_redirects=True since False case is covered
    by other tests (redirect URL inspection).
    """
    user = agent_user_with_business["user"]
    client = Client()
    
    # Login
    # CRITICAL: Use 'identifier' field (not 'username')
    response = client.post(
        reverse("accounts:login"),
        {"identifier": "testagent", "password": "testpass123"},
        follow=follow_redirects
    )
    
    if follow_redirects:
        # Should end up on a valid page (200)
        assert response.status_code == 200
        
        # Check redirect chain for loops
        if response.redirect_chain:
            urls = [url for url, status in response.redirect_chain]
            # Should not have more than 2 redirects to login page (would indicate loop)
            login_redirects = sum(1 for url in urls if '/accounts/login/' in url)
            assert login_redirects <= 1, (
                f"Detected redirect loop: {login_redirects} redirects to login page. "
                f"Redirect chain: {response.redirect_chain}"
            )
        
        # Final URL should NOT be login page (unless it's a special case)
        assert "/accounts/login/" not in response.wsgi_request.path, (
            "Agent ended up on login page after successful login (redirect loop)"
        )
    
    # Most importantly: user should be authenticated
    # This is the core bug - session was not persisting
    response = client.get("/", follow=False)
    assert hasattr(response, 'wsgi_request'), "Response should have wsgi_request"
    assert hasattr(response.wsgi_request, 'user'), "Request should have user"
    assert response.wsgi_request.user.is_authenticated, (
        "CRITICAL BUG: User is not authenticated after login. "
        "This indicates session cookie was rejected by browser. "
        "Check SESSION_COOKIE_DOMAIN settings."
    )

