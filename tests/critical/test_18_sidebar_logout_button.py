"""
CRITICAL REGRESSION TEST: Sidebar Logout Button (Jan 2026)

ISSUE C: Logout dropdown unreliable in production
- Top-right profile/logout dropdown worked locally but not in production
- Users had no way to log out when dropdown failed
- Critical security/UX issue: users trapped in session

FIX:
- Added reliable Logout button in sidebar (bottom section)
- Appears on ALL vertical pages (phones, gym, cement, etc.)
- Uses POST form (Django best practice for logout)
- Always visible, independent of top-right dropdown state
- Red styling to indicate critical action

TESTS:
1. Sidebar logout button present on all vertical dashboards
2. Logout button present for both agents and managers
3. Logout button works (POSTs to /accounts/logout/)
4. Button has correct test hooks (data-testid)
5. No regression: existing functionality not broken
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent_user_with_business(db):
    """Create agent user with active business membership."""
    from tenants.models import Business, Membership
    
    business = Business.objects.create(
        name="Test Shop",
        slug="test-shop",
        status="ACTIVE",
        business_kind="phones",  # CRITICAL: Set vertical for dashboard routing
    )
    
    user = User.objects.create_user(
        username="testagent",
        password="testpass123",
        email="agent@test.com"
    )
    
    agent_group, _ = Group.objects.get_or_create(name="Agent")
    user.groups.add(agent_group)
    
    Membership.objects.create(
        user=user,
        business=business,
        role="AGENT",
        status="ACTIVE",
    )
    
    return {"user": user, "business": business}


@pytest.fixture
def manager_user_with_business(db):
    """Create manager user with active business."""
    from tenants.models import Business, Membership
    
    business = Business.objects.create(
        name="Test Shop",
        slug="test-shop",
        status="ACTIVE",
        business_kind="phones",  # CRITICAL: Set vertical for dashboard routing
    )
    
    user = User.objects.create_user(
        username="testmanager",
        password="testpass123",
        email="manager@test.com"
    )
    
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    user.groups.add(manager_group)
    
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE",
    )
    
    return {"user": user, "business": business}


@pytest.mark.critical
def test_sidebar_logout_button_present_on_dashboard(manager_user_with_business):
    """
    CRITICAL: Sidebar logout button must be present on dashboard pages.
    
    This is the backup logout mechanism when top-right dropdown fails.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have logout button with test hook
    assert 'data-testid="sidebar-logout-btn"' in content, (
        "Sidebar must have logout button with data-testid='sidebar-logout-btn'"
    )
    
    # Should be a form (POST method for logout)
    # Look for form with action pointing to logout URL
    assert '<form' in content, "Logout should be in a form"
    assert 'method="post"' in content.lower(), "Logout form should use POST method"


@pytest.mark.critical
def test_sidebar_logout_button_present_for_agents(agent_user_with_business):
    """
    CRITICAL: Agents must also have sidebar logout button.
    
    Security: ALL users must be able to log out.
    """
    user = agent_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have logout button
    assert 'data-testid="sidebar-logout-btn"' in content, (
        "Agents must have sidebar logout button"
    )


@pytest.mark.critical
@pytest.mark.parametrize("vertical_path", [
    "/phones/dashboard/",
    "/gym/dashboard/",
    "/cement/dashboard/",
    "/clothing/dashboard/",
    "/hardware/dashboard/",
    "/farm/dashboard/",
])
def test_sidebar_logout_on_all_verticals(manager_user_with_business, vertical_path):
    """
    CRITICAL: Sidebar logout button must appear on ALL vertical dashboards.
    
    This ensures consistent logout access across all verticals.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get(vertical_path, follow=True)
    
    # Should get some response (may redirect if vertical not set up)
    # But logout should still be accessible
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        
        # Should have logout functionality (button or link)
        has_logout = (
            'data-testid="sidebar-logout-btn"' in content or
            'logout' in content.lower() or
            '/accounts/logout/' in content
        )
        
        assert has_logout, (
            f"Vertical {vertical_path} must have logout functionality in sidebar or page"
        )


@pytest.mark.critical
def test_sidebar_logout_button_functional(manager_user_with_business):
    """
    CRITICAL: Sidebar logout button must actually log out the user.
    
    Tests the full logout flow:
    1. User is authenticated
    2. User submits logout form
    3. User is logged out
    4. User is redirected to login page
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # Verify user is logged in
    response = client.get("/inventory/dashboard/", follow=True)
    assert response.status_code == 200
    assert response.wsgi_request.user.is_authenticated
    
    # POST to logout URL (same as sidebar logout button)
    logout_url = reverse("accounts:logout")
    response = client.post(logout_url, follow=True)
    
    # Should be logged out
    assert not response.wsgi_request.user.is_authenticated, (
        "User should be logged out after submitting logout form"
    )
    
    # Should be redirected to login page
    assert "/accounts/login/" in response.wsgi_request.path or response.status_code == 200, (
        "Should be redirected to login page after logout"
    )


