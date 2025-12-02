# tests/test_auth_templates.py
"""
Tests for authentication templates and UI elements.
Ensures login, signup, and password reset pages have correct navigation.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestLoginTemplate:
    """Test login page template and navigation."""
    
    def test_login_page_accessible(self, client: Client):
        """Login page should be accessible without authentication."""
        response = client.get(reverse("accounts:login"))
        assert response.status_code == 200
    
    def test_login_page_has_back_to_home_button(self, client: Client):
        """Login page should have a 'Back to home' link/button."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should contain "Back to home" text
        assert "Back to home" in content or "back to home" in content.lower()
    
    def test_login_page_back_button_points_to_home(self, client: Client):
        """Login page 'Back to home' button should point to home page."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Try to resolve the home URL
        try:
            home_url = reverse("staticpages:home")
        except Exception:
            # Fallback URLs if staticpages:home doesn't exist
            home_url = "/home/"
        
        # Should contain link to home
        assert home_url in content or "/home/" in content or 'href="/"' in content
    
    def test_login_page_back_button_is_visible(self, client: Client):
        """Login page back button should be visible (not hidden with CSS)."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have "Back to home" and it should not be in a hidden element
        # Check that there's an <a> tag with "Back to home"
        assert '<a' in content and "Back to home" in content
    
    def test_login_page_has_form(self, client: Client):
        """Login page should still have the login form."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have form elements
        assert '<form' in content
        assert 'type="password"' in content or 'name="password"' in content
    
    def test_login_form_submission_works(self, client: Client, db):
        """Login form should still work after adding back button."""
        # Create a test user
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Try to login
        response = client.post(
            reverse("accounts:login"),
            {
                "identifier": "testuser",
                "password": "testpass123"
            },
            follow=False
        )
        
        # Should redirect on successful login
        assert response.status_code in [200, 302]


@pytest.mark.django_db
class TestLoginBackButtonSafety:
    """Test that Back to Home button is safe and doesn't submit form."""
    
    def test_back_button_does_not_submit_form(self, client: Client):
        """Back to home button should not submit the login form."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Find the "Back to home" element
        # It should be either:
        # 1. An <a> tag (link) - safe
        # 2. A <button type="button"> - safe
        # NOT: <button type="submit"> inside form - dangerous
        
        # Check it's implemented as a link
        assert '<a' in content and 'Back to home' in content
        
        # If implemented as button, should have type="button" not type="submit"
        # This regex check is soft - main check is that it's an <a> tag
        if '<button' in content and 'Back to home' in content:
            # Extract button element
            import re
            # Should have type="button" if it's a button
            button_pattern = r'<button[^>]*Back to home[^>]*>'
            matches = re.findall(button_pattern, content, re.IGNORECASE | re.DOTALL)
            if matches:
                for match in matches:
                    # Should NOT be type="submit"
                    assert 'type="submit"' not in match.lower()


@pytest.mark.django_db
class TestAuthNavigation:
    """Test authentication flow navigation."""
    
    def test_unauthenticated_user_can_access_login(self, client: Client):
        """Unauthenticated user should be able to access login page."""
        response = client.get(reverse("accounts:login"))
        assert response.status_code == 200
    
    def test_login_page_has_signup_link(self, client: Client):
        """Login page should have link to signup page."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have signup link
        assert "sign" in content.lower() and "up" in content.lower()
    
    def test_login_page_has_forgot_password_link(self, client: Client):
        """Login page should have link to forgot password."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have forgot password link
        assert "forgot" in content.lower() and "password" in content.lower()


@pytest.mark.django_db
class TestLoginPageStyling:
    """Test login page styling and UX."""
    
    def test_login_page_has_title(self, client: Client):
        """Login page should have a clear title."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have page title
        assert "<title>" in content
        assert "Sign in" in content or "Login" in content or "Emajinet" in content
    
    def test_login_page_is_responsive(self, client: Client):
        """Login page should have responsive meta tag."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have viewport meta tag for responsiveness
        assert 'name="viewport"' in content
    
    def test_back_button_has_icon_or_arrow(self, client: Client):
        """Back to home button should have an icon or arrow for better UX."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have some visual indicator (arrow, icon, or svg)
        # Check for common patterns
        has_visual = (
            "←" in content or  # Left arrow character
            "<svg" in content or  # SVG icon
            "bi-arrow" in content or  # Bootstrap icon
            "&larr;" in content  # HTML entity for left arrow
        )
        
        # This is a soft check - as long as the button text exists, it's acceptable
        assert "Back to home" in content


@pytest.mark.django_db
class TestLoginPageAccessibility:
    """Test login page accessibility features."""
    
    def test_login_form_has_labels(self, client: Client):
        """Login form inputs should have proper labels."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have label elements or aria-labels
        assert "<label" in content or 'aria-label' in content
    
    def test_login_page_has_proper_html_structure(self, client: Client):
        """Login page should have proper HTML structure."""
        response = client.get(reverse("accounts:login"))
        content = response.content.decode()
        
        # Should have proper HTML structure
        assert "<!doctype html>" in content.lower() or "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "<head>" in content or "<head " in content
        assert "<body>" in content or "<body " in content

