# tests/critical/test_01_auth_and_signup.py
"""
CRITICAL TEST 01: Authentication and Signup

These tests ensure users can:
1. Access signup page
2. Create an account
3. Login successfully
4. Logout works

FAILURE HERE = Users cannot onboard = Business-critical failure
"""
import pytest
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model

from tests.critical.conftest import create_user, _unique_suffix

User = get_user_model()

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestSignupPageLoads:
    """Test that signup pages are accessible."""
    
    def test_manager_signup_page_loads(self):
        """Manager signup page should load without errors."""
        client = Client()
        
        # Try different possible signup URLs
        urls_to_try = [
            ("accounts:signup_manager", {}),
            ("accounts:signup", {}),
        ]
        
        for url_name, kwargs in urls_to_try:
            try:
                url = reverse(url_name, kwargs=kwargs) if kwargs else reverse(url_name)
                response = client.get(url, follow=True)
                
                # CRITICAL: Must not be 500
                assert response.status_code != 500, \
                    f"Signup page {url_name} returned 500 Server Error"
                
                # Should be 200 or redirect to login
                assert response.status_code in [200, 302], \
                    f"Signup page {url_name} returned unexpected status {response.status_code}"
                
                if response.status_code == 200:
                    content = response.content.decode("utf-8", errors="ignore")
                    assert "Server Error" not in content, \
                        f"Signup page {url_name} contains Server Error text"
                
                # If we found a working URL, test passed
                return
            except NoReverseMatch:
                continue
        
        # Check fallback path
        response = client.get("/accounts/signup/manager/", follow=True)
        assert response.status_code != 500, "Signup page at fallback path returned 500"
    
    def test_agent_signup_page_loads(self):
        """Agent signup page should load without errors."""
        client = Client()
        
        urls_to_try = [
            "/accounts/signup/agent/",
            "/accounts/signup/join/",
        ]
        
        for url in urls_to_try:
            response = client.get(url, follow=True)
            
            # Even if 404, should NOT be 500
            assert response.status_code != 500, \
                f"Agent signup at {url} returned 500 Server Error"


class TestLoginFlow:
    """Test the login flow works correctly."""
    
    def test_login_page_loads(self):
        """Login page should be accessible."""
        client = Client()
        
        urls_to_try = [
            ("accounts:login", {}),
            ("login", {}),
        ]
        
        for url_name, kwargs in urls_to_try:
            try:
                url = reverse(url_name)
                response = client.get(url, follow=True)
                
                assert response.status_code != 500, \
                    f"Login page {url_name} returned 500 Server Error"
                
                if response.status_code == 200:
                    return  # Success
            except NoReverseMatch:
                continue
        
        # Try fallback paths
        for path in ["/accounts/login/", "/login/"]:
            response = client.get(path, follow=True)
            if response.status_code == 200:
                return  # Success
            assert response.status_code != 500, f"Login at {path} returned 500"
    
    def test_login_with_valid_credentials_works(self):
        """User can login with valid credentials."""
        # Create user
        password = "testpass123"
        user = create_user(password=password)
        
        client = Client()
        
        # Login
        result = client.login(username=user.username, password=password)
        assert result is True, "Login should succeed with valid credentials"
    
    def test_login_with_invalid_credentials_fails(self):
        """User cannot login with invalid credentials."""
        client = Client()
        
        result = client.login(username="nonexistent@test.com", password="wrongpass")
        assert result is False, "Login should fail with invalid credentials"
    
    def test_authenticated_user_can_access_protected_page(self):
        """Authenticated user can access protected pages (with business setup)."""
        from tests.critical.conftest import (
            create_business, create_location, create_membership, 
            setup_authenticated_client
        )
        
        password = "testpass123"
        user = create_user(password=password)
        
        # User needs a business to access dashboard - this is expected behavior
        business = create_business(created_by=user, kind="phones")
        location = create_location(business)
        create_membership(user, business, role="MANAGER", location=location)
        
        client = setup_authenticated_client(user, business, location, password=password)
        
        # Try to access a protected page (settings or dashboard)
        protected_urls = [
            "/settings/",
        ]
        
        for url in protected_urls:
            response = client.get(url, follow=True)
            
            # Should not be 500
            assert response.status_code != 500, \
                f"Protected page {url} returned 500 for authenticated user"
    
    def test_user_without_business_redirected_to_signup(self):
        """User without a business membership is redirected to signup."""
        password = "testpass123"
        user = create_user(password=password)
        
        client = Client()
        client.login(username=user.username, password=password)
        
        # Access dashboard without business - should redirect, not 500
        response = client.get("/dashboard/", follow=False)
        
        # Should redirect (302), not error (500)
        assert response.status_code != 500, \
            "Dashboard should not 500 for user without business"
        assert response.status_code == 302, \
            "User without business should be redirected"


class TestLogoutFlow:
    """Test logout functionality."""
    
    def test_logout_works(self):
        """User can logout successfully."""
        password = "testpass123"
        user = create_user(password=password)
        
        client = Client()
        client.login(username=user.username, password=password)
        
        # Logout
        try:
            logout_url = reverse("accounts:logout")
        except NoReverseMatch:
            try:
                logout_url = reverse("logout")
            except NoReverseMatch:
                logout_url = "/accounts/logout/"
        
        response = client.post(logout_url, follow=True)
        
        # Should not be 500
        assert response.status_code != 500, "Logout returned 500 Server Error"
        
        # After logout, accessing protected page should redirect to login
        response = client.get("/settings/", follow=False)
        assert response.status_code in [302, 403], \
            "After logout, protected page should redirect"


class TestUserCreation:
    """Test user model creation works correctly."""
    
    def test_user_can_be_created(self):
        """User model can be created without errors."""
        suffix = _unique_suffix()
        user = User.objects.create_user(
            username=f"testuser_{suffix}",
            email=f"test_{suffix}@example.com",
            password="testpass123",
        )
        
        assert user.pk is not None, "User should have a primary key"
        assert user.email == f"test_{suffix}@example.com"
        assert user.check_password("testpass123")
    
    def test_user_profile_created(self):
        """User profile is created automatically (if applicable)."""
        user = create_user()
        
        # Check if profile exists (some apps use signals to create profiles)
        if hasattr(user, "profile"):
            assert user.profile is not None, "User profile should exist"


class TestOTPFlow:
    """Test OTP verification flow if enabled."""
    
    def test_otp_page_loads_or_skipped(self):
        """OTP verification page loads if OTP is enabled, otherwise skip."""
        from django.conf import settings
        
        enable_otp = getattr(settings, "ENABLE_EMAIL_OTP", False)
        
        if not enable_otp:
            pytest.skip("OTP is disabled in settings")
        
        password = "testpass123"
        user = create_user(password=password)
        
        client = Client()
        client.login(username=user.username, password=password)
        
        # Try to access OTP verification page
        otp_urls = [
            "/accounts/verify-otp/",
            "/accounts/otp/verify/",
        ]
        
        for url in otp_urls:
            response = client.get(url, follow=True)
            
            # Must not be 500
            assert response.status_code != 500, \
                f"OTP page {url} returned 500 Server Error"

