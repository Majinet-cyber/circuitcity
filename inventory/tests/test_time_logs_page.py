"""
Test suite for the Time Logs page (/inventory/time/logs/).

Ensures the view:
- Actually renders HTML (not a wrapper object debug message)
- Returns status 200 for logged-in users with business context
- Contains expected page elements
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
def test_time_logs_page_renders_successfully(client):
    """
    Test that the time logs page renders properly and returns valid HTML.
    
    This test specifically addresses the bug where the page was returning:
    "_wrapped: callable returned by view (not executed)"
    
    Now it should return proper HTML with status 200.
    """
    # Create user
    user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
    
    # Create business
    business = Business.objects.create(
        name="Test Phone Business",
        slug="test-phone-business",
        business_kind=BusinessKind.PHONES
    )
    
    # Create membership
    Membership.objects.create(
        business=business,
        user=user,
        role="MANAGER",
        status="ACTIVE"
    )
    
    # Get or create location (Business creation may auto-create a default location)
    location = Location.objects.filter(business=business).first()
    if not location:
        location = Location.objects.create(
            business=business,
            name="Main Store",
            is_default=True
        )
    
    # Login
    client.login(username="testuser", password="testpass123")
    
    # Set up session with business context (required by @require_business decorator in urls.py)
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    
    # Perform GET request
    url = reverse("inventory:time_logs")
    response = client.get(url)
    
    # Assert successful response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Assert it's not the wrapper object debug text
    content = response.content.decode('utf-8')
    assert "_wrapped: callable returned by view" not in content, \
        "Page still returning wrapper object instead of rendering"
    assert "not executed" not in content, \
        "Page still showing 'not executed' debug message"
    
    # Assert the page contains expected elements
    assert "Time Logs" in content, "Page title 'Time Logs' not found"
    
    # Check template name if available (HttpResponse might not have it, but TemplateResponse does)
    if hasattr(response, 'template_name'):
        assert "time_logs.html" in str(response.template_name), "Wrong template used"


@pytest.mark.django_db
def test_time_logs_page_without_business_context(client):
    """
    Test that the page handles missing business context gracefully.
    
    With @require_business in urls.py, it should redirect to business selection.
    """
    # Create and login user (but don't create business/membership)
    user = User.objects.create_user(username="testuser2", email="test2@example.com", password="testpass123")
    client.login(username="testuser2", password="testpass123")
    
    # No business context in session
    url = reverse("inventory:time_logs")
    response = client.get(url)
    
    # Should redirect (302) when no business context due to @require_business
    assert response.status_code == 302, \
        f"Expected 302 redirect when no business context, got {response.status_code}"
    
    # Should redirect to tenants activation or settings
    assert "tenants" in response.url.lower() or "settings" in response.url.lower() or "activate" in response.url.lower(), \
        f"Expected redirect to tenants/settings/activate, got {response.url}"


@pytest.mark.django_db
def test_time_logs_page_requires_login(client):
    """
    Test that unauthenticated users cannot access the time logs page.
    """
    url = reverse("inventory:time_logs")
    response = client.get(url)
    
    # Should redirect to login (302) for unauthenticated users
    assert response.status_code == 302, \
        f"Expected redirect for unauthenticated user, got {response.status_code}"
    
    # The app may redirect to tenants page, login, or accounts - all valid for unauthenticated users
    # Just verify it redirects somewhere (not rendering the page itself)
    assert response.url is not None, "Should redirect somewhere, not render the page"


@pytest.mark.django_db
def test_time_logs_page_content_structure(client):
    """
    Test that the time logs page contains expected UI elements.
    """
    # Create user
    user = User.objects.create_user(username="testuser3", email="test3@example.com", password="testpass123")
    
    # Create business
    business = Business.objects.create(
        name="Test Business 3",
        slug="test-business-3",
        business_kind=BusinessKind.PHONES
    )
    
    # Create membership
    Membership.objects.create(
        business=business,
        user=user,
        role="MANAGER",
        status="ACTIVE"
    )
    
    # Login
    client.login(username="testuser3", password="testpass123")
    
    # Set up session
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    
    # Get the page
    url = reverse("inventory:time_logs")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode('utf-8')
    
    # Check for expected elements from the template
    # The template should have table structure, filters, etc.
    assert "Time Logs" in content, "Missing page title"
    
    # The template uses JavaScript to load data, so we just check structure exists
    # Not checking for actual log data since that requires database setup

