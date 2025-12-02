"""
Tests for the manager signup wizard (4-step flow).
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class ManagerWizardTestCase(TestCase):
    """Test the 4-step manager signup wizard."""

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('accounts:signup_manager')

    def test_step1_renders(self):
        """Test that step 1 renders correctly."""
        response = self.client.get(f"{self.signup_url}?step=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 1 of 4")
        self.assertContains(response, "Your account")

    def test_step1_to_step2_navigation(self):
        """Test navigating from step 1 to step 2."""
        response = self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'test@example.com',
                'full_name': 'Test User',
                'password1': 'TestPassword123!@#',
                'password2': 'TestPassword123!@#',
            }
        )
        # Should redirect to step 2
        self.assertEqual(response.status_code, 302)
        self.assertIn('step=2', response.url)

    def test_step2_requires_step1(self):
        """Test that step 2 redirects to step 1 if step 1 not completed."""
        response = self.client.get(f"{self.signup_url}?step=2")
        # Should redirect back to step 1
        self.assertEqual(response.status_code, 302)
        self.assertIn('step=1', response.url)

    def test_step2_renders_after_step1(self):
        """Test that step 2 renders after completing step 1."""
        # Complete step 1
        self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'test@example.com',
                'full_name': 'Test User',
                'password1': 'TestPassword123!@#',
                'password2': 'TestPassword123!@#',
            }
        )
        
        # Access step 2
        response = self.client.get(f"{self.signup_url}?step=2")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 2 of 4")
        self.assertContains(response, "Your store")

    def test_step2_back_navigation(self):
        """Test back navigation from step 2 to step 1."""
        # Complete step 1
        self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'test@example.com',
                'full_name': 'Test User',
                'password1': 'TestPassword123!@#',
                'password2': 'TestPassword123!@#',
            }
        )
        
        # Go back from step 2
        response = self.client.post(
            f"{self.signup_url}?step=2",
            {
                'step': '2',
                'action': 'back',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('step=1', response.url)

    def test_password_validation(self):
        """Test that weak passwords are rejected."""
        response = self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'test@example.com',
                'full_name': 'Test User',
                'password1': 'weak',
                'password2': 'weak',
            }
        )
        # Should not redirect (form errors)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "password")

    def test_email_validation(self):
        """Test that invalid emails are rejected."""
        response = self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'not-an-email',
                'full_name': 'Test User',
                'password1': 'TestPassword123!@#',
                'password2': 'TestPassword123!@#',
            }
        )
        # Should not redirect (form errors)
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_rejected(self):
        """Test that duplicate emails are rejected."""
        # Create a user first
        User.objects.create_user(
            username='existing@example.com',
            email='existing@example.com',
            password='ExistingPass123!@#'
        )
        
        # Try to sign up with the same email
        response = self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'existing@example.com',
                'full_name': 'Test User',
                'password1': 'TestPassword123!@#',
                'password2': 'TestPassword123!@#',
            }
        )
        # Should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already have an account")

    def test_complete_wizard_creates_user(self):
        """Test that completing the wizard creates a user and business."""
        # Step 1
        self.client.post(
            f"{self.signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'newuser@example.com',
                'full_name': 'New User',
                'password1': 'NewPassword123!@#',
                'password2': 'NewPassword123!@#',
            }
        )
        
        # Step 2
        self.client.post(
            f"{self.signup_url}?step=2",
            {
                'step': '2',
                'action': 'next',
                'business_name': 'Test Store',
                'business_kind': 'phones',
                'subdomain': '',
            }
        )
        
        # Step 3 (skip logo)
        self.client.post(
            f"{self.signup_url}?step=3",
            {
                'step': '3',
                'action': 'next',
            }
        )
        
        # Step 4 (create)
        response = self.client.post(
            f"{self.signup_url}?step=4",
            {
                'step': '4',
                'action': 'create',
                'agree': 'on',
            }
        )
        
        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        
        # User should be created
        user = User.objects.filter(email='newuser@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'New')
        self.assertEqual(user.last_name, 'User')

    def test_url_without_step_defaults_to_step1(self):
        """Test that accessing signup without step parameter shows step 1."""
        response = self.client.get(self.signup_url)
        # Should redirect or show step 1
        if response.status_code == 302:
            self.assertIn('step=1', response.url)
        else:
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Step 1")


@pytest.mark.django_db
class ManagerWizardSessionTests:
    """Test session-based wizard data persistence."""

    def test_wizard_data_persists_across_steps(self, client):
        """Test that wizard data is stored in session."""
        signup_url = reverse('accounts:signup_manager')
        
        # Complete step 1
        client.post(
            f"{signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'persist@example.com',
                'full_name': 'Persist User',
                'password1': 'PersistPass123!@#',
                'password2': 'PersistPass123!@#',
            }
        )
        
        # Check session has step1 data
        session = client.session
        assert 'manager_wizard_data' in session
        assert 'step1' in session['manager_wizard_data']
        assert session['manager_wizard_data']['step1']['email'] == 'persist@example.com'

    def test_wizard_data_cleared_after_completion(self, client):
        """Test that wizard data is cleared after successful completion."""
        signup_url = reverse('accounts:signup_manager')
        
        # Complete all steps
        client.post(
            f"{signup_url}?step=1",
            {
                'step': '1',
                'action': 'next',
                'email': 'clear@example.com',
                'full_name': 'Clear User',
                'password1': 'ClearPass123!@#',
                'password2': 'ClearPass123!@#',
            }
        )
        
        client.post(
            f"{signup_url}?step=2",
            {
                'step': '2',
                'action': 'next',
                'business_name': 'Clear Store',
                'business_kind': 'phones',
            }
        )
        
        client.post(
            f"{signup_url}?step=3",
            {
                'step': '3',
                'action': 'next',
            }
        )
        
        client.post(
            f"{signup_url}?step=4",
            {
                'step': '4',
                'action': 'create',
                'agree': 'on',
            }
        )
        
        # Session should be cleared
        session = client.session
        assert 'manager_wizard_data' not in session

