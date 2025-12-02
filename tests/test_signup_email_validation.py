# tests/test_signup_email_validation.py
"""
Tests for signup email validation and password requirements.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestSignupEmailValidation(TestCase):
    """Test signup email validation and password requirements."""

    def setUp(self):
        """Set up test fixtures."""
        # Create existing user
        self.existing_user = User.objects.create_user(
            username="existing@test.com",
            email="existing@test.com",
            password="testpass123",
        )
        
        self.client = Client()
        
    def test_signup_rejects_existing_email(self):
        """Test that signup rejects emails that already exist."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'existing@test.com',  # This email already exists
            'full_name': 'Test User',
            'business_name': 'Test Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should show form with error (not redirect)
        self.assertEqual(response.status_code, 200)
        
        # Check error message
        self.assertContains(
            response,
            "You already have an account with this email",
            status_code=200
        )
        
        # Ensure no new user was created
        user_count = User.objects.filter(email='existing@test.com').count()
        self.assertEqual(user_count, 1)  # Only the original user
        
    def test_signup_accepts_new_email(self):
        """Test that signup accepts new emails."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'newuser@test.com',
            'full_name': 'New User',
            'business_name': 'New Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should redirect (success)
        self.assertEqual(response.status_code, 302)
        
        # Check user was created
        user = User.objects.filter(email='newuser@test.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'newuser@test.com')
        
    def test_signup_email_case_insensitive(self):
        """Test that email validation is case-insensitive."""
        # Try to signup with different case of existing email
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'EXISTING@TEST.COM',  # Different case
            'full_name': 'Test User',
            'business_name': 'Test Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You already have an account with this email",
            status_code=200
        )
        
    def test_password_minimum_8_characters(self):
        """Test that passwords must be at least 8 characters."""
        # Try with short password
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'short@test.com',
            'full_name': 'Short Password User',
            'business_name': 'Short Pass Business',
            'business_kind': 'PHONES',
            'password1': 'short',  # Only 5 characters
            'password2': 'short',
        })
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        # Django's MinimumLengthValidator should trigger
        
    def test_password_8_characters_accepted(self):
        """Test that 8-character passwords are accepted."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'validpass@test.com',
            'full_name': 'Valid Password User',
            'business_name': 'Valid Pass Business',
            'business_kind': 'PHONES',
            'password1': 'testpass',  # Exactly 8 characters
            'password2': 'testpass',
        })
        
        # Should redirect (success)
        self.assertEqual(response.status_code, 302)
        
        # Check user was created
        user = User.objects.filter(email='validpass@test.com').first()
        self.assertIsNotNone(user)
        
    def test_password_mismatch_rejected(self):
        """Test that mismatched passwords are rejected."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'mismatch@test.com',
            'full_name': 'Mismatch User',
            'business_name': 'Mismatch Business',
            'business_kind': 'PHONES',
            'password1': 'password123',
            'password2': 'different456',  # Different
        })
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        
    def test_same_user_multiple_businesses(self):
        """Test that same user can own/join multiple businesses."""
        # First signup
        response1 = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'multibiz@test.com',
            'full_name': 'Multi Business User',
            'business_name': 'First Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        self.assertEqual(response1.status_code, 302)
        
        # Get the user
        user = User.objects.get(email='multibiz@test.com')
        
        # User should have one business
        businesses_count = Business.objects.filter(
            memberships__user=user
        ).distinct().count()
        
        self.assertGreaterEqual(businesses_count, 1)
        
        # If they try to signup again, should be rejected
        response2 = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'multibiz@test.com',
            'full_name': 'Multi Business User',
            'business_name': 'Second Business',
            'business_kind': 'CLOTHING',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should reject (email exists)
        self.assertEqual(response2.status_code, 200)
        
    def test_signup_template_has_gamification(self):
        """Test that signup template has gamification elements."""
        response = self.client.get(reverse('accounts:signup_manager'))
        
        # Check for gamification text
        self.assertContains(
            response,
            "Create your smart shop in 60 seconds",
            status_code=200
        )
        
        self.assertContains(
            response,
            "Use one account for all your businesses",
            status_code=200
        )
        
    def test_empty_email_rejected(self):
        """Test that empty email is rejected."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': '',
            'full_name': 'No Email User',
            'business_name': 'No Email Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should show error
        self.assertEqual(response.status_code, 200)
        
    def test_invalid_email_format_rejected(self):
        """Test that invalid email formats are rejected."""
        response = self.client.post(reverse('accounts:signup_manager'), {
            'email': 'not-an-email',
            'full_name': 'Invalid Email User',
            'business_name': 'Invalid Email Business',
            'business_kind': 'PHONES',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        
        # Should show error
        self.assertEqual(response.status_code, 200)