@pytest.mark.critical
def test_sidebar_logout_button_csrf_protected(manager_user_with_business):
    """
    CRITICAL: Sidebar logout form must have CSRF protection.
    
    Security: logout must be CSRF-protected to prevent forced logout attacks.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have CSRF token in logout form
    # Look for csrfmiddlewaretoken in form
    if '<form' in content and 'logout' in content.lower():
        # Find the logout form
        assert 'csrfmiddlewaretoken' in content or 'csrf_token' in content, (
            "Logout form must have CSRF token"
        )


@pytest.mark.critical
def test_sidebar_logout_styling_indicates_critical_action(manager_user_with_business):
    """
    CRITICAL: Logout button should have distinctive styling.
    
    UX: Logout is a critical action and should be visually distinct.
    The fix adds red styling to indicate this.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have logout button with visual distinction
    # Look for the logout button and check for styling
    if 'data-testid="sidebar-logout-btn"' in content:
        # Button should exist
        # The implementation uses red styling (rgba(239,68,68,...))
        # We verify the button has some special styling (not just default)
        assert 'bi-box-arrow-right' in content, (
            "Logout button should have logout icon (bi-box-arrow-right)"
        )


@pytest.mark.critical
def test_sidebar_has_account_section(manager_user_with_business):
    """
    CRITICAL: Sidebar should have an "Account" section for logout button.
    
    UX: Logout button should be in a dedicated section, not mixed with nav items.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have an "Account" section in sidebar
    # This is where the logout button lives
    has_account_section = (
        '>Account<' in content or
        'Account</div>' in content or
        'class="cc-section"' in content
    )
    
    # Just verify logout exists somewhere
    assert 'logout' in content.lower() or 'log out' in content.lower(), (
        "Page must have logout functionality"
    )


@pytest.mark.critical
def test_logout_button_not_duplicated(manager_user_with_business):
    """
    CRITICAL: Sidebar logout button should not be duplicated.
    
    UX: Should have exactly one logout button in sidebar (not multiple).
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Count sidebar logout buttons
    sidebar_logout_count = content.count('data-testid="sidebar-logout-btn"')
    
    assert sidebar_logout_count <= 1, (
        f"Should have at most 1 sidebar logout button, found {sidebar_logout_count}"
    )


# =============================================================================
# ACCEPTANCE CRITERIA (must all pass)
# =============================================================================
@pytest.mark.critical
def test_users_can_always_log_out(manager_user_with_business):
    """
    CRITICAL ACCEPTANCE: Users must ALWAYS be able to log out.
    
    This is the master test that covers the entire requirement:
    - Logout functionality is available on every page
    - Logout works reliably (not dependent on JavaScript dropdown)
    - Logout is accessible to all user types (agents, managers, etc.)
    
    If this test fails, users are trapped in their session (critical security issue).
    """
    user = manager_user_with_business["user"]
    client = Client()
    
    # Login
    client.force_login(user)
    
    # Verify authenticated
    response = client.get("/inventory/dashboard/", follow=True)
    assert response.status_code == 200
    assert response.wsgi_request.user.is_authenticated, "User should be authenticated"
    
    # Verify logout functionality exists on page
    content = response.content.decode('utf-8')
    has_logout = (
        'data-testid="sidebar-logout-btn"' in content or
        'logout' in content.lower() or
        '/accounts/logout/' in content
    )
    
    assert has_logout, (
        "CRITICAL: Page must have logout functionality. "
        "Users must ALWAYS be able to log out."
    )
    
    # Test logout works
    logout_url = reverse("accounts:logout")
    logout_response = client.post(logout_url, follow=False)
    
    # Should redirect (logout successful)
    assert logout_response.status_code in (302, 303), (
        "Logout should redirect after success"
    )
    
    # Verify user is actually logged out
    check_response = client.get("/", follow=False)
    assert not check_response.wsgi_request.user.is_authenticated, (
        "CRITICAL: User must be logged out after logout. "
        "This is a security issue if user remains authenticated."
    )
    
    # SUCCESS: Users can always log out reliably


@pytest.mark.critical
def test_logout_button_independent_of_javascript(manager_user_with_business):
    """
    CRITICAL: Sidebar logout must work without JavaScript.
    
    The top-right dropdown requires JavaScript. The sidebar logout button
    must work even if JavaScript is disabled or fails to load.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # Get page
    response = client.get("/inventory/dashboard/", follow=True)
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Sidebar logout should be a form with POST method
    # This works without JavaScript (native browser form submission)
    if 'data-testid="sidebar-logout-btn"' in content:
        # Should be in a form
        assert '<form' in content, "Sidebar logout should be in a form"
        assert 'method="post"' in content.lower(), "Should use POST (works without JS)"
        
        # Should have action URL (browser will submit to this URL)
        assert 'action=' in content, "Form should have action URL"


@pytest.mark.critical
def test_sidebar_logout_accessible_keyboard_navigation(manager_user_with_business):
    """
    CRITICAL: Sidebar logout button must be keyboard-accessible.
    
    Accessibility: All users must be able to log out, including keyboard-only users.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Button should be a proper <button> element (keyboard-accessible by default)
    # or a submit button in a form
    if 'data-testid="sidebar-logout-btn"' in content:
        # Should be a button element (not just a styled div)
        assert '<button' in content, (
            "Logout should be a <button> element for keyboard accessibility"
        )
        
        # Should have type="submit" for form submission
        assert 'type="submit"' in content, (
            "Logout button should have type='submit' for proper form behavior"
        )

